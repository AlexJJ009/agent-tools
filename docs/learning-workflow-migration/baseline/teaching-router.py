#!/usr/bin/env python3
"""Deterministic teaching-skill router."""

from __future__ import annotations

from typing import Any


READ_PAPER_MATERIAL = ("下载", "pdf", "原文在哪", "哪一页", "citation", "cite", "引用")
PAPER_SIGNALS = ("论文", "paper", "zotero", "pdf", "rpucg", "openevolve", "精读")
PAPER_EVIDENCE_SIGNALS = ("论文", "paper", "zotero", "pdf", "原文", "文章", "文中", "作者")
TEACHING_SIGNALS = (
    "先精读",
    "讲透",
    "精读",
    "读这篇",
    "teach me",
    "deeply understand",
    "真正理解",
)
ARTIFACT_SIGNALS = (
    "写成博客",
    "写一篇博客",
    "完整博客",
    "完整综述",
    "综述正文",
    "完整学习材料",
    "独立学习材料",
    "教程",
    "tutorial",
    "standalone",
    "artifact",
)
DAG_TEACHING_SIGNALS = (
    *TEACHING_SIGNALS,
    "讲清",
    "讲解",
    "解释",
    "一小段教学",
    "教学单元",
    "我想理解",
    "帮我理解",
    "来龙去脉",
    *ARTIFACT_SIGNALS,
)


def _has(text: str, *needles: str) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def _route(owner: str, mode: str, delegates: tuple[str, ...] = (), adapter: str | None = None) -> dict[str, Any]:
    result: dict[str, Any] = {"owner": owner, "mode": mode}
    if delegates:
        result["delegates"] = delegates
    if adapter:
        result["adapter"] = adapter
    return result


def route_request(prompt: str) -> dict[str, Any]:
    text = prompt.lower()

    if _has(text, "citation", "cite", "给我这篇论文的 citation"):
        return _route("read-paper", "metadata")
    if _has(text, "下载") and _has(text, "论文", "pdf"):
        return _route("read-paper", "material")
    if _has(text, "原文在哪", "哪一页报告") or (
        _has(text, "在哪一页") and _has(text, *PAPER_EVIDENCE_SIGNALS)
    ):
        return _route("read-paper", "evidence-audit")

    if _has(text, "dictionary definition", "definition of"):
        return _route("none", "definition")

    base_delegates = ("teaching-dag-builder", "evidence-anchor", "retrieval-practice")
    adapter = "read-paper" if _has(text, *PAPER_SIGNALS) else None

    if _has(text, "compile these", "compile verified"):
        return _route("learning-artifact-compiler", "compile")

    dag_requested = _has(
        text,
        "build a knowledge prerequisite dag",
        "prerequisite dag",
        "current frontier",
        "kc map",
        "概念 dag",
        "知识 dag",
        "当前 frontier",
        "前置知识图",
    )
    dag_only = dag_requested and not _has(text, *DAG_TEACHING_SIGNALS)
    if dag_only:
        return _route("teaching-dag-builder", "dag")
    if _has(
        text,
        "anchor this",
        "exact lines",
        "immutable commit",
        "evidence anchor",
        "锚定",
        "论文页码",
        "代码行",
        "证据 anchor",
    ):
        return _route("evidence-anchor", "anchor")
    if _has(text, "retrieval", "transfer exercise", "interleaved"):
        return _route("retrieval-practice", "practice")

    if _has(text, "审计", "audit") and _has(text, "post-hoc", "rationalization", "是不是"):
        return _route("teaching-reconstruction", "reconstruction-audit", ("evidence-anchor",), adapter)

    if _has(text, "比较") and _has(text, "来龙去脉", "理解"):
        return _route("teaching-reconstruction", "survey-as-learning", base_delegates, adapter)

    if _has(text, "直接讲", "不要问我"):
        return _route("teaching-reconstruction", "guided-direct", base_delegates, adapter)

    if _has(text, *TEACHING_SIGNALS) or (
        dag_requested and _has(text, *DAG_TEACHING_SIGNALS)
    ):
        delegates = base_delegates
        if _has(text, *ARTIFACT_SIGNALS):
            delegates = (*base_delegates, "learning-artifact-compiler")
        return _route("teaching-reconstruction", "guided", delegates, adapter)

    if _has(text, "写成", "博客", "tutorial", "learning material", "standalone"):
        return _route(
            "teaching-reconstruction",
            "artifact",
            (*base_delegates, "learning-artifact-compiler"),
            adapter,
        )

    if _has(text, "按源码讲", "source code", "code walkthrough"):
        return _route("teaching-reconstruction", "paper-code", base_delegates, adapter)

    if _has(text, "一道题", "三道题", "练习题", "题检查", "检查我是否", "确认我真的懂", "check", "quiz"):
        return _route("teaching-reconstruction", "check-only", ("retrieval-practice",), adapter)

    return _route("none", "unmatched")


if __name__ == "__main__":
    import json
    import sys

    print(json.dumps(route_request(" ".join(sys.argv[1:])), ensure_ascii=False, sort_keys=True))
