"""Grading for all question types.

- choice / fill : deterministic matching
- code         : run the candidate code against test cases in a subprocess
- solution / interview : LLM-as-judge against a rubric

Security note: code questions execute model-generated Python in a subprocess
with a timeout. This is intended for trusted, local evaluation only. Disable
`run.allow_code_exec` for untrusted models.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import os
import time
from math import comb

from .taxonomy import TRUE_TOKENS, FALSE_TOKENS

CHOICE_LETTERS = "ABCDEFGH"

# ---------------------------------------------------------------- text utils


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    text = text.replace("**", "").replace("__", "")
    return text


def extract_final_answer(text: str) -> str:
    """Pull a short final answer out of a free-form reply when possible."""
    m = re.search(r"【答案】\s*[:：]?\s*(.+)", text)
    if m:
        return m.group(1).strip()
    m = re.search(r"(?:最终答案|正确答案|答案|答)\s*[:：]\s*(.+)", text)
    if m:
        return m.group(1).strip()
    return text.strip()


def _norm(text: str) -> str:
    text = _strip_markdown(str(text)).strip().lower()
    text = re.sub(r"\s+", "", text)
    text = re.sub(r"[，。、,\.；;：:！!？?\"'“”‘’（）()\[\]【】<>《》°%‰]", "", text)
    return text


def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _numbers(text) -> list[float]:
    return [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", str(text))]


# ---------------------------------------------------------------- choice/fill


def _expected_choice_letter(q: dict) -> str:
    ans = str(q.get("answer", "")).strip()
    m = re.match(r"^[\(\（]?\s*([A-Ha-h])", ans)
    if m:
        return m.group(1).upper()
    for i, opt in enumerate(q.get("options", [])):
        body = re.sub(r"^[A-Ha-h]\s*[\.、\)）]\s*", "", opt).strip()
        if body and (ans == opt or ans in opt or _norm(ans) == _norm(body)):
            return CHOICE_LETTERS[i]
    return ans.upper()


def _extract_choice(text: str) -> str | None:
    cleaned = _strip_markdown(text)
    # most precise: a letter right after the 【答案】 marker
    m = re.search(r"【答案】\s*[:：]?\s*[\(\（]?\s*([A-Ha-h])(?![A-Za-z])", cleaned)
    if m:
        return m.group(1).upper()
    patterns = [
        r"(?:答案|选项|正确选项|答案是|应选|故选)\s*[:：]?\s*[\(\（]?\s*([A-Ha-h])(?![A-Za-z])",
        r"(?<![A-Za-z])([A-H])(?![A-Za-z])\s*[\.。、:：]",
        r"(?<![A-Za-z])([A-H])(?![A-Za-z])",
    ]
    for pat in patterns:
        m = re.search(pat, cleaned)
        if m:
            return m.group(1).upper()
    return None


def grade_choice(q: dict, text: str) -> dict:
    expected = _expected_choice_letter(q)
    got = _extract_choice(text)
    if got is None:
        # last resort: match option body text
        norm = _norm(text)
        for i, opt in enumerate(q.get("options", [])):
            body = re.sub(r"^[A-Ha-h]\s*[\.、\)）]\s*", "", opt).strip()
            if body and _norm(body) and _norm(body) in norm:
                got = CHOICE_LETTERS[i]
                break
    ok = got is not None and got == expected
    return {
        "score": float(q["points"]) if ok else 0.0,
        "max": float(q["points"]),
        "fraction": 1.0 if ok else 0.0,
        "correct": ok,
        "method": "exact",
        "detail": {"expected": expected, "got": got},
    }


def grade_fill(q: dict, text: str) -> dict:
    points = float(q["points"])
    acceptable = q.get("answers") or [q.get("answer", "")]
    if not isinstance(acceptable, list):
        acceptable = [acceptable]
    final = extract_final_answer(text)
    norm_final = _norm(final)
    norm_all = _norm(text)
    matched = None
    for cand in acceptable:
        nc = _norm(cand)
        if nc and (nc == norm_final or nc == norm_all or nc in norm_all):
            matched = cand
            break
    ok = matched is not None
    detail = {"accepted": acceptable, "got": final[:300], "matched": matched}
    # numeric equivalence: 2 == 2.0 == 2.00
    if not ok:
        expected_num = _to_float(q.get("answer"))
        if expected_num is not None:
            tol = float(q.get("tolerance")) if q.get("tolerance") is not None else 1e-9
            for num in _numbers(final):
                if abs(num - expected_num) <= tol:
                    ok = True
                    detail["matched"] = f"{num:g} == {expected_num:g}"
                    detail["numeric"] = True
                    break
    # explicit numeric tolerance (e.g. 3.14 ± 0.01)
    tolerance = q.get("tolerance")
    if not ok and tolerance is not None:
        expected_num = _to_float(q.get("answer"))
        if expected_num is not None:
            for num in _numbers(final):
                if abs(num - expected_num) <= float(tolerance):
                    ok = True
                    detail["matched"] = f"{num:g} ≈ {expected_num:g} (±{tolerance})"
                    detail["numeric"] = True
                    break
    return {
        "score": points if ok else 0.0,
        "max": points,
        "fraction": 1.0 if ok else 0.0,
        "correct": ok,
        "method": "exact",
        "detail": detail,
    }


def _extract_multi(text: str) -> list[str]:
    cleaned = _strip_markdown(text)
    m = re.search(r"【答案】\s*[:：]?\s*(.+)", cleaned)
    seg = m.group(1) if m else cleaned
    letters = re.findall(r"(?<![A-Za-z])([A-Ha-h])(?![A-Za-z])", seg)
    if not letters:
        letters = re.findall(r"([A-Ha-h])", seg)
    return sorted({x.upper() for x in letters})


def _expected_multi(q: dict) -> list[str]:
    ans = q.get("answer", [])
    if isinstance(ans, (list, tuple)):
        out = []
        for item in ans:
            s = str(item).strip()
            m = re.match(r"^\s*[\(\（]?\s*([A-Ha-h])", s)
            if m:
                out.append(m.group(1).upper())
            else:
                out.extend(x.upper() for x in re.findall(r"[A-Ha-h]", s))
        return sorted(set(out))
    s = str(ans)
    letters = re.findall(r"[A-Ha-h]", s)
    if letters:
        return sorted({x.upper() for x in letters})
    out = []
    for i, opt in enumerate(q.get("options", [])):
        body = re.sub(r"^[A-Ha-h]\s*[\.、\)）]\s*", "", opt).strip()
        if body and _norm(body) in _norm(s):
            out.append(CHOICE_LETTERS[i])
    return out


def grade_multi(q: dict, text: str) -> dict:
    """Multiple-select with partial credit: (hits - wrong_hits) / #correct."""
    points = float(q["points"])
    expected = set(_expected_multi(q))
    selected = set(_extract_multi(text))
    if not expected:
        return {
            "score": None, "max": points, "fraction": None, "correct": None,
            "method": "multi", "detail": {"error": "multi question has no answer"},
        }
    hit = len(expected & selected)
    wrong = len(selected - expected)
    frac = max(0.0, (hit - wrong) / len(expected))
    ok = selected == expected
    return {
        "score": round(points * frac, 4),
        "max": points,
        "fraction": round(frac, 4),
        "correct": ok,
        "method": "multi",
        "detail": {"expected": sorted(expected), "got": sorted(selected),
                   "correct_hits": hit, "wrong_hits": wrong},
    }


def _parse_bool(value) -> str | None:
    n = _norm(value)
    if n in TRUE_TOKENS:
        return "T"
    if n in FALSE_TOKENS:
        return "F"
    for tok in TRUE_TOKENS:
        if tok and n.startswith(tok):
            return "T"
    for tok in FALSE_TOKENS:
        if tok and n.startswith(tok):
            return "F"
    return None


def grade_judge(q: dict, text: str) -> dict:
    points = float(q["points"])
    expected = _parse_bool(q.get("answer", ""))
    cleaned = _strip_markdown(text)
    m = re.search(r"【答案】\s*[:：]?\s*(.+)", cleaned)
    seg = m.group(1) if m else cleaned
    got = _parse_bool(seg)
    ok = expected is not None and got == expected
    return {
        "score": points if ok else 0.0,
        "max": points,
        "fraction": 1.0 if ok else 0.0,
        "correct": ok,
        "method": "exact",
        "detail": {"expected": expected, "got": got},
    }


# ---------------------------------------------------------------- code


def extract_code(text: str) -> str:
    m = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, flags=re.S)
    if m:
        return m.group(1).strip("\n")
    m = re.search(r"(def\s+[A-Za-z_]\w*\s*\(.*)", text, flags=re.S)
    if m:
        return m.group(1).strip()
    return text.strip()


_HARNESS = r'''
import json as _json
import sys as _sys
with open(_sys.argv[1], encoding="utf-8") as _fh:
    _TESTS = _json.load(_fh)
_RESULTS = []
_PASSED = 0
for _t in _TESTS:
    try:
        _got = eval(_t["call"], globals())
        _exp = _t["expected"]
        _ok = _got == _exp
        if (not _ok) and _t.get("unordered") and isinstance(_got, list) and isinstance(_exp, list):
            try:
                _ok = sorted(_got) == sorted(_exp)
            except Exception:
                _ok = False
        _RESULTS.append({"call": _t["call"], "expected": _exp,
                         "got": _got, "ok": bool(_ok)})
        _PASSED += 1 if _ok else 0
    except Exception as _e:
        _RESULTS.append({"call": _t.get("call"), "error": repr(_e), "ok": False})
print("__RESULT__" + _json.dumps(
    {"passed": _PASSED, "total": len(_TESTS), "cases": _RESULTS},
    ensure_ascii=False, default=str))
'''


def _exec_code_sample(code: str, tests: list, timeout: int) -> dict:
    """Run one code sample against the test cases; return a raw result dict."""
    source = code + "\n\n" + _HARNESS
    code_path = None
    tests_path = None
    total = len(tests)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False, encoding="utf-8") as fh:
            fh.write(source)
            code_path = fh.name
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as fh:
            json.dump(tests, fh, ensure_ascii=False, default=str)
            tests_path = fh.name
        proc = subprocess.run(
            [sys.executable, code_path, tests_path],
            capture_output=True, text=True, timeout=timeout,
        )
        out = proc.stdout or ""
        marker = out.rfind("__RESULT__")
        if marker == -1:
            return {"passed": 0, "total": total, "fraction": 0.0, "cases": [],
                    "error": "no result marker", "stdout": out[-1200:],
                    "stderr": (proc.stderr or "")[-1200:]}
        data = json.loads(out[marker + len("__RESULT__"):].strip())
        n = max(1, int(data.get("total", total or 1)))
        passed = int(data.get("passed", 0))
        return {"passed": passed, "total": n, "fraction": round(passed / n, 4),
                "cases": data.get("cases", []), "stderr": (proc.stderr or "")[-800:]}
    except subprocess.TimeoutExpired:
        return {"passed": 0, "total": total, "fraction": 0.0, "cases": [],
                "error": f"timeout after {timeout}s"}
    except Exception as exc:  # noqa: BLE001
        return {"passed": 0, "total": total, "fraction": 0.0, "cases": [],
                "error": repr(exc)}
    finally:
        for p in (code_path, tests_path):
            if p and os.path.exists(p):
                os.unlink(p)


def _pass_at_k(n: int, c: int, k: int) -> float:
    """Unbiased pass@k estimator: 1 - C(n-c, k) / C(n, k)."""
    if k <= 0:
        return 0.0
    if n < k:
        return 1.0 if c > 0 else 0.0
    if n - c < k:
        return 1.0
    return 1.0 - comb(n - c, k) / comb(n, k)


def grade_code(q: dict, text, allow_exec: bool = True, timeout: int = 15) -> dict:
    """Grade one or several code samples.

    `text` may be a single completion or a list of completions (pass@k).
    Cases are `test_cases` (public) plus optional `hidden_cases`.
    With a single sample the score keeps partial credit by case pass ratio;
    with multiple samples the score uses the pass@k estimate.
    """
    points = float(q["points"])
    samples = [text] if isinstance(text, str) else list(text)
    visible = list(q.get("test_cases", []))
    hidden = list(q.get("hidden_cases", []))
    cases = visible + hidden
    if not allow_exec:
        return {
            "score": None, "max": points, "fraction": None, "correct": None,
            "method": "tests", "detail": {"error": "code execution disabled",
                                          "visible_cases": len(visible),
                                          "hidden_cases": len(hidden)},
        }
    if not cases:
        return {
            "score": None, "max": points, "fraction": None, "correct": None,
            "method": "tests", "detail": {"error": "no test cases"},
        }

    runs = []
    for s in samples:
        code = extract_code(s)
        r = _exec_code_sample(code, cases, timeout)
        r["ok"] = r.get("total", 0) > 0 and r.get("fraction", 0.0) >= 1.0
        r["code"] = code
        runs.append(r)

    n = len(runs)
    passed_all = sum(1 for r in runs if r["ok"])
    if n == 0:
        return {"score": None, "max": points, "fraction": None, "correct": None,
                "method": "tests", "detail": {"error": "no samples"}}

    if n == 1:
        frac = runs[0].get("fraction", 0.0)
        method = "tests"
    else:
        frac = _pass_at_k(n, passed_all, n)
        method = "tests+pass@k"

    best = max(runs, key=lambda r: r.get("fraction", 0.0))
    detail = {
        "samples": n,
        "passed_all": passed_all,
        "pass_rate": round(passed_all / n, 4),
        "pass_at_k": round(frac, 4) if n > 1 else None,
        "visible_cases": len(visible),
        "hidden_cases": len(hidden),
        "cases": best.get("cases", []),
        "stderr": best.get("stderr", ""),
    }
    if n > 1:
        detail["sample_runs"] = [
            {"ok": r["ok"], "passed": r.get("passed", 0),
             "total": r.get("total", len(cases)), "error": r.get("error"),
             "stderr": r.get("stderr", ""), "code": r.get("code", "")[:1500]}
            for r in runs
        ]
    if best.get("error"):
        detail["error"] = best["error"]

    return {
        "score": round(points * frac, 4),
        "max": points,
        "fraction": round(frac, 4),
        "correct": passed_all == n and n > 0,
        "method": method,
        "detail": detail,
    }


# ---------------------------------------------------------------- subjective


JUDGE_SYSTEM = (
    "你是一位严谨、公正的阅卷老师。你会收到题目、评分要点、参考答案和考生作答。"
    "请逐条判断考生是否达成每个评分要点，并给出 0 到 1 的达成度（可用 0、0.5、1 或两位小数）。"
    "只输出 JSON，不要输出任何其他文字。"
)

JUDGE_TEMPLATE = """【题目】
{question}

【评分要点】
{rubric}

【参考答案 / 参考解析】
{reference}

【考生作答】
{answer}

请严格按下面的 JSON 结构输出（不要加代码块标记），每条 reason 不超过 30 字：
{{"points": [{{"point": "要点原文", "score": 0.0, "reason": "判断依据"}}], "total_comment": "整体评语"}}
"""


def _extract_json(text: str) -> dict | None:
    text = _strip_markdown(text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    for candidate in (text[start:end + 1],):
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def _salvage_scores(text: str) -> list[float]:
    """Recover per-point scores when the judge JSON got truncated."""
    vals = re.findall(r'"score"\s*:\s*([0-9]+(?:\.[0-9]+)?)', text or "")
    out = []
    for v in vals:
        try:
            out.append(max(0.0, min(1.0, float(v))))
        except ValueError:
            continue
    return out


def _judge_call(judge_client, judge_model: str, prompt: str, retries: int = 2):
    last_exc = None
    for attempt in range(retries + 1):
        try:
            resp = judge_client.chat(
                [{"role": "system", "content": JUDGE_SYSTEM},
                 {"role": "user", "content": prompt}],
                temperature=0.0,
                model=judge_model or None,
            )
            raw = resp["content"]
            return raw, _extract_json(raw)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


def _rubric_text(rubric: list[str]) -> str:
    return "\n".join(f"{i + 1}. {r}" for i, r in enumerate(rubric))


def _clamp_score(value) -> float:
    try:
        s = float(value)
    except (TypeError, ValueError):
        s = 0.0
    return max(0.0, min(1.0, s))


def _fit_scores(scores: list[float], n: int) -> list[float]:
    out = list(scores[:n])
    while len(out) < n:
        out.append(0.0)
    return out


def grade_subjective(q: dict, text: str, judge_client, judge_model: str = "",
                     debias: bool = False, candidate_model: str = "") -> dict:
    """Grade a free-form answer with an LLM judge.

    debias=True judges twice with the rubric order reversed (order-bias control)
    and averages the two passes, recording their agreement.
    """
    points = float(q["points"])
    rubric = q.get("rubric") or []
    if not rubric:
        rubric = ["作答内容正确、完整，逻辑清晰"]
    self_judge = bool(candidate_model and judge_model
                      and _norm(candidate_model) == _norm(judge_model))
    meta = {"rubric": rubric, "judge_model": judge_model,
            "self_judge": self_judge, "debias": bool(debias)}

    if judge_client is None:
        return {
            "score": None, "max": points, "fraction": None, "correct": None,
            "method": "judge", "detail": {**meta, "error": "judge disabled"},
        }

    base = dict(question=q["question"], reference=q.get("reference", "（无）"),
                answer=(text or "")[:4000])
    prompt = JUDGE_TEMPLATE.format(rubric=_rubric_text(rubric), **base)
    try:
        raw1, parsed1 = _judge_call(judge_client, judge_model, prompt)
    except Exception as exc:  # noqa: BLE001
        return {
            "score": None, "max": points, "fraction": None, "correct": None,
            "method": "judge", "detail": {**meta, "error": f"judge call failed: {exc}"},
        }

    if not parsed1 or "points" not in parsed1:
        salvaged = _salvage_scores(raw1)
        if salvaged:
            parsed1 = {
                "points": [{"point": r, "score": s, "reason": ""}
                           for r, s in zip(rubric, salvaged)],
                "total_comment": "",
            }
        else:
            return {
                "score": None, "max": points, "fraction": None, "correct": None,
                "method": "judge",
                "detail": {**meta, "error": "judge returned unparsable JSON",
                           "raw": raw1[:1200]},
            }

    got1 = parsed1.get("points") or []
    scores1 = _fit_scores([_clamp_score(p.get("score")) for p in got1], len(rubric))

    pass2_scores = None
    agreement = None
    if debias and len(rubric) > 1:
        rev = list(reversed(rubric))
        prompt2 = JUDGE_TEMPLATE.format(rubric=_rubric_text(rev), **base)
        try:
            _raw2, parsed2 = _judge_call(judge_client, judge_model, prompt2)
            if parsed2 and "points" in parsed2:
                rev_scores = _fit_scores(
                    [_clamp_score(p.get("score")) for p in (parsed2.get("points") or [])],
                    len(rev))
                pass2_scores = list(reversed(rev_scores))
                diffs = [abs(a - b) for a, b in zip(scores1, pass2_scores)]
                agreement = round(1.0 - sum(diffs) / len(diffs), 4)
        except Exception:  # noqa: BLE001
            pass2_scores = None

    if pass2_scores is not None:
        combined = [(a + b) / 2.0 for a, b in zip(scores1, pass2_scores)]
    else:
        combined = scores1
    frac = (sum(combined) / len(combined)) if combined else 0.0

    detail = {
        **meta,
        "point_scores": got1,
        "comment": parsed1.get("total_comment", ""),
        "raw": raw1[:2000],
        "agreement": agreement,
    }
    if pass2_scores is not None:
        detail["pass2_scores"] = pass2_scores

    return {
        "score": round(points * frac, 4),
        "max": points,
        "fraction": round(frac, 4),
        "correct": frac >= 0.6,
        "method": "judge",
        "detail": detail,
    }


# ---------------------------------------------------------------- dispatch


def grade_question(q: dict, text: str, judge_client=None,
                   judge_model: str = "", allow_code_exec: bool = True,
                   judge_debias: bool = False, candidate_model: str = "") -> dict:
    qtype = q["type"]
    if qtype == "choice":
        return grade_choice(q, text)
    if qtype == "multi":
        return grade_multi(q, text)
    if qtype == "judge":
        return grade_judge(q, text)
    if qtype == "fill":
        return grade_fill(q, text)
    if qtype == "code":
        return grade_code(q, text, allow_exec=allow_code_exec)
    if qtype in ("solution", "interview"):
        return grade_subjective(q, text, judge_client, judge_model,
                                debias=judge_debias, candidate_model=candidate_model)
    raise ValueError(f"unknown question type {qtype}")
