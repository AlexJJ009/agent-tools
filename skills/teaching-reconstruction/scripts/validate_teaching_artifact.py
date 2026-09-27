#!/usr/bin/env python3
"""Validate versioned teaching reconstruction Markdown artifacts.

This is intentionally deterministic and dependency-free: it parses the single
version marker and single fenced JSON manifest, validates the frozen v1 shape,
and emits stable error/warning codes for hooks and reviewer evidence.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


MARKER = "<!-- teaching-reconstruction:v1 -->"
MANIFEST_RE = re.compile(r"```json teaching-manifest\r?\n(.*?)\r?\n```", re.DOTALL)
ANY_MARKER_RE = re.compile(r"<!--\s*teaching-reconstruction:([^>\s]+)\s*-->")
MANAGED_RE = re.compile(r"%%zt-managed%%(.*?)%%/zt-managed%%", re.DOTALL)
MANAGED_TOKEN_RE = re.compile(r"%%(?:/)?zt-managed%%")
TEACHING_HEADING_RE = re.compile(
    r"(?im)^\s{0,3}#{1,6}\s+(?:"
    r"teaching(?:\s+(?:reconstruction|map|unit|session))?"
    r"|goal|readerstate|learner\s+state|current\s+frontier|frontier"
    r"|learning\s*check|evidence\s+index|review\s+queue|review\s+verdict"
    r")\b"
)

ALLOWED_STATES = {"mastered", "callable", "fragile", "unknown", "conflict"}
UNFINISHED_STATES = {"fragile", "unknown", "conflict"}
SATISFIED_STATES = {"mastered", "callable"}
ALLOWED_EDGE_TYPES = {"strict", "common", "convenience"}
ALLOWED_MODES = {
    "guided",
    "guided-direct",
    "artifact",
    "survey-as-learning",
    "paper-code",
    "reconstruction-audit",
    "check-only",
}
ALLOWED_LAYERS = {
    "source_fact",
    "runtime_fact",
    "inference",
    "design_mapping",
    "teaching_reconstruction",
    "advice",
}
ALLOWED_CHECK_TYPES = {
    "reconstruction",
    "retrieval",
    "near_transfer",
    "far_transfer",
    "evidence_location",
    "counterexample",
    "artifact_transfer",
    "artifact_audit",
}
TOP_LEVEL_FIELDS = {
    "schema_version",
    "artifact_id",
    "mode",
    "goal",
    "learner_state",
    "teaching_unit",
    "knowledge_components",
    "teaching_edges",
    "frontier",
    "evidence_anchors",
    "learning_checks",
    "review_queue",
}
KC_FIELDS = {
    "id",
    "ability",
    "state",
    "definition",
    "why_needed",
    "prerequisites",
    "witnesses",
    "worked_example",
    "checks",
}
EDGE_FIELDS = {"id", "from", "to", "edge_type", "failure_without", "witness"}
ANCHOR_FIELDS = {
    "anchor_id",
    "claim",
    "source_kind",
    "layer",
    "status",
    "verified_at",
    "boundary",
    "locator",
}
CHECK_FIELDS = {
    "check_id",
    "kc",
    "type",
    "prompt",
    "success_signal",
    "failure_prerequisite",
    "evidence",
}
CARD_FIELDS = {
    "card_id",
    "kc",
    "prompt",
    "due_or_trigger",
    "target_note",
    "check_id",
    "status",
}


@dataclass
class ValidationResult:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors

    def error(self, code: str) -> None:
        if code not in self.errors:
            self.errors.append(code)

    def warn(self, code: str) -> None:
        if code not in self.warnings:
            self.warnings.append(code)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _is_nonempty_string(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _has_fields(obj: Any, fields: set[str]) -> bool:
    return isinstance(obj, dict) and fields <= set(obj)


def _managed_spans(text: str, result: ValidationResult | None = None) -> list[tuple[int, int, str]]:
    spans: list[tuple[int, int, str]] = []
    opened: tuple[int, int] | None = None
    for match in MANAGED_TOKEN_RE.finditer(text):
        token = match.group(0)
        if token == "%%zt-managed%%":
            if opened is not None:
                if result is not None:
                    result.error("MANAGED_REGION_BOUNDARY")
                start, body_start = opened
                spans.append((start, match.start(), text[body_start : match.start()]))
            opened = (match.start(), match.end())
        elif opened is None:
            if result is not None:
                result.error("MANAGED_REGION_BOUNDARY")
        else:
            start, body_start = opened
            spans.append((start, match.end(), text[body_start : match.start()]))
            opened = None
    if opened is not None:
        if result is not None:
            result.error("MANAGED_REGION_BOUNDARY")
        start, body_start = opened
        spans.append((start, len(text), text[body_start:]))
    return spans


def _inside_any_span(start: int, end: int, spans: list[tuple[int, int, str]]) -> bool:
    return any(span_start <= start and end <= span_end for span_start, span_end, _ in spans)


def _validate_managed_boundaries(text: str, result: ValidationResult) -> list[tuple[int, int, str]]:
    spans = _managed_spans(text, result)
    for m in re.finditer(re.escape(MARKER), text):
        if _inside_any_span(m.start(), m.end(), spans):
            result.error("MANAGED_REGION")
    for _, _, body in spans:
        if TEACHING_HEADING_RE.search(body):
            result.error("MANAGED_REGION_HEADING")
    return spans


def parse_manifest(text: str, result: ValidationResult) -> dict[str, Any] | None:
    spans = _validate_managed_boundaries(text, result)

    marker_count = text.count(MARKER)
    if marker_count == 0:
        any_marker = ANY_MARKER_RE.search(text)
        result.error("VERSION_MARKER_WRONG" if any_marker else "VERSION_MARKER_MISSING")
    elif marker_count > 1:
        result.error("VERSION_MARKER_DUPLICATE")

    blocks = MANIFEST_RE.findall(text)
    if len(blocks) != 1:
        result.error("MANIFEST_DUPLICATE" if len(blocks) > 1 else "MANIFEST_MISSING")
        return None

    block_match = MANIFEST_RE.search(text)
    if block_match and _inside_any_span(block_match.start(), block_match.end(), spans):
        result.error("MANAGED_REGION")

    try:
        data = json.loads(blocks[0])
    except json.JSONDecodeError:
        result.error("MANIFEST_JSON")
        return None
    if not isinstance(data, dict):
        result.error("MANIFEST_JSON")
        return None
    if data.get("schema_version") != "teaching-reconstruction:v1":
        result.error("VERSION_MARKER_WRONG")
    return data


def _validate_top_level(data: dict[str, Any], result: ValidationResult) -> None:
    if not TOP_LEVEL_FIELDS <= set(data):
        result.error("MISSING_MANIFEST_FIELD")
    if not _is_nonempty_string(data.get("artifact_id")):
        result.error("MISSING_MANIFEST_FIELD")
    if data.get("mode") not in ALLOWED_MODES:
        result.error("ILLEGAL_MODE")
    for field_name in (
        "knowledge_components",
        "teaching_edges",
        "frontier",
        "evidence_anchors",
        "learning_checks",
        "review_queue",
    ):
        if not isinstance(data.get(field_name), list):
            result.error("MISSING_MANIFEST_FIELD")
    for field_name in ("knowledge_components", "evidence_anchors", "learning_checks"):
        if not _as_list(data.get(field_name)):
            result.error("MISSING_MANIFEST_FIELD")


def _validate_guided_core(data: dict[str, Any], result: ValidationResult) -> None:
    goal = data.get("goal")
    learner_state = data.get("learner_state")
    teaching_unit = data.get("teaching_unit")
    success_criteria = goal.get("success_criteria") if isinstance(goal, dict) else None
    goal_ok = (
        isinstance(goal, dict)
        and _is_nonempty_string(goal.get("target_ability"))
        and isinstance(success_criteria, list)
        and bool(success_criteria)
        and all(_is_nonempty_string(item) for item in success_criteria)
    )
    learner_ok = (
        isinstance(learner_state, dict)
        and isinstance(learner_state.get("profile_sources"), list)
        and isinstance(learner_state.get("assumptions"), list)
        and isinstance(learner_state.get("observed_gaps"), list)
    )
    unit_ok = (
        isinstance(teaching_unit, dict)
        and _is_nonempty_string(teaching_unit.get("kc"))
        and _is_nonempty_string(teaching_unit.get("explanation"))
        and _is_nonempty_string(teaching_unit.get("worked_step"))
        and _is_nonempty_string(teaching_unit.get("next_action"))
    )
    if not (goal_ok and learner_ok and unit_ok):
        result.error("MISSING_GUIDED_CORE")


def _validate_kcs(data: dict[str, Any], result: ValidationResult) -> tuple[dict[str, dict[str, Any]], set[str]]:
    kcs: dict[str, dict[str, Any]] = {}
    duplicate_ids: set[str] = set()
    for kc in _as_list(data.get("knowledge_components")):
        if not isinstance(kc, dict) or not KC_FIELDS <= set(kc):
            result.error("MISSING_CORE_FIELD")
            continue
        kc_id = kc.get("id")
        if not _is_nonempty_string(kc_id):
            result.error("MISSING_CORE_FIELD")
            continue
        if kc_id in kcs:
            duplicate_ids.add(kc_id)
        kcs[kc_id] = kc
        if kc.get("state") not in ALLOWED_STATES:
            result.error("ILLEGAL_KC_STATE")
        for field_name in ("prerequisites", "witnesses", "checks"):
            if not isinstance(kc.get(field_name), list):
                result.error("MISSING_CORE_FIELD")
        for field_name in ("ability", "definition", "why_needed", "worked_example"):
            if not _is_nonempty_string(kc.get(field_name)):
                result.error("MISSING_CORE_FIELD")
    if duplicate_ids:
        result.error("DUPLICATE_KC")

    frontier = _as_list(data.get("frontier"))
    if len(frontier) != len(set(item for item in frontier if isinstance(item, str))):
        result.error("DUPLICATE_FRONTIER")
    for frontier_id in frontier:
        kc = kcs.get(frontier_id)
        if kc is None or kc.get("state") not in UNFINISHED_STATES:
            result.error("ILLEGAL_FRONTIER")
        elif any(
            kcs.get(prereq, {}).get("state") not in SATISFIED_STATES
            for prereq in _as_list(kc.get("prerequisites"))
        ):
            result.error("ILLEGAL_FRONTIER")

    teaching_unit = data.get("teaching_unit")
    if isinstance(teaching_unit, dict) and teaching_unit.get("kc") not in kcs:
        result.error("MISSING_GUIDED_CORE")
    return kcs, duplicate_ids


def _validate_edges(
    data: dict[str, Any],
    kcs: dict[str, dict[str, Any]],
    anchor_ids: set[str],
    result: ValidationResult,
    *,
    disabled_rules: set[str],
) -> None:
    edge_ids: set[str] = set()
    edge_pairs: set[tuple[str, str]] = set()
    graph: dict[str, list[str]] = {kc_id: [] for kc_id in kcs}

    for edge in _as_list(data.get("teaching_edges")):
        if not isinstance(edge, dict) or not EDGE_FIELDS <= set(edge):
            result.error("MISSING_TEACHING_EDGE")
            continue
        edge_id = edge.get("id")
        if not _is_nonempty_string(edge_id):
            result.error("MISSING_TEACHING_EDGE")
        if edge_id in edge_ids:
            result.error("DUPLICATE_EDGE")
        edge_ids.add(edge_id)
        src = edge.get("from")
        dst = edge.get("to")
        if src not in kcs or dst not in kcs:
            result.error("MISSING_PREREQUISITE")
        else:
            graph[src].append(dst)
            edge_pairs.add((src, dst))
        if edge.get("edge_type") not in ALLOWED_EDGE_TYPES:
            result.error("ILLEGAL_EDGE_TYPE")
        if edge.get("witness") not in anchor_ids:
            result.error("MISSING_WITNESS")
        if not _is_nonempty_string(edge.get("failure_without")):
            result.error("MISSING_TEACHING_EDGE")

    prereq_pairs: set[tuple[str, str]] = set()
    for kc_id, kc in kcs.items():
        for prereq in _as_list(kc.get("prerequisites")):
            if prereq not in kcs:
                result.error("MISSING_PREREQUISITE")
            else:
                prereq_pairs.add((prereq, kc_id))
    if prereq_pairs != edge_pairs:
        missing = prereq_pairs - edge_pairs
        extra = edge_pairs - prereq_pairs
        if missing or extra:
            result.error("MISSING_TEACHING_EDGE")

    if "cycle" not in disabled_rules and _has_cycle(graph):
        result.error("CYCLE")


def _has_cycle(graph: dict[str, list[str]]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node: str) -> bool:
        if node in visiting:
            return True
        if node in visited:
            return False
        visiting.add(node)
        for nxt in graph.get(node, []):
            if visit(nxt):
                return True
        visiting.remove(node)
        visited.add(node)
        return False

    return any(visit(node) for node in graph)


def _validate_anchors(data: dict[str, Any], result: ValidationResult) -> set[str]:
    anchors: dict[str, dict[str, Any]] = {}
    for anchor in _as_list(data.get("evidence_anchors")):
        if not _has_fields(anchor, ANCHOR_FIELDS):
            result.error("EVIDENCE_CORE")
            continue
        anchor_id = anchor.get("anchor_id")
        if not _is_nonempty_string(anchor_id):
            result.error("EVIDENCE_CORE")
            continue
        if anchor_id in anchors:
            result.error("DUPLICATE_ANCHOR")
        anchors[anchor_id] = anchor
        for field_name in ("claim", "source_kind", "layer", "status", "verified_at", "boundary"):
            if not _is_nonempty_string(anchor.get(field_name)):
                result.error("EVIDENCE_CORE")
        if anchor.get("layer") not in ALLOWED_LAYERS:
            result.error("EVIDENCE_LAYER")
        locator = anchor.get("locator")
        if not isinstance(locator, dict):
            result.error("EVIDENCE_CORE")
            continue
        source_kind = anchor.get("source_kind")
        if source_kind not in {"paper", "code", "log", "web"}:
            result.error("EVIDENCE_CORE")
        status = anchor.get("status")
        if status == "verified":
            _validate_verified_locator(source_kind, locator, result)
        elif status == "provisional":
            _validate_provisional_locator(source_kind, locator, result)
            result.warn("PROVISIONAL_ANCHOR")
        else:
            result.error("EVIDENCE_STATUS")
    return set(anchors)


def _validate_provisional_locator(source_kind: str, locator: dict[str, Any], result: ValidationResult) -> None:
    valid = False
    if source_kind == "paper":
        valid = _is_nonempty_string(locator.get("zotero_item_key"))
    elif source_kind == "code":
        valid = _is_nonempty_string(locator.get("repository")) and _is_nonempty_string(locator.get("path"))
    elif source_kind == "log":
        valid = (
            _is_nonempty_string(locator.get("run_id")) or _is_nonempty_string(locator.get("artifact_id"))
        ) and _is_nonempty_string(locator.get("artifact_path"))
    elif source_kind == "web":
        valid = _is_nonempty_string(locator.get("canonical_url")) and _is_nonempty_string(locator.get("retrieved_at"))
    if not valid:
        result.error("PROVISIONAL_LOCATOR")


def _validate_verified_locator(source_kind: str, locator: dict[str, Any], result: ValidationResult) -> None:
    if source_kind == "paper":
        if not (
            _is_nonempty_string(locator.get("zotero_item_key"))
            and _is_nonempty_string(locator.get("zotero_pdf_key"))
            and isinstance(locator.get("page"), int)
            and locator["page"] > 0
        ):
            result.error("PAPER_LOCATOR")
    elif source_kind == "code":
        revision = locator.get("revision")
        if not (
            _is_nonempty_string(locator.get("repository"))
            and isinstance(revision, str)
            and re.fullmatch(r"[0-9a-fA-F]{40}", revision)
            and _is_nonempty_string(locator.get("path"))
            and isinstance(locator.get("line_start"), int)
            and isinstance(locator.get("line_end"), int)
            and locator["line_start"] > 0
            and locator["line_start"] <= locator["line_end"]
        ):
            result.error("CODE_REVISION")
    elif source_kind == "log":
        has_time_or_lines = _is_nonempty_string(locator.get("timestamp")) or (
            isinstance(locator.get("line_start"), int)
            and isinstance(locator.get("line_end"), int)
            and locator["line_start"] > 0
            and locator["line_start"] <= locator["line_end"]
        )
        if not (
            (_is_nonempty_string(locator.get("run_id")) or _is_nonempty_string(locator.get("artifact_id")))
            and _is_nonempty_string(locator.get("artifact_path"))
            and isinstance(locator.get("artifact_sha256"), str)
            and re.fullmatch(r"[0-9a-fA-F]{64}", locator.get("artifact_sha256", ""))
            and has_time_or_lines
        ):
            result.error("LOG_ARTIFACT")
    elif source_kind == "web":
        has_snapshot_ref = _is_nonempty_string(locator.get("snapshot_path")) or _is_nonempty_string(
            locator.get("zotero_item_key")
        )
        if not (
            _is_nonempty_string(locator.get("canonical_url"))
            and _is_nonempty_string(locator.get("retrieved_at"))
            and has_snapshot_ref
            and isinstance(locator.get("snapshot_sha256"), str)
            and re.fullmatch(r"[0-9a-fA-F]{64}", locator.get("snapshot_sha256", ""))
        ):
            result.error("WEB_SNAPSHOT")


def _validate_checks_and_cards(
    data: dict[str, Any],
    kcs: dict[str, dict[str, Any]],
    anchor_ids: set[str],
    result: ValidationResult,
) -> None:
    checks: dict[str, dict[str, Any]] = {}
    for check in _as_list(data.get("learning_checks")):
        if not _has_fields(check, CHECK_FIELDS):
            result.error("MISSING_CHECK")
            continue
        check_id = check.get("check_id")
        if not _is_nonempty_string(check_id):
            result.error("MISSING_CHECK")
            continue
        if check_id in checks:
            result.error("DUPLICATE_CHECK")
        checks[check_id] = check
        if check.get("kc") not in kcs:
            result.error("MISSING_CHECK")
        if check.get("type") not in ALLOWED_CHECK_TYPES:
            result.error("CHECK_TYPE")
        failure_prereq = check.get("failure_prerequisite")
        if failure_prereq is not None and failure_prereq not in kcs:
            result.error("MISSING_PREREQUISITE")
        if (
            not isinstance(check.get("evidence"), list)
            or not check.get("evidence")
            or any(e not in anchor_ids for e in check.get("evidence", []))
        ):
            result.error("MISSING_WITNESS")
        for field_name in ("type", "prompt", "success_signal"):
            if not _is_nonempty_string(check.get(field_name)):
                result.error("MISSING_CHECK")

    for kc_id, kc in kcs.items():
        kc_check_ids = _as_list(kc.get("checks"))
        if any(check_id not in checks for check_id in kc_check_ids):
            result.error("MISSING_CHECK")
        kc_checks = [checks[c] for c in kc_check_ids if c in checks]
        check_types = {c.get("type") for c in kc_checks}
        has_reconstruct_retrieve = {"reconstruction", "retrieval"} <= check_types
        has_artifact_audit_pair = {"artifact_transfer", "artifact_audit"} <= check_types
        if not (has_reconstruct_retrieve or has_artifact_audit_pair):
            result.error("MISSING_CHECK")
        for witness in _as_list(kc.get("witnesses")):
            if witness not in anchor_ids:
                result.error("MISSING_WITNESS")

    all_types = {check.get("type") for check in checks.values()}
    if not {"reconstruction", "retrieval"} <= all_types:
        result.error("MISSING_CHECK")
    if data.get("mode") == "artifact":
        if not {"reconstruction", "retrieval", "artifact_transfer", "artifact_audit"} <= all_types:
            result.error("ARTIFACT_TRANSFER")

    card_ids: set[str] = set()
    for card in _as_list(data.get("review_queue")):
        if not _has_fields(card, CARD_FIELDS):
            result.error("REVIEW_QUEUE_FIELDS")
            continue
        card_id = card.get("card_id")
        if card_id in card_ids:
            result.error("REVIEW_QUEUE_DUPLICATE")
        card_ids.add(card_id)
        target_note = card.get("target_note")
        if not (
            _is_nonempty_string(card_id)
            and card.get("kc") in kcs
            and card.get("check_id") in checks
            and _is_nonempty_string(card.get("prompt"))
            and _is_nonempty_string(card.get("due_or_trigger"))
            and isinstance(target_note, str)
            and target_note.startswith("[[")
            and target_note.endswith("]]")
            and _is_nonempty_string(card.get("status"))
        ):
            if card.get("check_id") not in checks or card.get("kc") not in kcs:
                result.error("REVIEW_QUEUE_ORPHAN")
            else:
                result.error("REVIEW_QUEUE_FIELDS")


def validate_text(text: str, *, disabled_rules: set[str] | None = None) -> ValidationResult:
    disabled_rules = disabled_rules or set()
    result = ValidationResult()
    data = parse_manifest(text, result)
    if data is None:
        return result

    _validate_top_level(data, result)
    _validate_guided_core(data, result)
    anchor_ids = _validate_anchors(data, result)
    kcs, _ = _validate_kcs(data, result)
    _validate_edges(data, kcs, anchor_ids, result, disabled_rules=disabled_rules)
    _validate_checks_and_cards(data, kcs, anchor_ids, result)
    return result


def validate_file(path: Path, *, disabled_rules: set[str] | None = None) -> ValidationResult:
    try:
        return validate_text(path.read_text(encoding="utf-8"), disabled_rules=disabled_rules)
    except (OSError, UnicodeDecodeError):
        result = ValidationResult()
        result.error("READ_ERROR")
        return result


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", *args], cwd=repo, capture_output=True, check=False)


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="surrogateescape")


def _managed_region_bodies(text: str) -> list[str]:
    return [text[start:end] for start, end, _ in _managed_spans(text)]


def _managed_region_segments(text: str) -> dict[str, set[int]]:
    """Map unchanged nonblank lines to the managed-region segment containing them.

    A line moving from one side of a managed block to the other is observable
    evidence that the block crossed durable user content. New or edited lines
    remain allowed because they do not occur unchanged in both revisions.
    """

    positions: dict[str, set[int]] = {}
    cursor = 0
    spans = _managed_spans(text)
    chunks: list[str] = []
    for start, end, _ in spans:
        chunks.append(text[cursor:start])
        cursor = end
    chunks.append(text[cursor:])
    for segment, chunk in enumerate(chunks):
        for line in chunk.splitlines():
            normalized = line.strip()
            if normalized:
                positions.setdefault(normalized, set()).add(segment)
    return positions


def _managed_region_crossed_unchanged_content(old_text: str, new_text: str) -> bool:
    old_positions = _managed_region_segments(old_text)
    new_positions = _managed_region_segments(new_text)
    for line in old_positions.keys() & new_positions.keys():
        if len(old_positions[line]) == 1 and len(new_positions[line]) == 1:
            if old_positions[line] != new_positions[line]:
                return True
    return False


def _merge_result(parent: ValidationResult, child: ValidationResult) -> None:
    for code in child.errors:
        parent.error(code)
    for code in child.warnings:
        parent.warn(code)


def _staged_changes(repo: Path, result: ValidationResult) -> list[tuple[str | None, str | None]]:
    names = _git(repo, "diff", "--cached", "--name-status", "-z", "--find-renames")
    if names.returncode != 0:
        result.error("GIT_STAGED")
        return []
    tokens = names.stdout.split(b"\0")
    changes: list[tuple[str | None, str | None]] = []
    index = 0
    while index < len(tokens) and tokens[index]:
        status = tokens[index].decode("ascii", errors="replace")
        index += 1
        if status.startswith(("R", "C")):
            if index + 1 >= len(tokens):
                result.error("GIT_STAGED")
                break
            old_rel = _decode(tokens[index])
            new_rel = _decode(tokens[index + 1])
            index += 2
        else:
            if index >= len(tokens):
                result.error("GIT_STAGED")
                break
            rel = _decode(tokens[index])
            index += 1
            old_rel = None if status.startswith("A") else rel
            new_rel = None if status.startswith("D") else rel
        changes.append((old_rel, new_rel))
    return changes


def validate_staged(repo: Path) -> ValidationResult:
    result = ValidationResult()
    baseline = _git(repo, "rev-parse", "--verify", "HEAD")
    if baseline.returncode != 0:
        result.error("GIT_BASELINE_MISSING")
        return result
    for old_rel, new_rel in _staged_changes(repo, result):
        if not any(rel and rel.endswith(".md") for rel in (old_rel, new_rel)):
            continue
        head_text = ""
        index_text = ""
        if old_rel is not None:
            head_blob = _git(repo, "show", f"HEAD:{old_rel}")
            if head_blob.returncode == 0:
                head_text = _decode(head_blob.stdout)
        if new_rel is not None:
            index_blob = _git(repo, "show", f":{new_rel}")
            if index_blob.returncode == 0:
                index_text = _decode(index_blob.stdout)

        if (
            _managed_region_bodies(head_text) != _managed_region_bodies(index_text)
            or _managed_region_crossed_unchanged_content(head_text, index_text)
        ):
            result.error("MANAGED_REGION_STAGED")

        boundary_result = ValidationResult()
        _validate_managed_boundaries(index_text, boundary_result)
        _merge_result(result, boundary_result)

        if ANY_MARKER_RE.search(index_text) or "```json teaching-manifest" in index_text:
            _merge_result(result, validate_text(index_text))
    return result


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def run_self_test(disabled_rules: set[str]) -> int:
    fixtures = _repo_root_from_script() / "tests" / "fixtures" / "teaching"
    failures: list[str] = []
    mutation_caught = False
    for fixture in sorted(fixtures.glob("*.md")):
        result = validate_file(fixture, disabled_rules=disabled_rules)
        if fixture.name.startswith("good_"):
            if not result.ok:
                failures.append(f"{fixture.name}: expected valid got {','.join(result.errors)}")
        elif fixture.name.startswith("bad_"):
            if result.ok:
                if disabled_rules and fixture.name == "bad_cycle.md" and "cycle" in disabled_rules:
                    mutation_caught = True
                else:
                    failures.append(f"{fixture.name}: expected invalid")

    if disabled_rules:
        if mutation_caught:
            print(f"MUTATION_CAUGHT {','.join(sorted(disabled_rules))}")
            return 1
        print(f"MUTATION_NOT_CAUGHT {','.join(sorted(disabled_rules))}")
        for failure in failures:
            print(failure)
        return 1

    if failures:
        for failure in failures:
            print(failure, file=sys.stderr)
        return 1
    print("SELF_TEST_PASS")
    return 0


def emit_result(result: ValidationResult, *, staged: bool = False) -> int:
    for warning in sorted(result.warnings):
        print(warning)
    if result.ok:
        print("STAGED_VALID" if staged else "VALID")
        return 0
    print("INVALID " + " ".join(sorted(result.errors)), file=sys.stderr)
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", nargs="?")
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--self-test-disable-rule", action="append", default=[])
    parser.add_argument("--staged", action="store_true")
    parser.add_argument("--repo", default=".")
    args = parser.parse_args(argv)

    disabled_rules = set(args.self_test_disable_rule)
    if args.self_test:
        return run_self_test(disabled_rules)
    if args.staged:
        return emit_result(validate_staged(Path(args.repo)), staged=True)
    if not args.artifact:
        parser.error("artifact path required unless --self-test or --staged is used")
    return emit_result(validate_file(Path(args.artifact), disabled_rules=disabled_rules))


if __name__ == "__main__":
    raise SystemExit(main())
