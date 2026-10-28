"""Aggregate per-question grades into stage/subject/type scores and a weighted total."""
from __future__ import annotations

from .loader import STAGE_ORDER
from .taxonomy import CAPABILITIES, DIFFICULTIES
from .profiles import resolve_profile

GRADE_BANDS = [
    (90, "A", "优秀"),
    (80, "B", "良好"),
    (70, "C", "中等"),
    (60, "D", "及格"),
    (0, "F", "不及格"),
]


def _band(percent: float) -> dict:
    for threshold, letter, label in GRADE_BANDS:
        if percent >= threshold:
            return {"letter": letter, "label": label}
    return {"letter": "F", "label": "不及格"}


def _agg(records: list[dict]) -> dict:
    earned = 0.0
    graded_total = 0.0
    ungraded = 0
    n = len(records)
    for r in records:
        g = r.get("grading") or {}
        score = g.get("score")
        if score is None:
            ungraded += 1
            continue
        earned += float(score)
        graded_total += float(g.get("max", r.get("points", 0)))
    rate = (earned / graded_total) if graded_total > 0 else 0.0
    return {
        "n": n,
        "graded_n": n - ungraded,
        "ungraded_n": ungraded,
        "earned": round(earned, 2),
        "graded_total": round(graded_total, 2),
        "rate": round(rate, 4),
        "percent": round(rate * 100, 2),
        "coverage": round((n - ungraded) / n, 4) if n else 0.0,
    }


def resolve_weights(config: dict, present_stages: list[str]) -> dict:
    """Return {stage_id: weight} normalized over the stages that are present."""
    weights_cfg = config.get("weights", {})
    presets = weights_cfg.get("presets", {})
    preset_name = weights_cfg.get("preset", "balanced")
    preset = presets.get(preset_name, {})
    table = {}
    for sid in present_stages:
        table[sid] = float(preset.get(sid, 1.0))
    return table


def aggregate(results: list[dict], config: dict) -> dict:
    by_stage: dict[str, list[dict]] = {}
    for r in results:
        by_stage.setdefault(r["stage"], []).append(r)

    present = [s for s in STAGE_ORDER if s in by_stage]
    # keep any custom stages that are not in the built-in order
    for s in by_stage:
        if s not in present:
            present.append(s)
    weights = resolve_weights(config, present)

    stages = []
    for sid in present:
        recs = by_stage[sid]
        agg = _agg(recs)
        agg["id"] = sid
        agg["name"] = recs[0].get("stage_name", sid)
        agg["track"] = recs[0].get("track", "education")
        agg["weight"] = weights.get(sid, 1.0)
        stages.append(agg)

    # role-weighted interview score (configurable per-job weights)
    role_weights = (config.get("weights") or {}).get("roles") or {}
    for stage in stages:
        if stage["id"] != "interview" or not role_weights:
            continue
        role_buckets: dict[str, list[dict]] = {}
        for r in by_stage["interview"]:
            role_buckets.setdefault(r.get("role") or "其他", []).append(r)
        num = 0.0
        den = 0.0
        for role, rs in role_buckets.items():
            a = _agg(rs)
            w = float(role_weights.get(role, 1.0))
            num += a["rate"] * w
            den += w
        if den > 0:
            stage["rate"] = round(num / den, 4)
            stage["percent"] = round(num / den * 100, 2)
            stage["role_weighted"] = True

    # subject breakdown (per stage)
    subjects = []
    for sid in present:
        recs = by_stage[sid]
        buckets: dict[str, list[dict]] = {}
        for r in recs:
            buckets.setdefault(r.get("subject", "综合"), []).append(r)
        for subj, rs in buckets.items():
            a = _agg(rs)
            a["stage"] = sid
            a["subject"] = subj
            subjects.append(a)

    # topic breakdown (per stage, fine-grained knowledge point)
    topics = []
    for sid in present:
        recs = by_stage[sid]
        buckets: dict[str, list[dict]] = {}
        for r in recs:
            t = r.get("topic") or r.get("subject") or "综合"
            buckets.setdefault(t, []).append(r)
        for t, rs in buckets.items():
            a = _agg(rs)
            a["stage"] = sid
            a["topic"] = t
            topics.append(a)

    # type breakdown (per stage)
    types = []
    for sid in present:
        recs = by_stage[sid]
        buckets: dict[str, list[dict]] = {}
        for r in recs:
            buckets.setdefault(r["type"], []).append(r)
        for t, rs in buckets.items():
            a = _agg(rs)
            a["stage"] = sid
            a["type"] = t
            types.append(a)

    # interview round breakdown (per stage, only questions with a `round`)
    rounds = []
    for sid in present:
        recs = by_stage[sid]
        buckets: dict[str, list[dict]] = {}
        for r in recs:
            if r.get("round"):
                buckets.setdefault(r["round"], []).append(r)
        for rnd, rs in buckets.items():
            a = _agg(rs)
            a["stage"] = sid
            a["round"] = rnd
            rounds.append(a)

    # interview role breakdown (per stage, only questions with a `role`)
    roles = []
    for sid in present:
        recs = by_stage[sid]
        buckets: dict[str, list[dict]] = {}
        for r in recs:
            if r.get("role"):
                buckets.setdefault(r["role"], []).append(r)
        for role, rs in buckets.items():
            a = _agg(rs)
            a["stage"] = sid
            a["role"] = role
            roles.append(a)

    # interview level breakdown (per stage, only questions with a `level`)
    levels = []
    for sid in present:
        recs = by_stage[sid]
        buckets: dict[str, list[dict]] = {}
        for r in recs:
            if r.get("level"):
                buckets.setdefault(r["level"], []).append(r)
        for lvl, rs in buckets.items():
            a = _agg(rs)
            a["stage"] = sid
            a["level"] = lvl
            levels.append(a)

    # capability profile (a question may map to several capabilities)
    cap_buckets: dict[str, list[dict]] = {}
    for r in results:
        for c in (r.get("capabilities") or ["知识"]):
            cap_buckets.setdefault(c, []).append(r)
    capabilities = []
    for c in CAPABILITIES:
        if c in cap_buckets:
            a = _agg(cap_buckets[c])
            a["capability"] = c
            capabilities.append(a)
    for c, rs in cap_buckets.items():
        if c not in CAPABILITIES:
            a = _agg(rs)
            a["capability"] = c
            capabilities.append(a)

    # difficulty breakdown
    diff_buckets: dict[str, list[dict]] = {}
    for r in results:
        diff_buckets.setdefault(r.get("difficulty", "medium"), []).append(r)
    difficulties = []
    for d in DIFFICULTIES:
        if d in diff_buckets:
            a = _agg(diff_buckets[d])
            a["difficulty"] = d
            difficulties.append(a)

    # judge metadata (for reliability warnings in the UI)
    judge_info: dict = {}
    for r in results:
        d = (r.get("grading") or {}).get("detail") or {}
        if "judge_model" in d:
            judge_info = {
                "model": d.get("judge_model"),
                "self_judge": bool(d.get("self_judge")),
                "debias": bool(d.get("debias")),
            }
            break

    # profile (job x level) context: weighted stage/capability/role scores
    profile_block = None
    profile_cfg = config.get("profile") or {}
    if profile_cfg.get("id"):
        try:
            spec = resolve_profile(profile_cfg["id"], profile_cfg.get("level") or "中级")
        except ValueError:
            spec = None
        if spec:
            stage_map = {s["id"]: s for s in stages}
            present_stages = [sid for sid in spec["stages"] if sid in stage_map]
            sw = sum(spec["stages"][sid] for sid in present_stages) or 1.0
            stage_score = sum(stage_map[sid]["rate"] * spec["stages"][sid]
                              for sid in present_stages) / sw

            cap_map = {c["capability"]: c["rate"] for c in capabilities}
            cap_present = [c for c in spec["capabilities"] if c in cap_map]
            cap_den = sum(spec["capabilities"][c] for c in cap_present) or 1.0
            cap_score = (sum(cap_map[c] * spec["capabilities"][c] for c in cap_present) / cap_den
                         if cap_present else None)

            role_map = {r["role"]: r["rate"] for r in roles}
            role_present = [r for r in spec["roles"] if r in role_map]
            role_den = sum(spec["roles"][r] for r in role_present) or 1.0
            role_score = (sum(role_map[r] * spec["roles"][r] for r in role_present) / role_den
                          if role_present else None)

            profile_block = {
                "id": spec["id"], "name": spec["name"], "level": spec["level"],
                "score": round(stage_score * 100, 2),
                "stage_score": round(stage_score * 100, 2),
                "capability_score": round(cap_score * 100, 2) if cap_score is not None else None,
                "role_score": round(role_score * 100, 2) if role_score is not None else None,
                "stage_weights": spec["stages"],
                "present_stages": present_stages,
                "subjects": spec["subjects"],
                "note": spec["note"],
            }

    overall = _agg(results)

    # low-sample markers: a section judged by a single question is not reliable
    for s in stages:
        s["low_sample"] = s["graded_n"] < 3
    for a in subjects:
        a["low_sample"] = a["graded_n"] < 2
    for a in roles:
        a["low_sample"] = a["graded_n"] < 2

    # weighted rate across stages (equal stage coverage within each stage's own points)
    wsum = sum(weights.get(s["id"], 1.0) for s in stages) or 1.0
    weighted_rate = sum(s["rate"] * weights.get(s["id"], 1.0) for s in stages) / wsum
    weighted_percent = round(weighted_rate * 100, 2)

    return {
        "overall": {**overall, "weighted_percent": weighted_percent,
                    "grade": _band(weighted_percent)},
        "stages": stages,
        "subjects": subjects,
        "topics": topics,
        "types": types,
        "rounds": rounds,
        "roles": roles,
        "levels": levels,
        "capabilities": capabilities,
        "difficulties": difficulties,
        "profile": profile_block,
        "judge": judge_info,
        "weights": {"preset": config.get("weights", {}).get("preset", "balanced"),
                    "table": weights},
        "questions": [
            {
                "id": r["id"], "stage": r["stage"], "subject": r.get("subject"),
                "type": r["type"], "capabilities": r.get("capabilities", []),
                "tags": r.get("tags", []),
                "difficulty": r.get("difficulty"),
                "points": r["points"],
                "score": (r.get("grading") or {}).get("score"),
                "correct": (r.get("grading") or {}).get("correct"),
                "error": r.get("error"),
            }
            for r in results
        ],
    }
