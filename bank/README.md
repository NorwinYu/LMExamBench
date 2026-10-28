# 题库目录（不入库）

本目录存放评测题目，每个阶段一个文件：`primary.json`、`junior.json`、`senior.json`、
`undergrad.json`、`master.json`、`ruankao.json`、`interview.json`、`leetcode.json`。

> 出于版权考虑，本仓库**不内置任何题库**。请自行生成或编写，并确保：
> - 题目为原创，或已获得授权；不逐字复制真实考卷、竞赛题、LeetCode 官方题面等。
> - 不提交任何带密钥/敏感信息的文件。

## 快速生成

用 AI 生成原创题库：参见 [`skills/generate-bank/SKILL.md`](../skills/generate-bank/SKILL.md)。

也可用内置生成器快速产出“可计算题”（答案由公式保证正确）：

```bash
python3 tools/generate_bank.py          # 中小学/大学/软考 的可计算题
python3 tools/generate_master.py        # 硕士 NLP/大模型 的可计算题
```

生成后校验：

```bash
python3 run.py validate
```

## 题目格式

每个阶段一个 JSON，顶层 `questions` 为数组。字段见下表（`type` 决定必填项）：

| 字段 | 说明 |
|---|---|
| `id` | 全局唯一 |
| `subject` | 学科（教育阶段）或岗位（面试） |
| `chapter` | 章节 |
| `topic` | 考点 |
| `type` | `choice` / `multi` / `judge` / `fill` / `solution` / `interview` / `code` |
| `difficulty` | `easy` / `medium` / `hard` |
| `capabilities` | 能力维度数组：知识/理解/计算/推理/编码/工程/表达 |
| `tags` | 标签数组 |
| `question` | 题干 |
| `answer` | 客观题答案（choice 用字母；multi 用 `["A","C"]`；judge 用 对/错；fill 用文本） |
| `answers` | 可选：填空的可接受答案列表 |
| `tolerance` | 可选：填空数值容差 |
| `options` | 选择/多选的选项 |
| `rubric` | 主观题评分要点（solution/interview） |
| `reference` | 参考答案/解析 |
| `points` | 满分 |
| `function_name` / `test_cases` / `hidden_cases` | code 题的函数名与用例 |
| `round` / `role` / `level` | 面试题的轮次 / 岗位 / 职级 |

示例见技能文档。缺失 `chapter`/`topic` 会自动回填为 `subject`。
