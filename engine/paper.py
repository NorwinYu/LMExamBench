"""Build an exam-style paper: several questions per (stage, subject/role).

`--sample N` picks N per *stage*, which lets one question decide a subject.
Paper mode picks up to N per *section* (subject for education, role for
interview), so every section is measured by multiple questions where the bank
allows it.
"""
from __future__ import annotations

import random
from collections import defaultdict

from .loader import STAGE_ORDER

_STAGE_ORDER = {s: i for i, s in enumerate(STAGE_ORDER)}


def section_key(q: dict) -> str:
    if q.get("stage") == "interview":
        return q.get("role") or "其他"
    return q.get("subject") or "综合"


def build_paper(questions: list[dict], per_section: int = 2, seed=None) -> list[dict]:
    """Return up to `per_section` questions for every stage/section."""
    rng = random.Random(seed)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for q in questions:
        groups[(q["stage"], section_key(q))].append(q)
    picked: list[dict] = []
    for pool in groups.values():
        picked.extend(rng.sample(pool, min(per_section, len(pool))))
    picked.sort(key=lambda q: (_STAGE_ORDER.get(q["stage"], 99),
                               q.get("subject") or q.get("role") or "",
                               q["id"]))
    return picked


def paper_structure(questions: list[dict]) -> list[dict]:
    """Section metadata for the UI/PDF: stage, section, count, total points."""
    groups: dict[tuple[str, str], dict] = {}
    for q in questions:
        key = (q["stage"], section_key(q))
        slot = groups.setdefault(key, {"stage": q["stage"], "section": key[1],
                                       "count": 0, "points": 0.0})
        slot["count"] += 1
        slot["points"] += float(q.get("points", 0))
    return sorted(groups.values(),
                  key=lambda s: (_STAGE_ORDER.get(s["stage"], 99), s["section"]))
