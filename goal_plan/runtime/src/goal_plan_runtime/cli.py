from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from string import Template
from typing import Any


REQUIRED_PLAN_SECTIONS = (
    "Outcome",
    "Scope",
    "Acceptance Criteria",
    "Feasibility Probes",
    "Milestones",
    "Runtime Contract",
    "Progression Policy",
    "Reviewer Contract",
    "Verification Commands",
)
VALID_EVENTS = {
    "PLAN_CREATED",
    "PLAN_AMENDED",
    "PLAN_REVIEWED",
    "MILESTONE_STARTED",
    "MILESTONE_COMPLETED",
    "MILESTONE_REVIEWED",
    "REVIEW_REQUESTED",
    "REVIEW_COMPLETED",
    "ACCEPTANCE_REQUESTED",
    "ACCEPTANCE_COMPLETED",
    "RISK_NOTICE_RECORDED",
    "USER_DECISION_REQUESTED",
    "USER_DECISION_RECORDED",
    "IDENTITY_CONFIGURED",
    "GOAL_COMPLETED",
    "GOAL_BLOCKED",
    "EVENT_CORRECTED",
}
# Absolute numeric budgets in an AC (latency, size, throughput, percentile
# targets) must be backed by a feasibility probe before the plan is READY.
BUDGET_PATTERN = re.compile(
    r"\b\d[\d,.]*\s*(?:ms|msec|milliseconds?|MiB|MB|GiB|GB|KiB|KB|req/s|rps|qps)\b"
    r"|\bp\d{2}\b",
    re.IGNORECASE,
)
VALID_FINDING_EVENTS = {
    "FINDING_OPENED",
    "FINDING_CLASSIFIED",
    "FINDING_FIX_PROPOSED",
    "FINDING_FIX_APPLIED",
    "FINDING_REVIEWED",
    "FINDING_CLOSED",
    "FINDING_REOPENED",
    "FINDING_CORRECTED",
}
FINDING_CLASSES = {"IN_SCOPE", "DEFERRED", "CONTRADICTION", "AC_CHANGE"}
REVIEW_VERDICTS = {"READY", "NOT_READY", "PASS", "FAIL", "WEAKENED", "CONTRADICTION"}
STOP_CATEGORIES = {
    "deletion",
    "destructive_or_hard_to_reverse",
    "public_sharing_or_exposure_expansion",
    "permission_expansion",
    "owner_transfer",
    "force_or_history_rewrite",
    "non_disposable_live_object_access",
    "credential_or_sensitive_data_exposure",
    "tool_confirmation_required",
    "new_outcome_or_out_of_scope",
    "CONTRADICTION",
    "AC_CHANGE",
}
AGENT_IDENTITIES = {
    "claude": ("Claude", "noreply@anthropic.com"),
    "codex": ("Codex", "noreply@openai.com"),
}
IDENTITY_HOOK = """\
#!/usr/bin/env bash
# goal-plan identity guard - installed by `goal-plan-runtime setup-identity`.
# Rejects commits whose author or committer email is not an allowed goal identity.
set -euo pipefail
hookdir="$(cd -- "$(dirname -- "$0")" && pwd)"
allow="$hookdir/goal-allowed-emails.txt"
ident="$(git var GIT_AUTHOR_IDENT)"
author="${ident##*<}"; author="${author%%>*}"
cident="$(git var GIT_COMMITTER_IDENT)"
committer="${cident##*<}"; committer="${committer%%>*}"
allowed() { [[ -f "$allow" ]] && grep -qxF "$1" "$allow"; }
if allowed "$author" && allowed "$committer"; then
  exit 0
fi
{
  echo "goal-plan identity guard: author '$author' and committer '$committer' must both be allowed goal identities."
  echo "allowed:"; sed 's/^/  - /' "$allow" 2>/dev/null || true
  echo "fix: goal-plan-runtime setup-identity <repo> --agent claude|codex"
} >&2
exit 1
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def plan_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def append_jsonl(path: Path, record: dict[str, Any]) -> dict[str, Any]:
    records = load_jsonl(path)
    record = dict(record)
    record["seq"] = len(records) + 1
    record.setdefault("time", utc_now())
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(canonical_json(record) + "\n")
    return record


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number}: expected JSON object")
        records.append(value)
    return records


def validate_sequence(records: list[dict[str, Any]], path: Path) -> list[str]:
    errors = []
    for index, record in enumerate(records, 1):
        if record.get("seq") != index:
            errors.append(f"{path}: expected seq {index}, got {record.get('seq')!r}")
        if not isinstance(record.get("time"), str):
            errors.append(f"{path}:{index}: missing time")
    return errors


def section_body(text: str, section: str) -> str:
    match = re.search(
        rf"^## {re.escape(section)}\s*$\n(?P<body>.*?)(?=^##\s|\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body") if match else ""


def milestone_authorization_values(body: str) -> list[str]:
    lines = body.splitlines()
    start = next(
        (index for index, line in enumerate(lines) if re.match(r"^\s*-\s*Milestone overrides:", line, re.IGNORECASE)),
        None,
    )
    if start is None:
        return []
    first = lines[start].split(":", 1)[1].strip().rstrip(".")
    if first.lower() in {"`none`", "none"}:
        return []
    values = []
    if first:
        first_match = re.search(r":\s*`?([A-Za-z][A-Za-z_]*)`?", first)
        if first_match:
            values.append(first_match.group(1).upper())
    for line in lines[start + 1:]:
        match = re.match(r"^\s{2,}-\s*`?[^:`]+:\s*([A-Za-z][A-Za-z_]*)`?", line)
        if not match:
            break
        values.append(match.group(1).upper())
    return values


def validate_plan(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors = []
    for section in REQUIRED_PLAN_SECTIONS:
        if not re.search(rf"^##\s+{re.escape(section)}\s*$", text, re.MULTILINE):
            errors.append(f"missing section: {section}")
    if re.search(r"^- Authorization policy version:\s*`?2`?\s*$", text, re.MULTILINE):
        if not re.search(r"^##\s+Authorization Policy\s*$", text, re.MULTILINE):
            errors.append("missing section: Authorization Policy")
    outcome = re.search(r"^## Outcome\s*$\n(?P<body>.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not outcome or not outcome.group("body").strip():
        errors.append("Outcome must contain one concrete capability, artifact, or decision")
    criteria = re.findall(r"^###\s+(AC-[A-Za-z0-9_-]+)\b(?P<body>.*?)(?=^###\s+AC-|^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    if not criteria:
        errors.append("Acceptance Criteria must define at least one AC")
    feasibility_body = section_body(text, "Feasibility Probes")
    for ac_id, body in criteria:
        for word in ("Given", "When", "Then"):
            if not re.search(rf"\b{word}\b", body):
                errors.append(f"{ac_id}: missing {word}")
        if not re.search(r"Verification command", body, re.IGNORECASE):
            errors.append(f"{ac_id}: missing verification command")
        if not re.search(r"Expected evidence", body, re.IGNORECASE):
            errors.append(f"{ac_id}: missing expected evidence")
        if BUDGET_PATTERN.search(body) and ac_id not in feasibility_body:
            errors.append(
                f"{ac_id}: declares a numeric budget; record a feasibility probe"
                " (or an explicit waiver) for it under Feasibility Probes"
            )
    progression_body = section_body(text, "Progression Policy")
    for marker in ("AUTO_ADVANCE", "USER_DECISION"):
        if marker not in progression_body:
            errors.append(f"Progression Policy missing class: {marker}")
    authorization_body = section_body(text, "Authorization Policy")
    if authorization_body:
        authorization_markers = (
            "DEFAULT_AUTHORIZED",
            "Whole-Goal authorization",
            "Milestone overrides",
            "RISK_NOTICE",
            "PREAUTHORIZED_STOP_ACTION",
            "USER_DECISION",
        )
        for marker in authorization_markers:
            if marker.lower() not in authorization_body.lower():
                errors.append(f"Authorization Policy missing rule: {marker}")
        valid_overrides = {"INHERIT", "AUTHORIZED", "HOLD", "DENIED"}
        for value in milestone_authorization_values(authorization_body):
            if value not in valid_overrides:
                errors.append(f"Authorization Policy invalid milestone override: {value}")
    required_rules = (
        "IN_SCOPE",
        "DEFERRED",
        "CONTRADICTION",
        "AC_CHANGE",
        "implementer",
        "reviewer",
        "two related",
    )
    runtime_match = re.search(r"^## Runtime Contract\s*$\n(?P<body>.*?)(?=^##\s|\Z)", text, re.MULTILINE | re.DOTALL)
    runtime_body = runtime_match.group("body") if runtime_match else ""
    for rule in required_rules:
        if rule.lower() not in runtime_body.lower():
            errors.append(f"Runtime Contract missing rule: {rule}")
    return errors


def apply_corrections(
    records: list[dict[str, Any]],
    correction_event: str,
    ledger_name: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    sequences = {record.get("seq") for record in records}
    correction_records = [record for record in records if record.get("event") == correction_event]
    corrected_corrections = {
        record.get("corrects_seq")
        for record in correction_records
        if record.get("corrects_seq") in {candidate.get("seq") for candidate in correction_records}
    }
    active_corrections = [record for record in correction_records if record.get("seq") not in corrected_corrections]
    correction_targets = {record.get("corrects_seq") for record in active_corrections}
    errors = []
    for record in active_corrections:
        target = record.get("corrects_seq")
        if not isinstance(target, int) or target not in sequences or target >= record.get("seq", 0):
            errors.append(f"{ledger_name} seq {record.get('seq')}: correction target is missing")
    effective_records = [
        dict(record, seq=index)
        for index, record in enumerate(
            [
                record
                for record in records
                if record.get("event") != correction_event and record.get("seq") not in correction_targets
            ],
            1,
        )
    ]
    return effective_records, errors


def replay_runtime(goal_dir: Path) -> tuple[dict[str, Any], list[str]]:
    plan = goal_dir / "plan.md"
    runtime_path = goal_dir / "runtime.jsonl"
    findings_path = goal_dir / "findings.jsonl"
    runtime = load_jsonl(runtime_path)
    findings = load_jsonl(findings_path)
    runtime, runtime_correction_errors = apply_corrections(runtime, "EVENT_CORRECTED", "runtime")
    findings, finding_correction_errors = apply_corrections(findings, "FINDING_CORRECTED", "findings")
    errors = runtime_correction_errors + finding_correction_errors
    errors += validate_sequence(runtime, runtime_path) + validate_sequence(findings, findings_path)
    state: dict[str, Any] = {
        "plan_version": 0,
        "plan_status": "UNREVIEWED",
        "current_milestone": None,
        "goal_status": "ACTIVE",
        "open_findings": {},
        "latest_review": None,
        "pending_user_decisions": [],
    }
    expected_hash = plan_hash(plan)
    latest_plan_event_seq = max(
        (record.get("seq", 0) for record in runtime if record.get("event") in {"PLAN_CREATED", "PLAN_AMENDED"}),
        default=0,
    )
    for record in runtime:
        event = record.get("event")
        if event not in VALID_EVENTS:
            errors.append(f"runtime seq {record.get('seq')}: unknown event {event!r}")
            continue
        if event in {"PLAN_CREATED", "PLAN_AMENDED"}:
            state["plan_version"] = record.get("plan_version")
            state["plan_status"] = "UNREVIEWED"
            if record.get("seq") == latest_plan_event_seq and record.get("plan_sha256") != expected_hash:
                errors.append(f"runtime seq {record['seq']}: plan hash does not match current plan.md")
        elif event == "PLAN_REVIEWED":
            if record.get("plan_version") != state["plan_version"]:
                errors.append(f"runtime seq {record['seq']}: review binds stale plan version")
            verdict = record.get("verdict")
            if verdict not in {"READY", "NOT_READY"}:
                errors.append(f"runtime seq {record['seq']}: invalid plan verdict")
            state["plan_status"] = verdict
            state["latest_review"] = record
        elif event == "MILESTONE_STARTED":
            if state["plan_status"] != "READY":
                errors.append(f"runtime seq {record['seq']}: milestone started before READY plan review")
            if state["current_milestone"] is not None:
                errors.append(f"runtime seq {record['seq']}: another milestone is already active")
            if state["pending_user_decisions"]:
                errors.append(
                    f"runtime seq {record['seq']}: milestone started while user decision pending:"
                    f" {', '.join(state['pending_user_decisions'])}"
                )
            state["current_milestone"] = record.get("milestone")
        elif event == "MILESTONE_COMPLETED":
            if record.get("milestone") != state["current_milestone"]:
                errors.append(f"runtime seq {record['seq']}: completed milestone is not active")
            state["current_milestone"] = None
        elif event in {"MILESTONE_REVIEWED", "REVIEW_COMPLETED", "ACCEPTANCE_COMPLETED"}:
            verdict = record.get("verdict")
            if verdict not in REVIEW_VERDICTS:
                errors.append(f"runtime seq {record['seq']}: invalid review verdict")
            if record.get("reviewer") == record.get("implementer"):
                errors.append(f"runtime seq {record['seq']}: implementer cannot self-review")
            if record.get("plan_version") != state["plan_version"]:
                if event != "MILESTONE_REVIEWED" or record.get("plan_version") is not None:
                    errors.append(f"runtime seq {record['seq']}: review binds stale plan version")
            state["latest_review"] = record
        elif event == "RISK_NOTICE_RECORDED":
            for field in ("risk", "mitigation", "target"):
                if not record.get(field):
                    errors.append(f"runtime seq {record['seq']}: risk notice missing {field}")
        elif event == "USER_DECISION_REQUESTED":
            decision_id = record.get("decision_id")
            legacy_request = "stop_category" not in record
            if legacy_request:
                # Ledgers created before Authorization Policy v2 remain replayable,
                # but new requests must use the narrow, structured stop schema.
                if record.get("authorization_policy_version") is not None:
                    errors.append(f"runtime seq {record['seq']}: missing stop_category")
            else:
                stop_category = record.get("stop_category")
                if stop_category not in STOP_CATEGORIES:
                    errors.append(f"runtime seq {record['seq']}: invalid stop_category {stop_category!r}")
                for field in ("target", "operation", "risk", "decision_needed"):
                    if not record.get(field):
                        errors.append(f"runtime seq {record['seq']}: user decision missing {field}")
            if not decision_id:
                errors.append(f"runtime seq {record['seq']}: missing decision_id")
            elif decision_id in state["pending_user_decisions"]:
                errors.append(f"runtime seq {record['seq']}: decision {decision_id!r} already pending")
            else:
                state["pending_user_decisions"].append(decision_id)
        elif event == "USER_DECISION_RECORDED":
            decision_id = record.get("decision_id")
            if decision_id in state["pending_user_decisions"]:
                state["pending_user_decisions"].remove(decision_id)
            else:
                errors.append(f"runtime seq {record['seq']}: no pending user decision {decision_id!r}")
        elif event == "GOAL_COMPLETED":
            if not state["latest_review"] or state["latest_review"].get("event") != "ACCEPTANCE_COMPLETED" or state["latest_review"].get("verdict") != "PASS":
                errors.append(f"runtime seq {record['seq']}: goal completed without passing independent acceptance")
            if state["pending_user_decisions"]:
                errors.append(
                    f"runtime seq {record['seq']}: goal completed while user decision pending:"
                    f" {', '.join(state['pending_user_decisions'])}"
                )
            state["goal_status"] = "COMPLETED"
        elif event == "IDENTITY_CONFIGURED":
            state["identity"] = {
                "agent": record.get("agent"),
                "repo": record.get("repo"),
                "hook": record.get("hook"),
                "allowlist": record.get("allowlist"),
            }
        elif event == "GOAL_BLOCKED":
            state["goal_status"] = "BLOCKED"
    for record in findings:
        event = record.get("event")
        if event not in VALID_FINDING_EVENTS:
            errors.append(f"findings seq {record.get('seq')}: unknown event {event!r}")
            continue
        finding_id = record.get("finding_id")
        if not finding_id:
            errors.append(f"findings seq {record['seq']}: missing finding_id")
            continue
        current = state["open_findings"].setdefault(finding_id, {"status": "OPEN", "review_fix_rounds": 0})
        if event == "FINDING_CLASSIFIED":
            classification = record.get("classification")
            if classification not in FINDING_CLASSES:
                errors.append(f"findings seq {record['seq']}: invalid classification")
            current["classification"] = classification
        elif event == "FINDING_FIX_PROPOSED":
            current["review_fix_rounds"] += 1
        elif event == "FINDING_CLOSED":
            current["status"] = "CLOSED"
        elif event == "FINDING_REOPENED":
            current["status"] = "OPEN"
    # A Goal that declared agent identity must still have the guard installed;
    # a missing or gutted hook is exactly the drift this event exists to catch.
    identity = state.get("identity")
    if identity:
        hook = Path(identity["hook"]) if identity.get("hook") else None
        if hook is None or not hook.is_file():
            errors.append(f"identity: guard hook missing at {identity.get('hook')!r}; rerun setup-identity")
        elif "goal-plan identity guard" not in hook.read_text(encoding="utf-8"):
            errors.append(f"identity: {hook} is not the goal-plan identity guard; rerun setup-identity")
        allowlist = identity.get("allowlist")
        if not allowlist or not Path(allowlist).is_file():
            errors.append(f"identity: allowlist missing at {allowlist!r}; rerun setup-identity")
    for finding_id, finding in state["open_findings"].items():
        if "classification" not in finding:
            errors.append(f"finding {finding_id}: open finding is unclassified")
        if finding["status"] == "OPEN" and finding["review_fix_rounds"] >= 2:
            errors.append(f"finding {finding_id}: convergence review required before a third fix round")
        if (
            finding["status"] == "OPEN"
            and finding.get("classification") in {"CONTRADICTION", "AC_CHANGE"}
            and state["plan_status"] == "READY"
        ):
            errors.append(f"finding {finding_id}: plan must return to review before implementation continues")
    return state, errors


def runtime_template_dir() -> Path:
    return Path(__file__).resolve().parent / "templates"


def init_goal(args: argparse.Namespace) -> int:
    goal_dir = Path(args.goal_dir).resolve()
    if goal_dir.exists() and any(goal_dir.iterdir()):
        raise ValueError(f"goal directory is not empty: {goal_dir}")
    goal_dir.mkdir(parents=True, exist_ok=True)
    templates = runtime_template_dir()
    plan_text = Template((templates / "plan.md").read_text(encoding="utf-8")).safe_substitute(
        goal_title=args.title,
        goal_id=goal_dir.name,
    )
    (goal_dir / "plan.md").write_text(plan_text, encoding="utf-8")
    (goal_dir / "runtime.jsonl").touch()
    (goal_dir / "findings.jsonl").touch()
    (goal_dir / "acceptance.md").write_text((templates / "acceptance.md").read_text(encoding="utf-8"), encoding="utf-8")
    (goal_dir / "reviews").mkdir()
    append_jsonl(
        goal_dir / "runtime.jsonl",
        {
            "event": "PLAN_CREATED",
            "actor": args.actor,
            "plan_version": 1,
            "plan_sha256": plan_hash(goal_dir / "plan.md"),
        },
    )
    print(goal_dir)
    return 0


def setup_identity(args: argparse.Namespace) -> int:
    repo_dir = Path(args.repo_dir).resolve()
    name, email = AGENT_IDENTITIES[args.agent]
    # Hooks resolve through core.hooksPath when set; writing .git/hooks there would be inert.
    hooks_config = subprocess.run(
        ["git", "-C", str(repo_dir), "config", "core.hooksPath"],
        capture_output=True,
        text=True,
    )
    if hooks_config.returncode == 0 and hooks_config.stdout.strip():
        hooks_dir = Path(hooks_config.stdout.strip())
    else:
        git_path_raw = subprocess.run(
            ["git", "-C", str(repo_dir), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
        )
        if git_path_raw.returncode != 0:
            raise ValueError(f"not a git repository: {repo_dir}\n{git_path_raw.stderr.strip()}")
        hooks_dir = Path(git_path_raw.stdout.strip())
    if not hooks_dir.is_absolute():
        hooks_dir = repo_dir / hooks_dir
    hook_path = hooks_dir / "pre-commit"
    if hook_path.exists() and "goal-plan identity guard" not in hook_path.read_text(encoding="utf-8"):
        raise ValueError(
            f"refusing to overwrite an existing unrelated pre-commit hook: {hook_path}\n"
            "chain the identity guard from that hook manually, or run setup-identity in an isolated worktree"
        )
    for key, value in (("user.name", name), ("user.email", email)):
        subprocess.run(["git", "-C", str(repo_dir), "config", key, value], check=True)
    hooks_dir.mkdir(parents=True, exist_ok=True)
    allow_path = hooks_dir / "goal-allowed-emails.txt"
    allow_path.write_text("".join(f"{e}\n" for _, e in AGENT_IDENTITIES.values()), encoding="utf-8")
    hook_path.write_text(IDENTITY_HOOK, encoding="utf-8")
    hook_path.chmod(hook_path.stat().st_mode | 0o755)
    if args.goal_dir:
        append_jsonl(
            Path(args.goal_dir).resolve() / "runtime.jsonl",
            {
                "event": "IDENTITY_CONFIGURED",
                "agent": args.agent,
                "repo": str(repo_dir),
                "hook": str(hook_path),
                "allowlist": str(allow_path),
            },
        )
    print(f"identity: {name} <{email}>")
    print(f"guard: {hook_path}")
    return 0


def append_event(args: argparse.Namespace) -> int:
    goal_dir = Path(args.goal_dir).resolve()
    payload = json.loads(args.data) if args.data else {}
    if not isinstance(payload, dict):
        raise ValueError("--data must be a JSON object")
    payload["event"] = args.event
    if args.ledger != "findings" and args.event in {"PLAN_CREATED", "PLAN_AMENDED"}:
        payload.setdefault("plan_sha256", plan_hash(goal_dir / "plan.md"))
    path = goal_dir / ("findings.jsonl" if args.ledger == "findings" else "runtime.jsonl")
    print(canonical_json(append_jsonl(path, payload)))
    return 0


def build_reviewer_prompt(args: argparse.Namespace) -> int:
    goal_dir = Path(args.goal_dir).resolve()
    state, errors = replay_runtime(goal_dir)
    convergence_only = args.review_type == "Convergence Review" and all(
        error.endswith("convergence review required before a third fix round") for error in errors
    )
    plan_reentry_only = args.review_type == "Plan Re-entry Review" and all(
        error.endswith("plan must return to review before implementation continues") for error in errors
    )
    if errors and not convergence_only and not plan_reentry_only:
        raise ValueError("runtime validation failed:\n- " + "\n- ".join(errors))
    template = (runtime_template_dir() / "reviewer_prompt.md").read_text(encoding="utf-8")
    focus = Path(args.focus_file).read_text(encoding="utf-8") if args.focus_file else args.focus
    values = {
        "review_type": args.review_type,
        "goal_dir": str(goal_dir),
        "plan_version": state["plan_version"],
        "milestone": args.milestone or state["current_milestone"] or "none",
        "base_commit": args.base_commit or "not supplied",
        "candidate_commit": args.candidate_commit or "not supplied",
        "applicable_acs": args.applicable_acs or "read from the Goal reviewer contract",
        "verification_commands": args.verification_commands or "read from the applicable ACs",
        "additional_focus": focus or "none",
    }
    prompt = Template(template).safe_substitute(values)
    if args.output:
        Path(args.output).write_text(prompt, encoding="utf-8")
    else:
        print(prompt)
    return 0


def print_validation(errors: list[str], state: dict[str, Any] | None = None) -> int:
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    if state is not None:
        print(json.dumps(state, indent=2, sort_keys=True))
    else:
        print("PASS")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="goal-plan-runtime")
    commands = root.add_subparsers(dest="command", required=True)
    init = commands.add_parser("init")
    init.add_argument("goal_dir")
    init.add_argument("--title", required=True)
    init.add_argument("--actor", default="main-agent")
    init.set_defaults(func=init_goal)
    plan = commands.add_parser("validate-plan")
    plan.add_argument("goal_dir")
    plan.set_defaults(func=lambda a: print_validation(validate_plan(Path(a.goal_dir) / "plan.md")))
    identity = commands.add_parser("setup-identity")
    identity.add_argument("repo_dir")
    identity.add_argument("--agent", required=True, choices=sorted(AGENT_IDENTITIES))
    identity.add_argument(
        "--goal-dir",
        help="append IDENTITY_CONFIGURED to this goal's runtime ledger so validate-runtime keeps checking the guard",
    )
    identity.set_defaults(func=setup_identity)
    append = commands.add_parser("append-event")
    append.add_argument("goal_dir")
    append.add_argument("event")
    append.add_argument("--ledger", choices=("runtime", "findings"), default="runtime")
    append.add_argument("--data", default="{}")
    append.set_defaults(func=append_event)
    runtime = commands.add_parser("validate-runtime")
    runtime.add_argument("goal_dir")
    runtime.set_defaults(func=lambda a: (lambda result: print_validation(result[1], result[0]))(replay_runtime(Path(a.goal_dir))))
    reviewer = commands.add_parser("build-reviewer-prompt")
    reviewer.add_argument("goal_dir")
    reviewer.add_argument("--review-type", required=True)
    reviewer.add_argument("--milestone")
    reviewer.add_argument("--base-commit")
    reviewer.add_argument("--candidate-commit")
    reviewer.add_argument("--applicable-acs")
    reviewer.add_argument("--verification-commands")
    reviewer.add_argument("--focus", default="")
    reviewer.add_argument("--focus-file")
    reviewer.add_argument("--output")
    reviewer.set_defaults(func=build_reviewer_prompt)
    return root


def main() -> None:
    args = parser().parse_args()
    try:
        raise SystemExit(args.func(args))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
