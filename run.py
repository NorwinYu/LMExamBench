#!/usr/bin/env python3
"""LMExamBench command line entry.

Usage:
  python3 run.py validate
  python3 run.py run [--config config.json] [--stages primary,junior] [--limit N]
                     [--paper N | --sample N --seed S] [--profile java-backend --level 中级]
                     [--base-url URL] [--model NAME] [--api-key KEY]
                     [--judge-base-url URL] [--judge-model NAME] [--no-judge] [--no-debias]
                     [--code-samples N] [--preset balanced] [--label TEXT] [--out path.json]
  python3 run.py list
  python3 run.py compare [RUN_ID ...]
  python3 run.py export RUN_ID [--format html|pdf] [--out path]
  python3 run.py regrade RUN_ID [--config config.json]
  python3 run.py audit [--threshold 0.85]
  python3 run.py serve [--host 127.0.0.1] [--port 8000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

from engine.loader import load_bank, bank_summary, STAGE_BY_ID, sample_questions  # noqa: E402
from engine.runner import evaluate  # noqa: E402
from engine.scorer import aggregate  # noqa: E402
from engine.audit import audit_questions  # noqa: E402
from engine.report import render_report  # noqa: E402
from engine.compare import compare_runs  # noqa: E402
from engine.profiles import LEVELS, resolve_profile, filter_by_profile  # noqa: E402
from engine.paper import build_paper, paper_structure  # noqa: E402

BANK_DIR = os.path.join(ROOT, "bank")
RUNS_DIR = os.path.join(ROOT, "runs")


def load_config(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def apply_overrides(cfg: dict, args) -> dict:
    if args.base_url:
        cfg["model"]["base_url"] = args.base_url
    if args.api_key is not None:
        cfg["model"]["api_key"] = args.api_key
    if args.model:
        cfg["model"]["name"] = args.model
    if getattr(args, "judge_base_url", None):
        cfg["judge"]["base_url"] = args.judge_base_url
    if getattr(args, "judge_api_key", None) is not None:
        cfg["judge"]["api_key"] = args.judge_api_key
    if getattr(args, "judge_model", None):
        cfg["judge"]["model"] = args.judge_model
    if args.no_judge:
        cfg["judge"]["enabled"] = False
    if getattr(args, "no_debias", False):
        cfg["judge"]["debias"] = False
    if args.preset:
        cfg["weights"]["preset"] = args.preset
    if args.concurrency:
        cfg["run"]["concurrency"] = args.concurrency
    if getattr(args, "code_samples", None):
        cfg["run"]["code_samples"] = max(1, int(args.code_samples))
    if getattr(args, "sample", None):
        cfg["run"]["sample"] = max(1, int(args.sample))
    if getattr(args, "seed", None) is not None:
        cfg["run"]["seed"] = args.seed
    return cfg


def select_questions(args) -> list[dict]:
    questions = load_bank(BANK_DIR)
    if getattr(args, "profile", None):
        spec = resolve_profile(args.profile, getattr(args, "level", None) or "中级")
        questions = filter_by_profile(questions, spec)
    if args.stages:
        wanted = {s.strip() for s in args.stages.split(",") if s.strip()}
        unknown = wanted - set(STAGE_BY_ID)
        if unknown:
            raise SystemExit(f"unknown stages: {sorted(unknown)}")
        questions = [q for q in questions if q["stage"] in wanted]
    if getattr(args, "paper", 0):
        questions = build_paper(questions, args.paper, getattr(args, "seed", None))
    elif getattr(args, "sample", 0):
        questions = sample_questions(questions, args.sample, args.seed)
    elif args.limit:
        seen: dict[str, int] = {}
        kept = []
        for q in questions:
            n = seen.get(q["stage"], 0)
            if n < args.limit:
                kept.append(q)
            seen[q["stage"]] = n + 1
        questions = kept
    return questions


def cmd_validate(args) -> None:
    questions = load_bank(BANK_DIR)
    print(f"bank OK: {len(questions)} questions in {BANK_DIR}")
    for s in bank_summary(questions):
        print(f"  {s['id']:<10} {s['name']:<6} {s['count']:>3} 题")


def _write_record(record: dict, out: str) -> None:
    os.makedirs(os.path.dirname(out) or ".", exist_ok=True)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, default=str)
    os.replace(tmp, out)


def _mask_model(cfg_model: dict) -> dict:
    m = dict(cfg_model)
    m["api_key"] = ""
    m["api_key_set"] = bool(cfg_model.get("api_key"))
    return m


def cmd_run(args) -> None:
    cfg = apply_overrides(load_config(args.config), args)
    if getattr(args, "profile", None):
        cfg["profile"] = {"id": args.profile,
                          "level": getattr(args, "level", None) or "中级"}
    questions = select_questions(args)
    if not questions:
        raise SystemExit("no questions selected")

    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    out = args.out or os.path.join(RUNS_DIR, f"{run_id}.json")
    t0 = time.time()
    record = {
        "id": run_id,
        "status": "running",
        "label": args.label or "",
        "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "started_ts": t0,
        "finished_at": None,
        "duration_s": None,
        "config": {
            "model": _mask_model(cfg["model"]),
            "judge": {"enabled": cfg["judge"].get("enabled"),
                      "model": cfg["judge"].get("model"),
                      "debias": cfg["judge"].get("debias")},
            "preset": cfg["weights"]["preset"],
            "code_samples": cfg["run"].get("code_samples", 1),
            "sample": cfg["run"].get("sample", 0),
            "seed": cfg["run"].get("seed"),
        },
        "stages": args.stages.split(",") if args.stages else [],
        "profile": cfg.get("profile"),
        "paper": ({"per_section": args.paper,
                   "sections": paper_structure(questions)} if getattr(args, "paper", 0) else None),
        "progress": {"done": 0, "total": len(questions)},
        "results": [],
        "summary": None,
        "error": None,
    }
    _write_record(record, out)
    print(f"run {run_id}: {len(questions)} questions, model={cfg['model']['name']}, "
          f"base_url={cfg['model']['base_url']}, judge={cfg['judge'].get('enabled')}")

    def progress(done: int, total: int, res: dict) -> None:
        record["results"].append(res)
        record["progress"] = {"done": done, "total": total}
        _write_record(record, out)
        score = (res.get("grading") or {}).get("score")
        mark = "ERR" if res.get("error") else ("-" if score is None else f"{score:g}")
        print(f"  [{done:>3}/{total}] {res['id']:<24} {mark:>7}", flush=True)

    try:
        results = evaluate(questions, cfg, progress_cb=progress)
    except Exception as exc:  # noqa: BLE001
        record["status"] = "error"
        record["error"] = repr(exc)
        record["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
        _write_record(record, out)
        raise

    results.sort(key=lambda r: r.get("index", 0))
    summary = aggregate(results, cfg)
    record.update({
        "status": "done",
        "finished_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration_s": round(time.time() - t0, 1),
        "progress": {"done": len(results), "total": len(results)},
        "results": results,
        "summary": summary,
    })
    _write_record(record, out)

    ov = summary["overall"]
    print("-" * 52)
    if summary.get("profile"):
        p = summary["profile"]
        print(f"方案 {p['name']} / {p['level']}：{p['score']}%"
              f"　能力 {p.get('capability_score')}　岗位 {p.get('role_score')}")
    print(f"weighted {ov['weighted_percent']:.1f}%  ({ov['grade']['label']})"
          f"  raw {ov['percent']:.1f}%"
          f"  coverage {ov['coverage'] * 100:.0f}%")
    for s in summary["stages"]:
        print(f"  {s['name']:<6} {s['percent']:>6.1f}%  "
              f"({s['earned']:g}/{s['graded_total']:g})  w={s['weight']:g}")
    print(f"results -> {out}")


def cmd_list(args) -> None:
    if not os.path.isdir(RUNS_DIR):
        print("no runs yet")
        return
    rows = []
    for name in sorted(os.listdir(RUNS_DIR)):
        if name.endswith(".json") and not name.startswith("."):
            with open(os.path.join(RUNS_DIR, name), encoding="utf-8") as fh:
                try:
                    rec = json.load(fh)
                except json.JSONDecodeError:
                    continue
            ov = (rec.get("summary") or {}).get("overall") or {}
            rows.append((rec.get("created_at", ""), name[:-5],
                         (rec.get("config", {}).get("model") or {}).get("name", ""),
                         ov.get("weighted_percent")))
    for created, rid, model, wp in rows:
        score = f"{wp:.1f}%" if isinstance(wp, (int, float)) else "-"
        print(f"{created}  {rid}  {model:<20} {score}")


def _pct(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.1f}%"
    return "-"


def _num(value) -> str:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f"{value:.3f}"
    return "-"


def _load_run(run_id: str) -> dict:
    path = os.path.join(RUNS_DIR, run_id + ".json")
    if not os.path.isfile(path):
        raise SystemExit(f"run not found: {path}")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _all_done_runs() -> list[dict]:
    out = []
    if not os.path.isdir(RUNS_DIR):
        return out
    for name in sorted(os.listdir(RUNS_DIR)):
        if not name.endswith(".json") or name.startswith("."):
            continue
        try:
            with open(os.path.join(RUNS_DIR, name), encoding="utf-8") as fh:
                rec = json.load(fh)
        except json.JSONDecodeError:
            continue
        if rec.get("status") == "done":
            out.append(rec)
    return out


def cmd_compare(args) -> None:
    records = [_load_run(r) for r in args.run_ids] if args.run_ids else _all_done_runs()
    if len(records) < 2:
        raise SystemExit(f"need at least 2 runs, got {len(records)}")
    res = compare_runs(records)
    runs = res["runs"]
    print("runs:")
    for i, r in enumerate(runs):
        print(f"  #{i + 1}  {r['id']:<28} {(r.get('model') or ''):<16} "
              f"weighted={_pct(r.get('weighted_percent'))} raw={_pct(r.get('percent'))}")
    print("stages (percent per run):")
    print("  " + "stage".ljust(10) + "".join(f"#{i + 1}".rjust(12) for i in range(len(runs))))
    for st in res["stages"]:
        cells = "".join(_pct(st["values"].get(r["id"])).rjust(12) for r in runs)
        print("  " + str(st.get("name")).ljust(10) + cells)
    print("capabilities:")
    for c in res["capabilities"]:
        cells = "".join(_pct(c["values"].get(r["id"])).rjust(12) for r in runs)
        print("  " + str(c.get("capability")).ljust(10) + cells)
    stats = res["stats"]
    print(f"item statistics ({len(stats['items'])} items; "
          f"discrimination needs >= {stats['min_runs_for_discrimination']} runs):")
    for it in stats["items"][:30]:
        disc = "-" if it["discrimination"] is None else f"{it['discrimination']:+.3f}"
        flags = ",".join(it["flags"])
        print(f"  {it['id']:<28} p={_num(it['p_value'])}  disc={disc:>7}  {flags}")


def _regrade_judge(cfg: dict):
    from engine.client import ChatClient
    jc = cfg.get("judge") or {}
    if not jc.get("enabled", True):
        return None, ""
    model = jc.get("model") or cfg["model"]["name"]
    client = ChatClient(
        base_url=jc.get("base_url") or cfg["model"]["base_url"],
        api_key=jc.get("api_key", ""),
        model=model,
        temperature=jc.get("temperature", 0.0),
        max_tokens=jc.get("max_tokens", 2048),
        timeout=jc.get("timeout", 180),
    )
    return client, model


def cmd_regrade(args) -> None:
    from engine.grader import grade_question
    path = os.path.join(RUNS_DIR, args.run_id + ".json")
    if not os.path.isfile(path):
        raise SystemExit(f"run not found: {path}")
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    cfg = load_config(args.config)
    rec_cfg = record.get("config") or {}
    if rec_cfg.get("preset"):
        cfg["weights"]["preset"] = rec_cfg["preset"]
    if record.get("profile"):
        cfg["profile"] = record["profile"]
    bank = {q["id"]: q for q in load_bank(BANK_DIR)}
    judge_client, judge_model = _regrade_judge(cfg)
    allow_code = cfg["run"].get("allow_code_exec", True)
    candidate = (rec_cfg.get("model") or {}).get("name") or cfg["model"]["name"]
    n = 0
    for r in record.get("results") or []:
        q = bank.get(r.get("id"))
        if not q:
            continue
        r["grading"] = grade_question(
            q, r.get("model_output") or "", judge_client, judge_model,
            allow_code_exec=allow_code, judge_debias=False, candidate_model=candidate,
        )
        n += 1
    summary = aggregate(record["results"], cfg)
    record["summary"] = summary
    record["regraded_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
    _write_record(record, path)
    ov = summary["overall"]
    print(f"regraded {n} questions -> weighted {ov['weighted_percent']:.1f}%"
          f" raw {ov['percent']:.1f}% coverage {ov['coverage'] * 100:.0f}%")


def cmd_serve(args) -> None:
    from server.app import serve
    serve(args.host, args.port)


def cmd_audit(args) -> None:
    questions = load_bank(BANK_DIR)
    res = audit_questions(questions, args.threshold)
    print(f"bank: {res['total']} questions, near-duplicate pairs: {res['duplicate_count']} "
          f"(threshold {res['threshold']})")
    for d in res["duplicates"]:
        print(f"  {d['a']} ~ {d['b']}  sim={d['similarity']}")
    print("capability coverage:")
    for stage, row in res["coverage"].items():
        cells = "  ".join(f"{c}:{n}" for c, n in sorted(row.items(), key=lambda x: -x[1]))
        print(f"  {stage:<10} {cells}")


def cmd_export(args) -> None:
    path = os.path.join(RUNS_DIR, args.run_id + ".json")
    if not os.path.isfile(path):
        raise SystemExit(f"run not found: {path}")
    with open(path, encoding="utf-8") as fh:
        record = json.load(fh)
    fmt = getattr(args, "format", "html")
    if args.out and args.out.lower().endswith(".pdf"):
        fmt = "pdf"
    if fmt == "pdf":
        from engine.report_pdf import render_report_pdf
        out = args.out or os.path.join(RUNS_DIR, args.run_id + ".pdf")
        with open(out, "wb") as fh:
            fh.write(render_report_pdf(record))
    else:
        html = render_report(record)
        out = args.out or os.path.join(RUNS_DIR, args.run_id + ".html")
        with open(out, "w", encoding="utf-8") as fh:
            fh.write(html)
    print(f"report -> {out}")


def main() -> None:
    p = argparse.ArgumentParser(description="LMExamBench - layered LLM exam evaluation")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser("validate", help="validate the question bank")
    v.set_defaults(func=cmd_validate)

    r = sub.add_parser("run", help="run an evaluation")
    r.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    r.add_argument("--stages", default="")
    r.add_argument("--limit", type=int, default=0, help="max questions per stage")
    r.add_argument("--base-url", default=None)
    r.add_argument("--model", default=None)
    r.add_argument("--api-key", default=None)
    r.add_argument("--judge-base-url", default=None, help="judge endpoint (default: config)")
    r.add_argument("--judge-api-key", default=None)
    r.add_argument("--judge-model", default=None, help="judge model name")
    r.add_argument("--no-judge", action="store_true")
    r.add_argument("--no-debias", action="store_true", help="disable two-pass judge debiasing")
    r.add_argument("--preset", default=None)
    r.add_argument("--concurrency", type=int, default=None)
    r.add_argument("--code-samples", type=int, default=None,
                   help="code samples per problem for pass@k")
    r.add_argument("--sample", type=int, default=0,
                   help="randomly draw N questions per stage")
    r.add_argument("--paper", type=int, default=0,
                   help="exam paper: up to N questions per stage/subject")
    r.add_argument("--seed", type=int, default=None, help="random seed for sampling")
    r.add_argument("--profile", default=None, help="job profile: java-backend | nlp-algorithm")
    r.add_argument("--level", default="中级", choices=LEVELS, help="job level")
    r.add_argument("--label", default="")
    r.add_argument("--out", default=None)
    r.set_defaults(func=cmd_run)

    l = sub.add_parser("list", help="list saved runs")
    l.set_defaults(func=cmd_list)

    a = sub.add_parser("audit", help="audit the question bank (duplicates/coverage)")
    a.add_argument("--threshold", type=float, default=0.85)
    a.set_defaults(func=cmd_audit)

    e = sub.add_parser("export", help="export a run as standalone HTML")
    e.add_argument("run_id")
    e.add_argument("--out", default=None)
    e.add_argument("--format", choices=("html", "pdf"), default="html")

    g = sub.add_parser("regrade", help="re-grade a run from stored outputs")
    g.add_argument("run_id")
    g.add_argument("--config", default=os.path.join(ROOT, "config.json"))
    g.set_defaults(func=cmd_regrade)
    e.set_defaults(func=cmd_export)

    c = sub.add_parser("compare", help="compare runs + cross-model item statistics")
    c.add_argument("run_ids", nargs="*")
    c.set_defaults(func=cmd_compare)

    s = sub.add_parser("serve", help="start the web dashboard")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.set_defaults(func=cmd_serve)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
