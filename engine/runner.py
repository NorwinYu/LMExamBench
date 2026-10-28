"""Run a model over the question bank and grade each answer."""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from .client import ChatClient, ChatError
from .grader import grade_question
from .prompts import build_messages


def _make_client(cfg: dict, default_model: str) -> ChatClient:
    return ChatClient(
        base_url=cfg.get("base_url", "http://127.0.0.1:11434/v1"),
        api_key=cfg.get("api_key", ""),
        model=cfg.get("model") or default_model,
        temperature=cfg.get("temperature", 0.2),
        max_tokens=cfg.get("max_tokens", 2048),
        timeout=cfg.get("timeout", 180),
    )


def _run_one(q: dict, client: ChatClient, judge_client, judge_model: str,
             allow_code_exec: bool, judge_debias: bool = False,
             candidate_model: str = "", code_samples: int = 1,
             max_retries: int = 2) -> dict:
    base = {
        "id": q["id"],
        "stage": q["stage"],
        "stage_name": q.get("stage_name", q["stage"]),
        "subject": q.get("subject", "综合"),
        "chapter": q.get("chapter"),
        "topic": q.get("topic"),
        "type": q["type"],
        "difficulty": q.get("difficulty", "medium"),
        "capabilities": q.get("capabilities", ["知识"]),
        "tags": q.get("tags", []),
        "round": q.get("round"),
        "role": q.get("role"),
        "level": q.get("level"),
        "format": q.get("format"),
        "source_style": q.get("source_style"),
        "time_limit_min": q.get("time_limit_min"),
        "question": q["question"],
        "options": q.get("options"),
        "reference": q.get("reference", ""),
        "rubric": q.get("rubric", []),
        "points": float(q["points"]),
        "model_output": "",
        "reasoning": "",
        "usage": {},
        "grading": None,
        "error": None,
        "latency_ms": None,
    }

    last_err = None
    for attempt in range(max_retries + 1):
        try:
            t0 = time.time()
            if q["type"] == "code" and code_samples > 1:
                samples = []
                usage: dict = {}
                for _ in range(code_samples):
                    r = client.chat(build_messages(q))
                    samples.append(r["content"])
                    for kk, vv in (r.get("usage") or {}).items():
                        if isinstance(vv, (int, float)):
                            usage[kk] = usage.get(kk, 0) + vv
                base["model_output"] = "\n\n".join(
                    f"# --- sample {i + 1} ---\n{s}" for i, s in enumerate(samples))
                base["usage"] = usage
                payload = samples
            else:
                r = client.chat(build_messages(q))
                base["model_output"] = r["content"]
                base["reasoning"] = r.get("reasoning", "")
                base["usage"] = r.get("usage", {})
                payload = r["content"]
            latency = int((time.time() - t0) * 1000)
            base["latency_ms"] = latency
            base["grading"] = grade_question(
                q, payload, judge_client, judge_model,
                allow_code_exec=allow_code_exec,
                judge_debias=judge_debias,
                candidate_model=candidate_model,
            )
            return base
        except ChatError as exc:
            last_err = str(exc)
            if attempt < max_retries:
                time.sleep(1.5 * (attempt + 1))
        except Exception as exc:  # noqa: BLE001
            last_err = repr(exc)
            break

    base["error"] = last_err
    base["grading"] = {
        "score": None, "max": float(q["points"]), "fraction": None,
        "correct": None, "method": "none", "detail": {"error": last_err},
    }
    return base


def evaluate(questions: list[dict], config: dict, progress_cb=None) -> list[dict]:
    model_cfg = config.get("model", {})
    judge_cfg = config.get("judge", {})
    run_cfg = config.get("run", {})

    client = _make_client(model_cfg, model_cfg.get("name", ""))
    candidate_model = model_cfg.get("name", "")
    judge_client = None
    judge_model = ""
    judge_debias = False
    if judge_cfg.get("enabled", True):
        judge_client = _make_client(judge_cfg, model_cfg.get("name", ""))
        judge_model = judge_cfg.get("model") or model_cfg.get("name", "")
        judge_debias = bool(judge_cfg.get("debias", False))

    allow_code = run_cfg.get("allow_code_exec", True)
    code_samples = max(1, int(run_cfg.get("code_samples", 1)))
    concurrency = max(1, int(run_cfg.get("concurrency", 4)))
    results: list[dict] = [None] * len(questions)  # type: ignore[list-item]
    lock = threading.Lock()
    done = 0

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {
            pool.submit(
                _run_one, q, client, judge_client, judge_model, allow_code,
                judge_debias=judge_debias, candidate_model=candidate_model,
                code_samples=code_samples,
            ): i
            for i, q in enumerate(questions)
        }
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                res = fut.result()
            except Exception as exc:  # noqa: BLE001
                q = questions[idx]
                res = {
                    "id": q["id"], "stage": q["stage"],
                    "stage_name": q.get("stage_name", q["stage"]),
                    "subject": q.get("subject", "综合"), "type": q["type"],
                    "chapter": q.get("chapter"), "topic": q.get("topic"),
                    "difficulty": q.get("difficulty", "medium"),
                    "capabilities": q.get("capabilities", ["知识"]),
                    "tags": q.get("tags", []),
                    "round": q.get("round"),
                    "role": q.get("role"),
                    "level": q.get("level"),
                    "format": q.get("format"),
                    "source_style": q.get("source_style"),
                    "time_limit_min": q.get("time_limit_min"),
                    "question": q["question"], "options": q.get("options"),
                    "reference": q.get("reference", ""), "rubric": q.get("rubric", []),
                    "points": float(q["points"]), "model_output": "",
                    "reasoning": "", "usage": {}, "error": repr(exc),
                    "grading": {"score": None, "max": float(q["points"]),
                                "fraction": None, "correct": None, "method": "none",
                                "detail": {"error": repr(exc)}},
                    "latency_ms": None,
                }
            res["index"] = idx
            with lock:
                results[idx] = res
                done += 1
                if progress_cb:
                    progress_cb(done, len(questions), res)

    return [r for r in results if r is not None]
