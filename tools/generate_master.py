#!/usr/bin/env python3
"""Generate computational NLP/LLM drill questions for the master track."""
from __future__ import annotations

import json
import math
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "bank")


def load_clean(stage: str) -> dict:
    with open(os.path.join(BANK, f"{stage}.json"), encoding="utf-8") as fh:
        data = json.load(fh)
    data["questions"] = [q for q in data["questions"] if "-drill-" not in q["id"]]
    return data


def save(stage: str, data: dict) -> None:
    with open(os.path.join(BANK, f"{stage}.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def add(qs, stage, subject, chapter, topic, diff, caps, question, answer, reference):
    qs.append({
        "id": f"{stage}-drill-{len(qs) + 1:04d}",
        "subject": subject, "chapter": chapter, "topic": topic,
        "type": "fill", "difficulty": diff, "format": "计算题",
        "source_style": "参数化生成题（原创，答案由公式计算）",
        "capabilities": caps, "tags": [topic],
        "question": question, "answer": answer, "reference": reference,
        "points": 5,
    })


def build_master() -> None:
    data = load_clean("master")
    qs = []
    for i in range(6):
        L, H, d, T = 24 + i * 8, 8 + i * 4, 64 + i * 16, 1024 + i * 512
        gb = 2 * L * H * d * T * 2 / 1e9
        add(qs, "master", "NLP", "推理与显存", "KV Cache", "hard", ["计算", "理解"],
            f"{L} 层、{H} 头、每头 {d} 维、序列长 {T}、fp16 的模型，KV Cache 约多少 GB？（两位小数）",
            f"{gb:.2f}", f"2×{L}×{H}×{d}×{T}×2 字节 ≈ {gb:.2f} GB。")
    for i in range(6):
        r, d = 4 + i * 2, 1024 + i * 512
        params = r * (2 * d)
        add(qs, "master", "NLP", "参数高效微调", "LoRA 参数量", "hard", ["计算"],
            f"对 {d}×{d} 的权重做 rank={r} 的 LoRA，可训练参数约多少个？", str(params),
            f"r×(d_in+d_out) = {r}×{2*d} = {params}。")
    for i in range(6):
        loss = 1.5 + i * 0.5
        ppl = math.exp(loss)
        add(qs, "master", "NLP", "评测", "困惑度", "medium", ["计算"],
            f"验证集平均负对数似然为 {loss:.1f}，困惑度约为多少？（两位小数）",
            f"{ppl:.2f}", f"PPL = exp({loss:.1f}) ≈ {ppl:.2f}。")
    for i in range(6):
        L, d = 12 + i * 4, 512 + i * 128
        params = 12 * L * d * d
        add(qs, "master", "NLP", "模型结构", "参数量估算", "hard", ["计算"],
            f"按 12·L·d² 估算，L={L}、d={d} 的模型参数量约为多少（科学计数法，两位）？",
            f"{params:.2e}", f"12×{L}×{d}² ≈ {params:.2e}。")
    for i in range(6):
        n, d = 512 + i * 256, 32 + i * 16
        flops = 2 * n * n * d
        add(qs, "master", "NLP", "注意力", "注意力 FLOPs", "hard", ["计算"],
            f"n={n}、d={d} 时，单层自注意力 QKᵀ 的 FLOPs 约为多少（2n²d，两位有效数字）？",
            f"{flops:.2e}", f"2×{n}²×{d} ≈ {flops:.2e}。")
    for i in range(6):
        total, chunk, overlap = 8000 + i * 2000, 400 + i * 100, 50 + i * 25
        step = chunk - overlap
        count = math.ceil((total - overlap) / step)
        add(qs, "master", "NLP", "RAG", "切分块数", "medium", ["计算"],
            f"文档 {total} token，chunk {chunk}、重叠 {overlap}，最多切出多少块？", str(count),
            f"步长 {step}，块数 ≈ ⌈({total}−{overlap})/{step}⌉ = {count}。")
    data["questions"].extend(qs)
    save("master", data)


def main() -> None:
    build_master()
    data = load_clean("master")
    print("master", len(data["questions"]))


if __name__ == "__main__":
    main()
