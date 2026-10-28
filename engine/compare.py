"""Multi-run comparison and cross-model item statistics.

Discrimination (item-rest correlation) and empirical difficulty (p-value) need
several respondents, i.e. several runs/models. With fewer than 3 runs the
discrimination is reported as unavailable rather than guessed.
"""
from __future__ import annotations

MIN_RUNS_FOR_DISCRIMINATION = 3


def _pearson(xs: list[float], ys: list[float]) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs) ** 0.5
    dy = sum((y - my) ** 2 for y in ys) ** 0.5
    if dx == 0 or dy == 0:
        return None
    return num / (dx * dy)


def _fraction(result: dict):
    g = result.get("grading") or {}
    f = g.get("fraction")
    if isinstance(f, (int, float)) and not isinstance(f, bool):
        return float(f)
    return None


def item_statistics(records: list[dict]) -> dict:
    """Compute per-question p-value and discrimination across run records."""
    items: dict[str, dict] = {}
    run_totals: dict[str, float] = {}
    for rec in records:
        rid = rec.get("id")
        total = 0.0
        for res in rec.get("results") or []:
            f = _fraction(res)
            if f is None:
                continue
            total += f
            qid = res.get("id")
            slot = items.setdefault(qid, {
                "id": qid,
                "stage": res.get("stage"),
                "subject": res.get("subject"),
                "type": res.get("type"),
                "difficulty": res.get("difficulty"),
                "capabilities": res.get("capabilities") or [],
                "tags": res.get("tags") or [],
                "scores": {},
            })
            slot["scores"][rid] = f
        run_totals[rid] = total

    rows = []
    for slot in items.values():
        scores = slot.pop("scores")
        vals = list(scores.values())
        n = len(vals)
        p = (sum(vals) / n) if n else None
        disc = None
        if n >= MIN_RUNS_FOR_DISCRIMINATION:
            xs = list(scores.values())
            ys = [run_totals[rid] - f for rid, f in scores.items()]
            disc = _pearson(xs, ys)

        flags = []
        if n < MIN_RUNS_FOR_DISCRIMINATION:
            flags.append("样本不足")
        if disc is not None and disc < 0.2:
            flags.append("低区分度")
        if p is not None and p >= 0.95:
            flags.append("过易")
        if p is not None and p <= 0.05:
            flags.append("过难")
        rows.append({
            **slot,
            "n_runs": n,
            "p_value": round(p, 4) if p is not None else None,
            "discrimination": round(disc, 4) if disc is not None else None,
            "flags": flags,
        })

    # declared difficulty vs empirical difficulty (calibration)
    groups: dict[str, dict] = {}
    for row in rows:
        d = row.get("difficulty") or "medium"
        g = groups.setdefault(d, {"n": 0, "sum_p": 0.0})
        if row["p_value"] is not None:
            g["n"] += 1
            g["sum_p"] += row["p_value"]
    calibration = {
        d: {"n": g["n"], "mean_p": round(g["sum_p"] / g["n"], 4) if g["n"] else None}
        for d, g in groups.items()
    }

    def sort_key(row):
        disc = row["discrimination"]
        return (disc is None, disc if disc is not None else 0.0)

    return {
        "runs": [r.get("id") for r in records],
        "min_runs_for_discrimination": MIN_RUNS_FOR_DISCRIMINATION,
        "items": sorted(rows, key=sort_key),
        "calibration": calibration,
        "low_discrimination": [r["id"] for r in rows if "低区分度" in r["flags"]],
        "extreme_difficulty": [r["id"] for r in rows if "过易" in r["flags"] or "过难" in r["flags"]],
    }


def compare_runs(records: list[dict]) -> dict:
    """Build a side-by-side comparison plus cross-run item statistics."""
    runs = []
    stage_map: dict[str, dict] = {}
    cap_map: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("id")
        s = rec.get("summary") or {}
        ov = s.get("overall") or {}
        runs.append({
            "id": rid,
            "model": ((rec.get("config") or {}).get("model") or {}).get("name"),
            "status": rec.get("status"),
            "created_at": rec.get("created_at"),
            "weighted_percent": ov.get("weighted_percent"),
            "percent": ov.get("percent"),
            "coverage": ov.get("coverage"),
            "grade": ov.get("grade"),
        })
        for st in s.get("stages") or []:
            row = stage_map.setdefault(st.get("id"), {
                "id": st.get("id"), "name": st.get("name"), "values": {},
            })
            row["values"][rid] = st.get("percent")
        for c in s.get("capabilities") or []:
            row = cap_map.setdefault(c.get("capability"), {
                "capability": c.get("capability"), "values": {},
            })
            row["values"][rid] = c.get("percent")

    stats = item_statistics(records)

    item_values: dict[str, dict] = {}
    for rec in records:
        rid = rec.get("id")
        for res in rec.get("results") or []:
            f = _fraction(res)
            if f is None:
                continue
            item_values.setdefault(res.get("id"), {})[rid] = f
    for it in stats["items"]:
        it["values"] = item_values.get(it["id"], {})

    return {
        "runs": runs,
        "stages": list(stage_map.values()),
        "capabilities": list(cap_map.values()),
        "stats": stats,
    }
