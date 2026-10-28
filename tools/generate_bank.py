#!/usr/bin/env python3
"""Procedurally generate drill questions whose answers are computed from formulas.

Every generated question carries `chapter` (章节) and `topic` (考点) so coverage is
fine-grained and auditable. Answers are derived in code, so they are correct by
construction. Run: python3 tools/generate_bank.py
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BANK = os.path.join(ROOT, "bank")


def load(stage: str) -> dict:
    with open(os.path.join(BANK, f"{stage}.json"), encoding="utf-8") as fh:
        return json.load(fh)


def load_clean(stage: str) -> dict:
    data = load(stage)
    data["questions"] = [q for q in data["questions"] if "-drill-" not in q["id"]]
    return data


def save(stage: str, data: dict) -> None:
    with open(os.path.join(BANK, f"{stage}.json"), "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def add(qs: list, stage: str, subject: str, chapter: str, topic: str, qtype: str,
        diff: str, caps: list, question: str, answer: str, reference: str,
        points: int = 5, options=None, answers=None) -> None:
    q = {
        "id": f"{stage}-drill-{len(qs) + 1:04d}",
        "subject": subject, "chapter": chapter, "topic": topic,
        "type": qtype, "difficulty": diff,
        "format": {"choice": "单选", "fill": "填空", "judge": "判断"}.get(qtype, "计算题"),
        "source_style": "参数化生成题（原创，答案由公式计算）",
        "capabilities": caps, "tags": [topic],
        "question": question, "answer": answer, "reference": reference,
        "points": points,
    }
    if options is not None:
        q["options"] = options
    if answers is not None:
        q["answers"] = answers
    qs.append(q)


def build_primary() -> None:
    data = load_clean("primary")
    qs = []
    # 加法
    for i, (a, b) in enumerate([(12 + 3 * i, 7 + 2 * i) for i in range(30)]):
        add(qs, "primary", "数学", "数与代数", "加法", "fill", "easy", ["计算"],
            f"计算：{a} + {b} = ____。", str(a + b), f"{a} + {b} = {a + b}。")
    # 乘法
    for i in range(30):
        a, b = 2 + i % 10, 2 + (i * 3) % 9
        add(qs, "primary", "数学", "数与代数", "乘法", "fill", "easy", ["计算"],
            f"计算：{a} × {b} = ____。", str(a * b), f"{a} × {b} = {a * b}。")
    # 除法
    for i in range(30):
        b, c = 2 + i % 8, 2 + (i * 2) % 9
        a = b * c
        add(qs, "primary", "数学", "数与代数", "除法", "fill", "easy", ["计算"],
            f"计算：{a} ÷ {b} = ____。", str(c), f"{a} ÷ {b} = {c}。")
    # 购物找零
    for i in range(30):
        a, b = 2 + i % 6, 3 + i % 7
        paid = a * b + 5 + i % 10
        add(qs, "primary", "数学", "应用题", "购物找零", "fill", "easy", ["计算", "理解"],
            f"小明买了 {a} 本单价 {b} 元的笔记本，付了 {paid} 元，应找回多少元？",
            str(paid - a * b), f"总价 {a}×{b}={a*b} 元，找回 {paid}−{a*b}={paid-a*b} 元。")
    # 长方形面积
    for i in range(30):
        a, b = 3 + i % 9, 4 + (i * 2) % 8
        add(qs, "primary", "数学", "图形与几何", "长方形面积", "fill", "easy", ["计算"],
            f"一个长方形长 {a} 厘米、宽 {b} 厘米，面积是多少平方厘米？",
            str(a * b), f"面积 = 长×宽 = {a}×{b} = {a*b} 平方厘米。")
    # 速度路程
    for i in range(30):
        v, t = 30 + i % 8 * 10, 2 + i % 7
        add(qs, "primary", "数学", "应用题", "路程问题", "fill", "easy", ["计算"],
            f"一辆汽车以每小时 {v} 千米行驶 {t} 小时，行驶多少千米？",
            str(v * t), f"路程 = 速度×时间 = {v}×{t} = {v*t} 千米。")
    data["questions"].extend(qs)
    save("primary", data)


def build_junior() -> None:
    data = load_clean("junior")
    qs = []
    # 一元一次方程
    for i in range(28):
        a, b = 2 + i % 7, 1 + i % 9
        x = 2 + (i * 3) % 11
        c = a * x + b
        add(qs, "junior", "数学", "方程与不等式", "一元一次方程", "fill", "medium", ["计算"],
            f"解方程：{a}x + {b} = {c}，x = ____。", str(x),
            f"{a}x = {c}−{b} = {c-b}，x = {c-b}÷{a} = {x}。")
    # 勾股定理
    for i in range(28):
        k = 1 + i % 12
        add(qs, "junior", "数学", "图形与几何", "勾股定理", "fill", "medium", ["计算"],
            f"直角三角形两直角边分别为 {3*k} 和 {4*k}，斜边长是多少？", str(5 * k),
            f"斜边 = √((3k)²+(4k)²) = 5k = {5*k}。")
    # 密度
    for i in range(28):
        m, V = 200 + i * 10, 100 + (i % 5) * 50
        rho = m / V
        add(qs, "junior", "物理", "物质与密度", "密度", "fill", "medium", ["计算"],
            f"物体质量 {m} g、体积 {V} cm³，密度是多少 g/cm³？（保留两位）",
            f"{rho:.2f}", f"ρ = m/V = {m}/{V} ≈ {rho:.2f} g/cm³。",
            answers=[f"{rho:.2f}"])
    # 速度
    for i in range(28):
        s, t = 100 + i * 10, 5 + i % 10
        v = s / t
        add(qs, "junior", "物理", "运动与力", "速度", "fill", "medium", ["计算"],
            f"物体在 {t} 秒内运动 {s} 米，平均速度是多少 m/s？（保留两位）",
            f"{v:.2f}", f"v = s/t = {s}/{t} ≈ {v:.2f} m/s。", answers=[f"{v:.2f}"])
    # 电功率
    for i in range(28):
        U, R = 110 + i * 5, 11 + i % 20
        P = U * U / R
        add(qs, "junior", "物理", "电学", "电功率", "fill", "medium", ["计算"],
            f"电阻两端电压 {U} V、阻值 {R} Ω，电功率是多少 W？（保留两位）",
            f"{P:.2f}", f"P = U²/R = {U}²/{R} ≈ {P:.2f} W。", answers=[f"{P:.2f}"])
    # 折扣
    for i in range(28):
        p, d = 100 + i * 10, 10 + (i % 6) * 10
        price = p * (100 - d) / 100
        add(qs, "junior", "数学", "应用题", "折扣", "fill", "medium", ["计算"],
            f"一件商品原价 {p} 元，打 {d/10:.1f} 折，现价多少元？",
            f"{price:.1f}", f"现价 = {p}×(1−{d}%) = {price:.1f} 元。", answers=[f"{price:.1f}"])
    data["questions"].extend(qs)
    save("junior", data)


def build_senior() -> None:
    data = load_clean("senior")
    qs = []
    # 二次函数最值
    for i in range(28):
        a, b = 1 + i % 5, 2 + i % 9
        mn = b - a * a
        add(qs, "senior", "数学", "函数", "二次函数最值", "fill", "medium", ["计算", "推理"],
            f"函数 f(x)=x²−{2*a}x+{b} 的最小值是 ____。", str(mn),
            f"配方得 (x−{a})²+{mn}，最小值为 {mn}。")
    # 等差数列
    for i in range(28):
        a1, d, k = 1 + i % 5, 1 + i % 4, 5 + i % 10
        val = a1 + (k - 1) * d
        add(qs, "senior", "数学", "数列", "等差数列", "fill", "medium", ["计算"],
            f"等差数列首项 {a1}、公差 {d}，第 {k} 项是多少？", str(val),
            f"a_k = {a1}+({k}−1)×{d} = {val}。")
    # 等比数列
    for i in range(28):
        a1, r, k = 1 + i % 4, 2 + i % 3, 3 + i % 5
        val = a1 * r ** (k - 1)
        add(qs, "senior", "数学", "数列", "等比数列", "fill", "medium", ["计算"],
            f"等比数列首项 {a1}、公比 {r}，第 {k} 项是多少？", str(val),
            f"a_k = {a1}×{r}^({k}−1) = {val}。")
    # 导数
    for i in range(28):
        a, b, c = 1 + i % 4, 1 + i % 5, 1 + i % 7
        add(qs, "senior", "数学", "导数", "多项式求导", "fill", "medium", ["计算"],
            f"函数 f(x)={a}x³+{b}x²+{c}x 的导数是 ____。",
            f"{3*a}x²+{2*b}x+{c}", f"逐项求导：{3*a}x²+{2*b}x+{c}。")
    # 自由落体
    for i in range(28):
        h = 5 * (i + 1) ** 2
        v = (20 * h) ** 0.5
        add(qs, "senior", "物理", "运动学", "自由落体", "fill", "hard", ["计算"],
            f"物体从 {h} m 高处自由下落（g=10），落地速度多少 m/s？",
            f"{v:.1f}", f"v=√(2gh)=√(20×{h})≈{v:.1f} m/s。", answers=[f"{v:.1f}", f"{v:g}"])
    # 串联电阻
    for i in range(28):
        r1, r2 = 2 + i % 10, 3 + i % 12
        add(qs, "senior", "物理", "电学", "串联电阻", "fill", "medium", ["计算"],
            f"两个电阻 {r1} Ω 和 {r2} Ω 串联，总电阻是多少 Ω？", str(r1 + r2),
            f"串联总电阻 = {r1}+{r2} = {r1+r2} Ω。")
    data["questions"].extend(qs)
    save("senior", data)


def build_undergrad() -> None:
    data = load_clean("undergrad")
    qs = []
    # 定积分
    for i in range(25):
        k, a = 1 + i % 5, 1 + i % 6
        val = k * a * a / 2
        add(qs, "undergrad", "高等数学", "积分", "定积分", "fill", "medium", ["计算"],
            f"计算 ∫₀^{a} {k}x dx = ____。", f"{val:g}",
            f"原函数 {k}x²/2，代入得 {k}×{a}²/2 = {val:g}。", answers=[f"{val:g}"])
    # 行列式
    for i in range(25):
        a, b, c, d = 1 + i % 5, 1 + i % 4, 1 + i % 6, 1 + i % 7
        val = a * d - b * c
        add(qs, "undergrad", "线性代数", "行列式", "二阶行列式", "fill", "medium", ["计算"],
            f"计算行列式 |{a} {b}; {c} {d}| = ____。", str(val),
            f"ad−bc = {a}×{d}−{b}×{c} = {val}。")
    # 古典概率
    for i in range(25):
        r, w = 1 + i % 6, 1 + i % 7
        add(qs, "undergrad", "概率论", "概率", "古典概型", "fill", "medium", ["计算"],
            f"袋中 {r} 红 {w} 白，任取 1 个，取到红球的概率是多少？",
            f"{r}/{r+w}", f"P = {r}/({r}+{w}) = {r}/{r+w}。",
            answers=[f"{r}/{r+w}", f"{r/(r+w):.4f}"])
    # 均匀分布期望
    for i in range(25):
        a = 2 + i % 9
        add(qs, "undergrad", "概率论", "期望", "均匀分布期望", "fill", "medium", ["计算"],
            f"X~U(0,{a})，E[X] = ____。", f"{a/2:g}",
            f"期望 = ({a}+0)/2 = {a/2:g}。", answers=[f"{a/2:g}"])
    # 子网可用主机
    for i in range(25):
        bits = 4 + i % 9
        hosts = 2 ** bits - 2
        add(qs, "undergrad", "计算机网络", "子网", "可用主机数", "fill", "medium", ["计算"],
            f"一个 /{32-bits} 的子网可容纳多少台可用主机？", str(hosts),
            f"主机位 {bits} 位，2^{bits}−2 = {hosts}。")
    # 排列组合
    for i in range(25):
        n = 5 + i % 6
        k = 2 + i % 3
        import math
        val = math.comb(n, k)
        add(qs, "undergrad", "离散数学", "组合", "组合数", "fill", "medium", ["计算"],
            f"计算 C({n},{k}) = ____。", str(val), f"C({n},{k}) = {val}。")
    data["questions"].extend(qs)
    save("undergrad", data)


def build_ruankao() -> None:
    data = load_clean("ruankao")
    qs = []
    # 关键路径
    for i in range(18):
        a, b, c, d = 1 + i % 5, 1 + i % 6, 1 + i % 7, 1 + i % 4
        val = a + max(b, c) + d
        add(qs, "ruankao", "项目管理", "进度管理", "关键路径", "fill", "medium", ["计算"],
            f"活动：A({a}) 无前置；B({b}) 前置 A；C({c}) 前置 A；D({d}) 前置 B、C。关键路径长度是多少天？",
            str(val), f"max({a}+{b}+{d}, {a}+{c}+{d}) = {val} 天。")
    # SPI
    for i in range(18):
        pv, ev = 100 + i * 10, 60 + i * 8
        add(qs, "ruankao", "项目管理", "挣值分析", "SPI", "fill", "medium", ["计算"],
            f"PV={pv}、EV={ev}，SPI 是多少？（保留两位）", f"{ev/pv:.2f}",
            f"SPI = EV/PV = {ev}/{pv} ≈ {ev/pv:.2f}。", answers=[f"{ev/pv:.2f}"])
    # CPI
    for i in range(18):
        ev, ac = 60 + i * 8, 70 + i * 9
        add(qs, "ruankao", "项目管理", "挣值分析", "CPI", "fill", "medium", ["计算"],
            f"EV={ev}、AC={ac}，CPI 是多少？（保留两位）", f"{ev/ac:.2f}",
            f"CPI = EV/AC = {ev}/{ac} ≈ {ev/ac:.2f}。", answers=[f"{ev/ac:.2f}"])
    # RAID5
    for i in range(18):
        n, size = 3 + i % 6, 1 + i % 4
        cap = (n - 1) * size
        add(qs, "ruankao", "系统架构", "存储", "RAID5容量", "fill", "medium", ["计算"],
            f"{n} 块 {size} TB 磁盘组成 RAID5，可用容量约多少 TB？", str(cap),
            f"(N−1)×单盘 = ({n}−1)×{size} = {cap} TB。")
    # 可用性
    for i in range(18):
        mtbf, mttr = 1000 + i * 100, 10 + i % 20
        avail = mtbf / (mtbf + mttr) * 100
        add(qs, "ruankao", "系统架构", "高可用", "可用性", "fill", "medium", ["计算"],
            f"MTBF={mtbf} 小时、MTTR={mttr} 小时，可用性是多少（百分比，两位）？",
            f"{avail:.2f}", f"可用性 = {mtbf}/({mtbf}+{mttr}) ≈ {avail:.2f}%。",
            answers=[f"{avail:.2f}"])
    # 命中率
    for i in range(18):
        h, m = 800 + i * 20, 50 + i * 5
        rate = h / (h + m) * 100
        add(qs, "ruankao", "系统架构", "缓存", "命中率", "fill", "medium", ["计算"],
            f"缓存命中 {h} 次、未命中 {m} 次，命中率是多少（百分比，两位）？",
            f"{rate:.2f}", f"命中率 = {h}/({h}+{m}) ≈ {rate:.2f}%。", answers=[f"{rate:.2f}"])
    data["questions"].extend(qs)
    save("ruankao", data)


def main() -> None:
    build_primary()
    build_junior()
    build_senior()
    build_undergrad()
    build_ruankao()
    for stage in ("primary", "junior", "senior", "undergrad", "ruankao"):
        data = load(stage)
        print(stage, len(data["questions"]))


if __name__ == "__main__":
    main()
