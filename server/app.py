"""Minimal web server (stdlib only): static UI + JSON API + run manager."""
from __future__ import annotations

import json
import os
import threading
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(ROOT, "web")
RUNS_DIR = os.path.join(ROOT, "runs")
CONFIG_PATH = os.path.join(ROOT, "config.json")
BANK_DIR = os.path.join(ROOT, "bank")

from engine.loader import load_bank, bank_summary, load_flows, sample_questions  # noqa: E402
from engine.runner import evaluate  # noqa: E402
from engine.scorer import aggregate  # noqa: E402
from engine.audit import audit_questions  # noqa: E402
from engine.report import render_report  # noqa: E402
from engine.compare import compare_runs  # noqa: E402
from engine.profiles import resolve_profile, filter_by_profile, profile_public  # noqa: E402
from engine.paper import build_paper, paper_structure  # noqa: E402

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}

STATE: dict = {"runs": {}}
LOCK = threading.Lock()


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _load_config_file() -> dict:
    with open(CONFIG_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def build_config(overrides: dict) -> dict:
    cfg = json.loads(json.dumps(_load_config_file()))
    if overrides.get("base_url"):
        cfg["model"]["base_url"] = overrides["base_url"]
    if overrides.get("api_key") is not None:
        cfg["model"]["api_key"] = overrides["api_key"]
    if overrides.get("model"):
        cfg["model"]["name"] = overrides["model"]
    if overrides.get("judge_base_url"):
        cfg["judge"]["base_url"] = overrides["judge_base_url"]
    if overrides.get("judge_api_key") is not None:
        cfg["judge"]["api_key"] = overrides["judge_api_key"]
    cfg["judge"]["enabled"] = bool(overrides.get("judge_enabled", True))
    cfg["judge"]["debias"] = bool(overrides.get("judge_debias",
                                                cfg["judge"].get("debias", False)))
    if overrides.get("judge_model"):
        cfg["judge"]["model"] = overrides["judge_model"]
    if overrides.get("preset"):
        cfg["weights"]["preset"] = overrides["preset"]
    if overrides.get("concurrency"):
        cfg["run"]["concurrency"] = int(overrides["concurrency"])
    if overrides.get("code_samples"):
        cfg["run"]["code_samples"] = max(1, int(overrides["code_samples"]))
    if overrides.get("sample"):
        cfg["run"]["sample"] = max(1, int(overrides["sample"]))
    if overrides.get("paper"):
        cfg["paper"] = max(1, int(overrides["paper"]))
    if overrides.get("seed") is not None:
        cfg["run"]["seed"] = overrides["seed"]
    if overrides.get("profile"):
        cfg["profile"] = {"id": overrides["profile"],
                          "level": overrides.get("level") or "中级"}
    return cfg


def _test_model(body: dict) -> dict:
    """Check an OpenAI-compatible endpoint: /models first, then a 1-token chat."""
    cfg = _load_config_file()
    base_url = str(body.get("base_url") or cfg["model"].get("base_url", "")).strip().rstrip("/")
    api_key = str(body.get("api_key") or cfg["model"].get("api_key", ""))
    model = str(body.get("model") or cfg["model"].get("name", ""))
    if not base_url:
        return {"ok": False, "error": "base_url 为空"}
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    models_error = None
    try:
        req = urllib.request.Request(base_url + "/models", headers=headers)
        with urllib.request.urlopen(req, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        models = [m.get("id") for m in (data.get("data") or [])
                  if isinstance(m, dict) and m.get("id")]
        return {"ok": True, "via": "models", "models": models[:50], "count": len(models)}
    except Exception as exc:  # noqa: BLE001
        models_error = str(exc)

    try:
        payload = {"model": model, "messages": [{"role": "user", "content": "ping"}],
                   "max_tokens": 1}
        req = urllib.request.Request(
            base_url + "/chat/completions",
            data=json.dumps(payload).encode(),
            headers=headers, method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8", "replace"))
        if data.get("choices"):
            return {"ok": True, "via": "chat"}
        return {"ok": False, "error": "chat 返回无 choices"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": f"/models: {models_error}; /chat/completions: {exc}"}


def _masked_settings() -> dict:
    """Full config for the settings UI; API keys are blanked but flagged."""
    cfg = _load_config_file()
    model_key = cfg.get("model", {}).get("api_key", "")
    judge_key = cfg.get("judge", {}).get("api_key", "")
    cfg.setdefault("model", {})["api_key"] = ""
    cfg["model"]["api_key_set"] = bool(model_key)
    cfg.setdefault("judge", {})["api_key"] = ""
    cfg["judge"]["api_key_set"] = bool(judge_key)
    return cfg


def _clamp(value, default, lo, hi, cast=float):
    try:
        x = cast(value)
    except (TypeError, ValueError):
        x = cast(default)
    return max(lo, min(hi, x))


def _save_settings(body: dict) -> dict:
    if not isinstance(body, dict):
        raise ValueError("settings must be an object")
    cfg = _load_config_file()
    model = body.get("model") or {}
    judge = body.get("judge") or {}
    runc = body.get("run") or {}
    weights = body.get("weights") or {}

    name = str(model.get("name") or cfg["model"].get("name", "")).strip()
    base_url = str(model.get("base_url") or cfg["model"].get("base_url", "")).strip()
    if "name" in model and not str(model.get("name", "")).strip():
        raise ValueError("model name is required")
    if "base_url" in model and not str(model.get("base_url", "")).strip():
        raise ValueError("base_url is required")
    if not name or not base_url:
        raise ValueError("model name and base_url are required")
    cfg["model"]["name"] = name
    cfg["model"]["base_url"] = base_url
    if model.get("api_key"):
        cfg["model"]["api_key"] = str(model["api_key"])
    cfg["model"]["temperature"] = _clamp(model.get("temperature"), cfg["model"].get("temperature", 0.2), 0, 2)
    cfg["model"]["max_tokens"] = _clamp(model.get("max_tokens"), cfg["model"].get("max_tokens", 2048), 1, 131072, int)
    cfg["model"]["timeout"] = _clamp(model.get("timeout"), cfg["model"].get("timeout", 180), 1, 3600, int)

    cfg["judge"]["enabled"] = bool(judge.get("enabled", cfg["judge"].get("enabled", True)))
    cfg["judge"]["debias"] = bool(judge.get("debias", cfg["judge"].get("debias", True)))
    cfg["judge"]["model"] = str(judge.get("model") or cfg["judge"].get("model", "")).strip()
    judge_base = str(judge.get("base_url") or "").strip()
    if judge_base:
        cfg["judge"]["base_url"] = judge_base
    if judge.get("api_key"):
        cfg["judge"]["api_key"] = str(judge["api_key"])
    cfg["judge"]["temperature"] = _clamp(judge.get("temperature"), cfg["judge"].get("temperature", 0.0), 0, 2)

    cfg["run"]["concurrency"] = _clamp(runc.get("concurrency"), cfg["run"].get("concurrency", 4), 1, 32, int)
    cfg["run"]["code_samples"] = _clamp(runc.get("code_samples"), cfg["run"].get("code_samples", 1), 1, 10, int)
    cfg["run"]["sample"] = _clamp(runc.get("sample"), cfg["run"].get("sample", 0), 0, 1000, int)
    seed = runc.get("seed")
    cfg["run"]["seed"] = None if seed in (None, "") else int(seed)
    cfg["run"]["allow_code_exec"] = bool(runc.get("allow_code_exec", cfg["run"].get("allow_code_exec", True)))

    preset = str(weights.get("preset") or cfg["weights"].get("preset", "balanced"))
    if preset in cfg["weights"].get("presets", {}):
        cfg["weights"]["preset"] = preset
    incoming = weights.get("presets") or {}
    for preset_name, table in cfg["weights"].get("presets", {}).items():
        incoming_table = incoming.get(preset_name)
        if not isinstance(incoming_table, dict):
            continue
        for stage, value in incoming_table.items():
            if stage in table:
                table[stage] = _clamp(value, table[stage], 0, 100)

    roles_in = weights.get("roles")
    if isinstance(roles_in, dict):
        cfg["weights"].setdefault("roles", {})
        for role, value in roles_in.items():
            role = str(role)
            cfg["weights"]["roles"][role] = _clamp(
                value, cfg["weights"]["roles"].get(role, 1.0), 0, 100)

    tmp = CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, CONFIG_PATH)
    return _masked_settings()


def _public_config() -> dict:
    cfg = _load_config_file()
    return {
        "model": {
            "name": cfg["model"].get("name", ""),
            "base_url": cfg["model"].get("base_url", ""),
        },
        "judge_enabled": cfg.get("judge", {}).get("enabled", True),
        "judge_debias": cfg.get("judge", {}).get("debias", False),
        "code_samples": cfg.get("run", {}).get("code_samples", 1),
        "sample": cfg.get("run", {}).get("sample", 0),
        "seed": cfg.get("run", {}).get("seed"),
        "presets": list(cfg.get("weights", {}).get("presets", {}).keys()),
        "preset": cfg.get("weights", {}).get("preset", "balanced"),
    }


def _persist(run_id: str, record: dict) -> None:
    os.makedirs(RUNS_DIR, exist_ok=True)
    tmp = os.path.join(RUNS_DIR, f".{run_id}.tmp")
    dst = os.path.join(RUNS_DIR, f"{run_id}.json")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(record, fh, ensure_ascii=False, default=str)
    os.replace(tmp, dst)


def load_persisted_runs() -> dict:
    out = {}
    if not os.path.isdir(RUNS_DIR):
        return out
    for name in os.listdir(RUNS_DIR):
        if not name.endswith(".json") or name.startswith("."):
            continue
        try:
            with open(os.path.join(RUNS_DIR, name), encoding="utf-8") as fh:
                rec = json.load(fh)
            rec.setdefault("status", "done")
            out[rec.get("id", name[:-5])] = rec
        except Exception:  # noqa: BLE001
            continue
    return out


def start_run(overrides: dict) -> str:
    run_id = time.strftime("%Y%m%d-%H%M%S") + "-" + uuid.uuid4().hex[:6]
    cfg = build_config(overrides)

    questions = load_bank(BANK_DIR)
    profile_cfg = cfg.get("profile")
    if profile_cfg:
        spec = resolve_profile(profile_cfg["id"], profile_cfg.get("level") or "中级")
        questions = filter_by_profile(questions, spec)
    stages = overrides.get("stages") or []
    if stages:
        allowed = set(stages)
        questions = [q for q in questions if q["stage"] in allowed]
    sample = overrides.get("sample") or cfg["run"].get("sample", 0)
    paper = overrides.get("paper") or cfg.get("paper") or 0
    if paper:
        questions = build_paper(questions, int(paper), cfg["run"].get("seed"))
    elif sample:
        questions = sample_questions(questions, int(sample), cfg["run"].get("seed"))
    limit = overrides.get("limit")
    if limit and not sample and not paper:
        seen: dict[str, int] = {}
        kept = []
        for q in questions:
            n = seen.get(q["stage"], 0)
            if n < int(limit):
                kept.append(q)
            seen[q["stage"]] = n + 1
        questions = kept

    record = {
        "id": run_id,
        "status": "running",
        "label": overrides.get("label") or "",
        "created_at": _now(),
        "started_ts": time.time(),
        "finished_at": None,
        "config": {
            "model": {**cfg["model"], "api_key": "",
                      "api_key_set": bool(cfg["model"].get("api_key"))},
            "judge": {"enabled": cfg["judge"].get("enabled"),
                      "model": cfg["judge"].get("model"),
                      "debias": cfg["judge"].get("debias")},
            "preset": cfg["weights"]["preset"],
            "code_samples": cfg["run"].get("code_samples", 1),
            "sample": cfg["run"].get("sample", 0),
            "seed": cfg["run"].get("seed"),
        },
        "stages": stages,
        "profile": cfg.get("profile"),
        "paper": ({"per_section": int(paper),
                   "sections": paper_structure(questions)} if paper else None),
        "progress": {"done": 0, "total": len(questions)},
        "results": [],
        "summary": None,
        "error": None,
    }
    with LOCK:
        STATE["runs"][run_id] = record

    def worker() -> None:
        try:
            def on_progress(done: int, total: int, res: dict) -> None:
                with LOCK:
                    record["results"].append(res)
                    record["progress"] = {"done": done, "total": total}

            results = evaluate(questions, cfg, progress_cb=on_progress)
            results.sort(key=lambda r: r.get("index", 0))
            summary = aggregate(results, cfg)
            with LOCK:
                record["results"] = results
                record["summary"] = summary
                record["status"] = "done"
                record["finished_at"] = _now()
                record["duration_s"] = round(time.time() - record["started_ts"], 1)
                _persist(run_id, record)
        except Exception as exc:  # noqa: BLE001
            with LOCK:
                record["status"] = "error"
                record["error"] = f"{exc}\n{traceback.format_exc()[-1500:]}"
                record["finished_at"] = _now()
                _persist(run_id, record)

    threading.Thread(target=worker, daemon=True).start()
    return run_id


class Handler(BaseHTTPRequestHandler):
    server_version = "LMExamBench/0.1"

    def log_message(self, fmt, *args):  # quieter logs
        return

    # ------------------------------------------------------------- helpers
    def _send_json(self, obj, status: int = 200) -> None:
        body = json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, msg: str, status: int = 400) -> None:
        self._send_json({"error": msg}, status=status)

    def _send_html(self, body: str, status: int = 200) -> None:
        raw = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def _send_bytes(self, body: bytes, ctype: str, status: int = 200,
                    filename: str | None = None) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(body)

    def _serve_web(self, path: str) -> None:
        name = os.path.basename(path)
        if name in ("", "/"):
            name = "index.html"
        full = os.path.abspath(os.path.join(WEB_DIR, name))
        if not full.startswith(os.path.abspath(WEB_DIR) + os.sep) and full != os.path.abspath(WEB_DIR):
            self._send_error_json("forbidden", 403)
            return
        if not os.path.isfile(full):
            self._send_error_json("not found", 404)
            return
        ext = os.path.splitext(full)[1].lower()
        ctype = CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_body(self) -> dict:
        length = int(self.headers.get("Content-Length") or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    # ------------------------------------------------------------- GET
    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        try:
            if path == "/api/health":
                self._send_json({"ok": True, "time": _now()})
            elif path == "/api/settings":
                self._send_json(_masked_settings())
            elif path == "/api/config":
                self._send_json(_public_config())
            elif path == "/api/bank/audit":
                questions = load_bank(BANK_DIR)
                self._send_json(audit_questions(questions, flows=load_flows(BANK_DIR)))
            elif path == "/api/compare":
                qs = parse_qs(urlparse(self.path).query)
                ids = (qs.get("ids") or [""])[0]
                with LOCK:
                    allruns = {**load_persisted_runs(), **STATE["runs"]}
                if ids:
                    selected = [allruns[i] for i in ids.split(",") if i in allruns]
                else:
                    selected = [r for r in allruns.values() if r.get("status") == "done"]
                selected.sort(key=lambda r: r.get("created_at") or "")
                if len(selected) < 2:
                    self._send_error_json("need at least 2 runs", 400)
                else:
                    self._send_json(compare_runs(selected))
            elif path == "/api/profiles":
                self._send_json(profile_public())
            elif path == "/api/bank":
                questions = load_bank(BANK_DIR)
                self._send_json({
                    "total": len(questions),
                    "stages": bank_summary(questions),
                    "flows": load_flows(BANK_DIR),
                })
            elif path.startswith("/api/runs/") and path.endswith("/export.pdf"):
                run_id = path[len("/api/runs/"):-len("/export.pdf")].strip("/")
                with LOCK:
                    rec = STATE["runs"].get(run_id) or load_persisted_runs().get(run_id)
                    payload = (json.loads(json.dumps(rec, ensure_ascii=False, default=str))
                               if rec is not None else None)
                if payload is None:
                    self._send_error_json("run not found", 404)
                else:
                    from engine.report_pdf import render_report_pdf
                    self._send_bytes(render_report_pdf(payload), "application/pdf",
                                     filename=f"{run_id}.pdf")
            elif path.startswith("/api/runs/") and path.endswith("/export"):
                run_id = path[len("/api/runs/"):-len("/export")].strip("/")
                with LOCK:
                    rec = STATE["runs"].get(run_id) or load_persisted_runs().get(run_id)
                    payload = (json.loads(json.dumps(rec, ensure_ascii=False, default=str))
                               if rec is not None else None)
                if payload is None:
                    self._send_error_json("run not found", 404)
                else:
                    self._send_html(render_report(payload))
            elif path == "/api/runs":
                with LOCK:
                    runs = {**load_persisted_runs(), **STATE["runs"]}
                summaries = []
                for r in runs.values():
                    summaries.append({
                        "id": r.get("id"),
                        "status": r.get("status"),
                        "label": r.get("label", ""),
                        "created_at": r.get("created_at"),
                        "model": (r.get("config") or {}).get("model", {}).get("name"),
                        "progress": r.get("progress"),
                        "overall": (r.get("summary") or {}).get("overall"),
                        "duration_s": r.get("duration_s"),
                    })
                summaries.sort(key=lambda x: x.get("created_at") or "", reverse=True)
                self._send_json({"runs": summaries})
            elif path.startswith("/api/runs/"):
                run_id = path[len("/api/runs/"):].strip("/")
                with LOCK:
                    rec = STATE["runs"].get(run_id) or load_persisted_runs().get(run_id)
                    if rec is not None:
                        payload = json.loads(json.dumps(rec, ensure_ascii=False, default=str))
                    else:
                        payload = None
                if payload is None:
                    self._send_error_json("run not found", 404)
                else:
                    self._send_json(payload)
            else:
                self._serve_web(path)
        except Exception as exc:  # noqa: BLE001
            self._send_error_json(f"server error: {exc}", 500)

    # ------------------------------------------------------------- POST
    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/api/runs":
            body = self._read_body()
            try:
                run_id = start_run(body)
                self._send_json({"id": run_id, "status": "running"}, status=201)
            except Exception as exc:  # noqa: BLE001
                self._send_error_json(f"cannot start run: {exc}", 500)
        elif path == "/api/settings":
            try:
                saved = _save_settings(self._read_body())
                self._send_json(saved)
            except Exception as exc:  # noqa: BLE001
                self._send_error_json(f"save settings failed: {exc}", 400)
        elif path == "/api/test":
            try:
                self._send_json(_test_model(self._read_body()))
            except Exception as exc:  # noqa: BLE001
                self._send_error_json(f"test failed: {exc}", 500)
        else:
            self._send_error_json("not found", 404)

    # ------------------------------------------------------------- DELETE
    def do_DELETE(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path.startswith("/api/runs/"):
            run_id = path[len("/api/runs/"):].strip("/")
            with LOCK:
                STATE["runs"].pop(run_id, None)
            f = os.path.join(RUNS_DIR, f"{run_id}.json")
            if os.path.isfile(f):
                os.unlink(f)
            self._send_json({"deleted": run_id})
        else:
            self._send_error_json("not found", 404)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"[LMExamBench] serving on http://{host}:{port}")
    print(f"[LMExamBench] bank: {BANK_DIR}  runs: {RUNS_DIR}")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[LMExamBench] stopped")
    finally:
        httpd.server_close()
