"""Render a run record as a standalone, self-contained HTML report."""
from __future__ import annotations

import html

CSS = """
*{box-sizing:border-box}
body{margin:0;background:#f5f6f8;color:#1f2937;font:14px/1.6 -apple-system,"Segoe UI","PingFang SC",sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:22px;margin:0 0 4px}
h2{font-size:16px;margin:28px 0 10px;border-left:3px solid #2563eb;padding-left:8px}
.meta{color:#6b7280;font-size:12px;margin:0 0 18px}
.hero{display:flex;align-items:center;gap:24px;flex-wrap:wrap;background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:18px 20px}
.big{font-size:40px;font-weight:700;color:#2563eb}
.big small{font-size:16px;color:#6b7280;font-weight:500}
.grade{background:#dbeafe;color:#2563eb;border-radius:999px;padding:3px 12px;font-weight:600}
.stats{display:flex;gap:22px;flex-wrap:wrap}
.stat .k{font-size:11px;color:#6b7280}
.stat .v{font-size:18px;font-weight:600}
table{width:100%;border-collapse:collapse;background:#fff;border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;font-size:13px}
th,td{text-align:left;padding:7px 10px;border-bottom:1px solid #e5e7eb}
th{color:#6b7280;font-size:12px;background:#fafbfc}
.q{background:#fff;border:1px solid #e5e7eb;border-radius:8px;padding:12px 14px;margin-bottom:10px}
.qh{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:6px}
.badge{font-size:11px;background:#eef2ff;color:#3730a3;border-radius:999px;padding:1px 8px}
.chip{font-size:10px;background:#f3f4f6;color:#4b5563;border:1px solid #e5e7eb;border-radius:999px;padding:0 6px}
.score{margin-left:auto;font-weight:600;font-variant-numeric:tabular-nums}
pre{background:#f9fafb;border:1px solid #e5e7eb;border-radius:8px;padding:10px;white-space:pre-wrap;word-break:break-word;font:12px/1.55 ui-monospace,Consolas,monospace;max-height:360px;overflow:auto}
.k{font-size:11px;color:#6b7280;margin:10px 0 4px;letter-spacing:.4px}
.ok{color:#16a34a}.warn{color:#d97706}.bad{color:#dc2626}
"""

TYPE_LABEL = {"choice": "选择", "multi": "多选", "judge": "判断", "fill": "填空",
              "solution": "解答", "interview": "面试", "code": "编程"}
DIFF_LABEL = {"easy": "简单", "medium": "中等", "hard": "困难"}


def _e(v) -> str:
    return html.escape(str(v if v is not None else ""))


def _fmt(n) -> str:
    if isinstance(n, (int, float)) and not isinstance(n, bool):
        return str(round(n, 2))
    return "-"


def _table(headers: list[str], rows: list[list]) -> str:
    out = ["<table><thead><tr>"]
    out += [f"<th>{_e(h)}</th>" for h in headers]
    out.append("</tr></thead><tbody>")
    for row in rows:
        out.append("<tr>" + "".join(f"<td>{_e(c)}</td>" for c in row) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _grading_html(g: dict) -> str:
    if not g:
        return ""
    method = g.get("method")
    detail = g.get("detail") or {}
    parts = []
    if method == "judge":
        pts = detail.get("point_scores") or []
        for i, p in enumerate(pts):
            s = p.get("score", 0)
            parts.append(
                f"<div>{i + 1}. {_e(p.get('point'))} "
                f"<b class='{ 'ok' if (isinstance(s, (int, float)) and s >= 1) else 'warn' }'>"
                f"{_e(s)}</b>"
                + (f" — {_e(p.get('reason'))}" if p.get("reason") else "")
                + "</div>")
        if detail.get("comment"):
            parts.append(f"<div class='k'>评语</div><div>{_e(detail['comment'])}</div>")
        meta = []
        if detail.get("judge_model"):
            meta.append(f"裁判：{detail['judge_model']}")
        if detail.get("debias"):
            meta.append(f"双向判分（一致性 {detail.get('agreement')}）")
        if detail.get("self_judge"):
            meta.append("⚠ 裁判与被测同模型")
        if meta:
            parts.append(f"<div class='k'>{'　'.join(_e(m) for m in meta)}</div>")
    elif method and method.startswith("tests"):
        if detail.get("samples") and detail["samples"] > 1:
            parts.append(f"<div class='k'>pass@{detail['samples']}：{_e(detail.get('pass_at_k'))}"
                         f"　通过样本 {detail.get('passed_all')}/{detail.get('samples')}"
                         f"　可见用例 {detail.get('visible_cases')}"
                         f"　隐藏用例 {detail.get('hidden_cases')}</div>")
        cases = detail.get("cases") or []
        if cases:
            rows = [[c.get("call"), _e(c.get("expected")), _e(c.get("got")),
                     "✅" if c.get("ok") else "❌"] for c in cases]
            parts.append(_table(["用例", "预期", "实际", "结果"], rows))
    else:
        if detail.get("expected") is not None or detail.get("got") is not None:
            parts.append(f"<div class='k'>预期：{_e(detail.get('expected'))}　实际：{_e(detail.get('got'))}</div>")
        if detail.get("accepted") is not None:
            parts.append(f"<div class='k'>可接受：{_e(' / '.join(detail.get('accepted') or []))}"
                         f"　实际：{_e(detail.get('got'))}</div>")
    if detail.get("error"):
        parts.append(f"<div class='bad'>{_e(detail['error'])}</div>")
    return "".join(parts)


def render_report(record: dict) -> str:
    cfg = record.get("config") or {}
    model = (cfg.get("model") or {}).get("name", "")
    summary = record.get("summary") or {}
    ov = summary.get("overall") or {}
    parts = ["<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>",
             f"<title>LMExamBench 报告 {_e(record.get('id'))}</title>",
             f"<style>{CSS}</style></head><body><div class='wrap'>",
             "<h1>LMExamBench 评测报告</h1>",
             f"<p class='meta'>运行 {_e(record.get('id'))} · 模型 {_e(model)} · "
             f"{_e(record.get('created_at'))} · 状态 {_e(record.get('status'))}</p>"]

    if ov:
        grade = ov.get("grade") or {}
        parts.append("<div class='hero'>")
        parts.append(f"<div class='big'>{_fmt(ov.get('weighted_percent'))}<small> 分</small></div>")
        parts.append(f"<div class='grade'>{_e(grade.get('letter'))} · {_e(grade.get('label'))}</div>")
        parts.append("<div class='stats'>")
        for k, v in (("原始得分率", f"{_fmt(ov.get('percent'))}%"),
                     ("覆盖率", f"{round((ov.get('coverage') or 0) * 100)}%"),
                     ("已评/总数", f"{ov.get('graded_n')}/{ov.get('n')}")):
            parts.append(f"<div class='stat'><div class='k'>{k}</div><div class='v'>{_e(v)}</div></div>")
        parts.append("</div></div>")

    if summary.get("stages"):
        parts.append("<h2>各阶段成绩</h2>")
        rows = [[s.get("name"), f"{_fmt(s.get('percent'))}%",
                 f"{_fmt(s.get('earned'))} / {_fmt(s.get('graded_total'))}",
                 _fmt(s.get("weight")),
                 "⚠ 样本不足" if s.get("low_sample") else ""] for s in summary["stages"]]
        parts.append(_table(["阶段", "得分率", "得分 / 满分", "权重", "备注"], rows))

    if summary.get("capabilities"):
        parts.append("<h2>能力画像</h2>")
        rows = [[c.get("capability"), f"{_fmt(c.get('percent'))}%",
                 f"{_fmt(c.get('earned'))} / {_fmt(c.get('graded_total'))}"]
                for c in summary["capabilities"]]
        parts.append(_table(["能力", "得分率", "得分 / 满分"], rows))

    if summary.get("difficulties"):
        parts.append("<h2>难度分层</h2>")
        rows = [[DIFF_LABEL.get(d.get("difficulty"), d.get("difficulty")),
                 f"{_fmt(d.get('percent'))}%",
                 f"{_fmt(d.get('earned'))} / {_fmt(d.get('graded_total'))}",
                 "样本不足" if d.get("low_sample") else ""]
                for d in summary["difficulties"]]
        parts.append(_table(["难度", "得分率", "得分 / 满分", "样本"], rows))

    if summary.get("subjects"):
        parts.append("<h2>学科细分</h2>")
        stage_names = {s.get("id"): s.get("name") for s in (summary.get("stages") or [])}
        rows = [[f"{stage_names.get(x.get('stage'), x.get('stage'))} · {x.get('subject')}",
                 f"{_fmt(x.get('percent'))}%",
                 f"{_fmt(x.get('earned'))} / {_fmt(x.get('graded_total'))}",
                 "样本不足" if x.get("low_sample") else ""] for x in summary["subjects"]]
        parts.append(_table(["学科", "得分率", "得分 / 满分", "样本"], rows))

    if summary.get("roles"):
        parts.append("<h2>面试岗位</h2>")
        rows = [[f"{x.get('role')}", f"{_fmt(x.get('percent'))}%",
                 f"{_fmt(x.get('earned'))} / {_fmt(x.get('graded_total'))}",
                 "样本不足" if x.get("low_sample") else ""] for x in summary["roles"]]
        parts.append(_table(["岗位", "得分率", "得分 / 满分", "样本"], rows))

    if summary.get("rounds"):
        parts.append("<h2>面试轮次</h2>")
        rows = [[f"{x.get('round')}", f"{_fmt(x.get('percent'))}%",
                 f"{_fmt(x.get('earned'))} / {_fmt(x.get('graded_total'))}",
                 "样本不足" if x.get("low_sample") else ""] for x in summary["rounds"]]
        parts.append(_table(["轮次", "得分率", "得分 / 满分", "样本"], rows))

    if summary.get("levels"):
        parts.append("<h2>面试职级</h2>")
        rows = [[f"{x.get('level')}", f"{_fmt(x.get('percent'))}%",
                 f"{_fmt(x.get('earned'))} / {_fmt(x.get('graded_total'))}",
                 "样本不足" if x.get("low_sample") else ""] for x in summary["levels"]]
        parts.append(_table(["职级", "得分率", "得分 / 满分", "样本"], rows))

    if summary.get("profile"):
        p = summary["profile"]
        parts.append("<h2>评估方案</h2>")
        parts.append(f"<p class='meta'>{_e(p.get('name'))} · {_e(p.get('level'))}"
                     + (f"　{_e(p.get('note'))}" if p.get("note") else "") + "</p>")
        rows = [["方案得分", f"{_fmt(p.get('score'))}%"],
                ["阶段加权", f"{_fmt(p.get('stage_score'))}%"],
                ["能力维度", f"{_fmt(p.get('capability_score'))}%"],
                ["岗位维度", f"{_fmt(p.get('role_score'))}%"]]
        parts.append(_table(["指标", "得分率"], rows))

    paper = record.get("paper") or {}
    if paper.get("sections"):
        parts.append(f"<h2>试卷结构（每部分最多 {_fmt(paper.get('per_section'))} 题）</h2>")
        rows = [[f"{sec.get('stage')} · {sec.get('section')}", f"{sec.get('count')} 题",
                 f"{_fmt(sec.get('points'))} 分"] for sec in paper["sections"]]
        parts.append(_table(["部分", "题数", "满分"], rows))

    judge = summary.get("judge") or {}
    if judge.get("model"):
        warn = "（⚠ 与被测同模型）" if judge.get("self_judge") else ""
        parts.append(f"<p class='meta'>主观题裁判：{_e(judge['model'])}{_e(warn)}"
                     f"　双向判分：{'开' if judge.get('debias') else '关'}</p>")

    # per-question details grouped by stage
    by_stage: dict = {}
    for r in record.get("results") or []:
        by_stage.setdefault(r.get("stage"), []).append(r)
    stage_names = {s.get("id"): s.get("name") for s in (summary.get("stages") or [])}
    for sid, recs in by_stage.items():
        parts.append(f"<h2>{_e(stage_names.get(sid, sid))}</h2>")
        for r in recs:
            g = r.get("grading") or {}
            sc = g.get("score")
            parts.append("<div class='q'>")
            chips = "".join(f"<span class='chip'>{_e(c)}</span>"
                            for c in (r.get("capabilities") or []))
            tags = "".join(f"<span class='chip'>{_e(t)}</span>"
                           for t in (r.get("tags") or []))
            parts.append(
                f"<div class='qh'><span class='badge'>{_e(TYPE_LABEL.get(r.get('type'), r.get('type')))}</span>"
                f"<code>{_e(r.get('id'))}</code><span class='meta'>{_e(r.get('subject'))}</span>"
                f"{chips}{tags}<span class='score'>{_fmt(sc)} / {_fmt(g.get('max'))}</span></div>")
            parts.append(f"<div class='k'>题目</div><pre>{_e(r.get('question'))}</pre>")
            if r.get("options"):
                parts.append("<div class='k'>选项</div><div>" +
                             "<br>".join(_e(o) for o in r["options"]) + "</div>")
            if r.get("model_output"):
                parts.append(f"<div class='k'>模型作答</div><pre>{_e(r['model_output'])}</pre>")
            gh = _grading_html(g)
            if gh:
                parts.append(f"<div class='k'>判分</div>{gh}")
            if r.get("reference"):
                parts.append(f"<div class='k'>参考答案 / 解析</div><pre>{_e(r['reference'])}</pre>")
            parts.append("</div>")

    parts.append("</div></body></html>")
    return "".join(parts)
