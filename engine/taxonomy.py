"""能力维度与题目分类的受控词表（taxonomy）。

用于把“粗粒度学科”细化为可聚合的**能力画像**：
- capabilities : 能力维度（一题可属多个），产出能力雷达图
- tags         : 考点标签（自由文本，用于更细颗粒度）
- difficulty   : 难度（受控），产出难度分层
- bloom        : 认知层级（可选，布鲁姆分类的中文精简版）
"""
from __future__ import annotations

CAPABILITIES = ["知识", "理解", "计算", "推理", "编码", "工程", "表达"]

DIFFICULTIES = ("easy", "medium", "hard")
DIFFICULTY_LABEL = {"easy": "简单", "medium": "中等", "hard": "困难"}

BLOOM_LEVELS = ("记忆", "理解", "应用", "分析", "评价", "创造")

QUESTION_TYPES = ("choice", "multi", "judge", "fill", "solution", "interview", "code")

# 判断题可接受的答案归一化
TRUE_TOKENS = {"t", "true", "对", "正确", "是", "yes", "√", "v"}
FALSE_TOKENS = {"f", "false", "错", "错误", "否", "no", "×", "x"}

DEFAULT_CAPABILITY = "知识"
