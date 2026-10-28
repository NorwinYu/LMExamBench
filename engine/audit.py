"""Question-bank auditing: near-duplicate detection and coverage matrix.

This is a *within-bank* duplicate/near-duplicate check (a practical
contamination/overlap guard). It cannot detect training-data contamination
of third-party corpora, which would require the corpus itself.
"""
from __future__ import annotations

import re
from itertools import combinations


def _norm(text: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]", "", str(text).lower())


def _shingles(text: str, n: int = 3) -> set[str]:
    s = _norm(text)
    if not s:
        return set()
    if len(s) <= n:
        return {s}
    return {s[i:i + n] for i in range(len(s) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def find_near_duplicates(questions: list[dict], threshold: float = 0.85) -> list[dict]:
    sh = [(q["id"], _shingles(q["question"])) for q in questions]
    out = []
    for (ida, sa), (idb, sb) in combinations(sh, 2):
        sim = jaccard(sa, sb)
        if sim >= threshold:
            out.append({"a": ida, "b": idb, "similarity": round(sim, 4)})
    out.sort(key=lambda x: -x["similarity"])
    return out


def capability_coverage(questions: list[dict]) -> dict:
    """stage -> capability -> question count."""
    table: dict = {}
    for q in questions:
        row = table.setdefault(q["stage"], {})
        for c in (q.get("capabilities") or ["知识"]):
            row[c] = row.get(c, 0) + 1
    return table


def flow_coverage(questions: list[dict], flows: dict) -> dict:
    """For each level, count questions per expected round and list missing rounds."""
    out = {}
    for level, rounds in (flows or {}).items():
        counts = {}
        for rnd in rounds:
            counts[rnd] = sum(1 for q in questions
                              if q.get("level") == level and q.get("round") == rnd)
        out[level] = {
            "expected": list(rounds),
            "counts": counts,
            "missing": [r for r in rounds if counts.get(r, 0) == 0],
        }
    return out


def audit_questions(questions: list[dict], threshold: float = 0.85,
                    flows: dict | None = None) -> dict:
    dups = find_near_duplicates(questions, threshold)
    result = {
        "total": len(questions),
        "threshold": threshold,
        "duplicate_count": len(dups),
        "duplicates": dups,
        "coverage": capability_coverage(questions),
    }
    if flows is not None:
        result["flows"] = flow_coverage(questions, flows)
    return result
