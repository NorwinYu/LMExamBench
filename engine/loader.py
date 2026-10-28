"""Load the layered exam bank from JSON files."""
from __future__ import annotations

import json
import os
import random

from .taxonomy import (  # noqa: F401  (re-exported for convenience)
    CAPABILITIES, DIFFICULTIES, QUESTION_TYPES, DEFAULT_CAPABILITY,
)

# Ordered stage definitions. `id` is used in configs/weights, `name` is displayed.
STAGES = [
    {"id": "primary", "name": "小学", "track": "education"},
    {"id": "junior", "name": "初中", "track": "education"},
    {"id": "senior", "name": "高中", "track": "education"},
    {"id": "undergrad", "name": "大学", "track": "education"},
    {"id": "master", "name": "硕士", "track": "education"},
    {"id": "ruankao", "name": "软考", "track": "engineer"},
    {"id": "interview", "name": "大厂面试", "track": "engineer"},
    {"id": "leetcode", "name": "LeetCode", "track": "engineer"},
]

STAGE_BY_ID = {s["id"]: s for s in STAGES}
STAGE_ORDER = [s["id"] for s in STAGES]

REQUIRED_KEYS = ("id", "question", "type", "points")


def validate_question(q: dict, source: str) -> None:
    missing = [k for k in REQUIRED_KEYS if k not in q]
    if missing:
        raise ValueError(f"{source}: question {q.get('id', '?')} missing {missing}")
    if q["type"] not in QUESTION_TYPES:
        raise ValueError(f"{source}: question {q['id']} has unknown type {q['type']}")
    if q["type"] in ("choice", "multi") and not q.get("options"):
        raise ValueError(f"{source}: {q['type']} question {q['id']} needs options")
    if q["type"] == "code" and not q.get("test_cases"):
        raise ValueError(f"{source}: code question {q['id']} needs test_cases")
    if q.get("hidden_cases") is not None and not isinstance(q["hidden_cases"], list):
        raise ValueError(f"{source}: question {q['id']} hidden_cases must be a list")
    if q.get("round") is not None and not isinstance(q["round"], str):
        raise ValueError(f"{source}: question {q['id']} round must be a string")
    if q.get("role") is not None and not isinstance(q["role"], str):
        raise ValueError(f"{source}: question {q['id']} role must be a string")
    if q.get("level") is not None and not isinstance(q["level"], str):
        raise ValueError(f"{source}: question {q['id']} level must be a string")
    for key in ("format", "source_style", "chapter", "topic"):
        if q.get(key) is not None and not isinstance(q[key], str):
            raise ValueError(f"{source}: question {q['id']} {key} must be a string")
    if (q.get("time_limit_min") is not None
            and not isinstance(q["time_limit_min"], (int, float))):
        raise ValueError(f"{source}: question {q['id']} time_limit_min must be a number")
    if q["type"] == "multi" and not isinstance(q.get("answer"), (list, str)):
        raise ValueError(f"{source}: multi question {q['id']} needs answer list/string")
    # controlled vocab
    if q.get("difficulty") and q["difficulty"] not in DIFFICULTIES:
        raise ValueError(
            f"{source}: question {q['id']} bad difficulty {q['difficulty']!r} "
            f"(allowed: {list(DIFFICULTIES)})")
    caps = q.get("capabilities")
    if caps is not None:
        if not isinstance(caps, list):
            raise ValueError(f"{source}: question {q['id']} capabilities must be a list")
        bad = [c for c in caps if c not in CAPABILITIES]
        if bad:
            raise ValueError(
                f"{source}: question {q['id']} unknown capabilities {bad} "
                f"(allowed: {CAPABILITIES})")
    if q.get("tags") is not None and not isinstance(q["tags"], list):
        raise ValueError(f"{source}: question {q['id']} tags must be a list")


def load_bank(bank_dir: str) -> list[dict]:
    """Return a flat, stage-annotated list of questions."""
    questions: list[dict] = []
    seen = set()
    for stage in STAGES:
        path = os.path.join(bank_dir, f"{stage['id']}.json")
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        items = data.get("questions", data if isinstance(data, list) else [])
        for q in items:
            validate_question(q, path)
            if q["id"] in seen:
                raise ValueError(f"duplicate question id {q['id']} in {path}")
            seen.add(q["id"])
            q = dict(q)
            q.setdefault("stage", stage["id"])
            q.setdefault("stage_name", stage["name"])
            q.setdefault("subject", "综合")
            q.setdefault("difficulty", "medium")
            q.setdefault("capabilities", [DEFAULT_CAPABILITY])
            q.setdefault("tags", [])
            questions.append(q)
    return questions


def bank_summary(questions: list[dict]) -> list[dict]:
    """Per-stage counts for the UI."""
    counts: dict[str, int] = {}
    for q in questions:
        counts[q["stage"]] = counts.get(q["stage"], 0) + 1
    out = []
    for stage in STAGES:
        n = counts.get(stage["id"], 0)
        if n:
            out.append({**stage, "count": n})
    return out


def load_flows(bank_dir: str) -> dict:
    """Interview flow metadata: level -> ordered rounds (from interview.json)."""
    path = os.path.join(bank_dir, "interview.json")
    if not os.path.isfile(path):
        return {}
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    return data.get("flows") or {}


def sample_questions(questions: list[dict], per_stage: int = 0, seed=None) -> list[dict]:
    """Randomly draw up to `per_stage` questions from each stage (seeded)."""
    if not per_stage or per_stage <= 0:
        return list(questions)
    rng = random.Random(seed)
    by_stage: dict[str, list[dict]] = {}
    for q in questions:
        by_stage.setdefault(q["stage"], []).append(q)
    out: list[dict] = []
    for sid in STAGE_ORDER:
        pool = by_stage.get(sid)
        if pool:
            out.extend(rng.sample(pool, min(per_stage, len(pool))))
    for sid, pool in by_stage.items():
        if sid not in STAGE_ORDER:
            out.extend(rng.sample(pool, min(per_stage, len(pool))))
    return out
