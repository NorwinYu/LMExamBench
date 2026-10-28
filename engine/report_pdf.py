"""Render a run record as a PDF using Pillow (CJK font, multi-page).

No third-party PDF library is available in this environment, so pages are
rendered with Pillow's built-in PDF writer. Text is rasterized (not selectable)
but the output is a real, multi-page PDF.
"""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

DPI = 150
W, H = 1240, 1754          # A4 at 150 DPI
MARGIN = 64
CONTENT_W = W - 2 * MARGIN

FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"

INK = (31, 41, 55)
MUTED = (107, 114, 128)
ACCENT = (37, 99, 235)
LINE = (226, 232, 240)

TYPE_LABEL = {"choice": "选择", "multi": "多选", "judge": "判断", "fill": "填空",
              "solution": "解答", "interview": "面试", "code": "编程"}


def _fmt(v) -> str:
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return str(round(v, 2))
    return "-"


def _clip(text, n=800) -> str:
    s = str(text if text is not None else "")
    return s if len(s) <= n else s[:n] + " …"


def _font(size: int, bold: bool = False):
    path = FONT_BOLD if bold else FONT_REG
    return ImageFont.truetype(path, size, index=0)


def _wrap(text, font, width: int) -> list[str]:
    lines: list[str] = []
    for para in str(text if text is not None else "").split("\n"):
        if not para:
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if font.getlength(cur + ch) <= width:
                cur += ch
            else:
                if cur:
                    lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
    return lines


class PdfDoc:
    def __init__(self) -> None:
        self.pages: list[Image.Image] = []
        self.new_page()

    def new_page(self) -> None:
        self.img = Image.new("RGB", (W, H), "white")
        self.draw = ImageDraw.Draw(self.img)
        self.pages.append(self.img)
        self.y = MARGIN

    def ensure(self, h: int) -> None:
        if self.y + h > H - MARGIN - 24:
            self.new_page()

    def text(self, text, size: int = 14, bold: bool = False, color=INK,
             indent: int = 0, spacing: int = 4, width: int | None = None) -> None:
        text = str(text if text is not None else "")
        if not text:
            return
        font = _font(size, bold)
        w = (CONTENT_W if width is None else width) - indent
        for line in _wrap(text, font, w):
            lh = size + 6
            self.ensure(lh)
            if line:
                self.draw.text((MARGIN + indent, self.y), line, font=font, fill=color)
            self.y += lh
        self.y += spacing

    def heading(self, text: str, size: int = 20) -> None:
        self.y += 6
        self.ensure(size + 10)
        self.text(text, size=size, bold=True, spacing=6)
        self.rule()

    def rule(self) -> None:
        self.ensure(6)
        self.draw.line([(MARGIN, self.y), (W - MARGIN, self.y)], fill=LINE, width=1)
        self.y += 6

    def finish(self) -> bytes:
        foot = _font(11)
        for i, img in enumerate(self.pages):
            d = ImageDraw.Draw(img)
            label = f"LMExamBench · 第 {i + 1} / {len(self.pages)} 页"
            tw = foot.getlength(label)
            d.text((W - MARGIN - tw, H - 36), label, font=foot, fill=MUTED)
        buf = io.BytesIO()
        first, rest = self.pages[0], self.pages[1:]
        first.save(buf, "PDF", save_all=True, append_images=rest, resolution=DPI)
        return buf.getvalue()


def _grading_lines(g: dict) -> list[str]:
    if not g:
        return []
    method = g.get("method")
    detail = g.get("detail") or {}
    out: list[str] = []
    if method == "judge":
        for i, p in enumerate(detail.get("point_scores") or []):
            reason = _clip(p.get("reason"), 120)
            out.append(f"{i + 1}. [{_fmt(p.get('score'))}] {_clip(p.get('point'), 70)}"
                       + (f" — {reason}" if reason else ""))
        if detail.get("comment"):
            out.append("评语：" + _clip(detail["comment"], 200))
        meta = []
        if detail.get("judge_model"):
            meta.append("裁判：" + str(detail["judge_model"]))
        if detail.get("debias"):
            meta.append("双向判分")
        if detail.get("self_judge"):
            meta.append("⚠ 裁判与被测同模型")
        if meta:
            out.append("　".join(meta))
    elif method and str(method).startswith("tests"):
        if detail.get("samples") and detail["samples"] > 1:
            out.append(f"pass@{detail['samples']}：{detail.get('pass_at_k')}　"
                       f"通过 {detail.get('passed_all')}/{detail.get('samples')}")
        for c in (detail.get("cases") or []):
            out.append(f"[{'PASS' if c.get('ok') else 'FAIL'}] "
                       f"{_clip(c.get('call'), 70)} → {_clip(c.get('got'), 50)}")
    else:
        if detail.get("expected") is not None:
            out.append(f"预期：{detail.get('expected')}　实际：{detail.get('got')}")
        if detail.get("accepted") is not None:
            out.append("可接受：" + " / ".join(map(str, detail.get("accepted") or []))
                       + f"　实际：{detail.get('got')}")
    if detail.get("error"):
        out.append("错误：" + _clip(detail["error"], 200))
    return out


def render_report_pdf(record: dict) -> bytes:
    cfg = record.get("config") or {}
    model = (cfg.get("model") or {}).get("name", "")
    summary = record.get("summary") or {}
    ov = summary.get("overall") or {}
    doc = PdfDoc()

    doc.text("LMExamBench 评测报告", size=30, bold=True, spacing=8)
    meta = (f"运行 {record.get('id')} · 模型 {model} · "
            f"{record.get('created_at') or ''} · 状态 {record.get('status') or ''}")
    profile = record.get("profile") or cfg.get("profile") or {}
    if profile.get("id"):
        meta += f" · 方案 {profile.get('name') or profile.get('id')} / {profile.get('level') or ''}"
    doc.text(meta, size=12, color=MUTED, spacing=10)
    doc.rule()

    if ov:
        grade = ov.get("grade") or {}
        doc.text(f"{_fmt(ov.get('weighted_percent'))} 分 · {grade.get('letter', '')} {grade.get('label', '')}",
                 size=24, bold=True, color=ACCENT, spacing=4)
        doc.text(f"原始得分率 {_fmt(ov.get('percent'))}%　覆盖率 {round((ov.get('coverage') or 0) * 100)}%　"
                 f"已评/总数 {ov.get('graded_n')}/{ov.get('n')}", size=12, color=MUTED, spacing=12)

    if summary.get("stages"):
        doc.heading("各阶段成绩", size=18)
        for s in summary["stages"]:
            flag = "（岗位加权）" if s.get("role_weighted") else ""
            doc.text(f"{s.get('name')}：{_fmt(s.get('percent'))}%　"
                     f"得分 {_fmt(s.get('earned'))}/{_fmt(s.get('graded_total'))}　"
                     f"权重 {_fmt(s.get('weight'))}{flag}", size=13, spacing=3)

    if summary.get("subjects"):
        doc.heading("学科细分", size=18)
        for x in summary["subjects"]:
            doc.text(f"{x.get('stage')} · {x.get('subject')}：{_fmt(x.get('percent'))}%　"
                     f"({_fmt(x.get('earned'))}/{_fmt(x.get('graded_total'))})", size=12, spacing=2)

    if summary.get("roles"):
        doc.heading("面试岗位", size=18)
        for x in summary["roles"]:
            doc.text(f"{x.get('role')}：{_fmt(x.get('percent'))}%　"
                     f"({_fmt(x.get('earned'))}/{_fmt(x.get('graded_total'))})", size=12, spacing=2)

    if summary.get("capabilities"):
        doc.heading("能力维度", size=18)
        for c in summary["capabilities"]:
            doc.text(f"{c.get('capability')}：{_fmt(c.get('percent'))}%", size=12, spacing=2)

    paper = record.get("paper") or {}
    if paper.get("sections"):
        doc.heading(f"试卷结构（每部分最多 {paper.get('per_section')} 题）", size=18)
        for sec in paper["sections"]:
            doc.text(f"{sec.get('stage')} · {sec.get('section')}："
                     f"{sec.get('count')} 题 / {_fmt(sec.get('points'))} 分", size=12, spacing=2)

    by_stage: dict = {}
    for r in record.get("results") or []:
        by_stage.setdefault(r.get("stage"), []).append(r)
    stage_names = {s.get("id"): s.get("name") for s in (summary.get("stages") or [])}
    for sid, recs in by_stage.items():
        doc.heading(f"逐题明细 · {stage_names.get(sid, sid)}", size=18)
        for r in recs:
            g = r.get("grading") or {}
            doc.text(f"{r.get('id')}  ·  {TYPE_LABEL.get(r.get('type'), r.get('type'))}  ·  "
                     f"{r.get('subject') or ''} / {r.get('chapter') or ''} / {r.get('topic') or ''}  ·  "
                     f"得分 {_fmt(g.get('score'))}/{_fmt(g.get('max'))}",
                     size=14, bold=True, spacing=2)
            doc.text("题目：" + _clip(r.get("question"), 500), size=12, indent=14, spacing=2)
            if r.get("model_output"):
                doc.text("作答：" + _clip(r["model_output"], 1400), size=11,
                         indent=14, color=(55, 65, 81), spacing=2)
            for line in _grading_lines(g):
                doc.text(line, size=11, indent=14, color=(75, 85, 99), spacing=1)
            if r.get("reference"):
                doc.text("参考：" + _clip(r["reference"], 500), size=10, indent=14,
                         color=MUTED, spacing=4)
            doc.rule()

    return doc.finish()
