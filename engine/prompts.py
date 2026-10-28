"""Prompt templates per question type."""
from __future__ import annotations

SYSTEM_PROMPT = (
    "你是一位正在参加考试或面试的考生。请独立作答，不要请求澄清，不要反问。"
    "回答要准确、完整；数学和推理题请展示必要的步骤。"
)


def build_user_prompt(q: dict) -> str:
    qtype = q["type"]

    if qtype == "choice":
        opts = "\n".join(q.get("options", []))
        return (
            f"请作答下面的单项选择题。\n\n题目：{q['question']}\n\n选项：\n{opts}\n\n"
            "请先简要分析，然后在最后一行严格以【答案】X 的形式给出你选择的选项字母"
            "（X 为 A/B/C/D 之一）。"
        )

    if qtype == "multi":
        opts = "\n".join(q.get("options", []))
        return (
            f"请作答下面的多项选择题（可能有多个正确选项）。\n\n题目：{q['question']}\n\n选项：\n{opts}\n\n"
            "请先简要分析，然后在最后一行严格以【答案】AC 的形式给出所有正确选项字母"
            "（多个字母连写）。"
        )

    if qtype == "judge":
        return (
            f"请判断下面的陈述是否正确。\n\n陈述：{q['question']}\n\n"
            "请简要说明理由，然后在最后一行严格以【答案】对 或【答案】错 的形式给出结论。"
        )

    if qtype == "fill":
        return (
            f"请作答下面的填空题。\n\n题目：{q['question']}\n\n"
            "请简要说明推理，然后在最后一行严格以【答案】… 的形式给出最终答案。"
        )

    if qtype == "code":
        fn = q.get("function_name", "solve")
        return (
            f"请用 Python 编写函数解决下面的问题。\n\n题目：{q['question']}\n\n"
            f"要求：只输出完整、可运行的 Python 代码，放在一个 ```python 代码块中；"
            f"函数名必须为 `{fn}`。"
        )

    if qtype == "interview":
        return (
            f"这是一道技术面试题，请给出条理清晰、切中要害的回答。\n\n问题：{q['question']}\n\n"
            "请分点作答，并说明关键取舍。"
        )

    # solution
    return (
        f"请作答下面的题目，写出完整的解题过程。\n\n题目：{q['question']}\n\n"
        "请分步推导，最后明确给出结论。"
    )


def build_messages(q: dict) -> list[dict]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(q)},
    ]
