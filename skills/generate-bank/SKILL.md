---
name: lmeb-generate-bank
description: 为 LMExamBench 分层大模型考试评测生成原创题库。当用户想创建或扩充评测题目、按阶段/学科/岗位出卷时使用。产出原创、不含版权风险的题目 JSON。
---

# 生成 LMExamBench 题库

为 `LMExamBench`（一个本地、分层的大模型考试评测框架）生成**原创**题目，
写入 `bank/<stage>.json`。

## 阶段（stage id 与文件名一一对应）

| id | 名称 | 学科/岗位 |
|---|---|---|
| primary | 小学 | 语文、数学、英语、科学 |
| junior | 初中 | 语文、数学、英语、物理、化学、生物、历史、地理、政治 |
| senior | 高中 | 语文、数学、英语、物理、化学、生物、历史、地理、政治 |
| undergrad | 大学 | 数据结构、算法、操作系统、计网、数据库、编译、计算机组成、高数、概率、线代 |
| master | 硕士 | NLP/大模型：Transformer、分词、LoRA、RLHF、RAG、评测、KV Cache、MoE、蒸馏… |
| ruankao | 软考 | 软件工程、架构、数据库、网络、安全、项目管理、案例题、论文题 |
| interview | 大厂面试 | 岗位 × 职级 × 轮次（一面/二面/三面/交叉面/HR面） |
| leetcode | LeetCode | 编程题（自拟题面与用例） |

## 题目 schema

一个阶段一个 JSON 文件，顶层 `questions` 为数组。每道题：

```json
{
  "id": "senior-math-001",
  "subject": "数学",
  "chapter": "函数",
  "topic": "二次函数最值",
  "type": "fill",                       // choice|multi|judge|fill|solution|interview|code
  "difficulty": "medium",               // easy|medium|hard
  "capabilities": ["计算", "推理"],      // 知识|理解|计算|推理|编码|工程|表达
  "tags": ["二次函数"],
  "question": "函数 f(x)=x²−2x+3 的最小值是 ____。",
  "answer": "2",                        // choice 用字母；multi 用 ["A","C"]；judge 用 对/错
  "answers": ["2"],                     // 可选：填空可接受答案
  "tolerance": 0.01,                    // 可选：填空数值容差
  "reference": "配方得 (x−1)²+2，最小值为 2。",
  "points": 5
}
```

按 `type` 补充：

- `choice` / `multi`：`options`: ["A. …", "B. …"]
- `solution` / `interview`：`rubric`: ["要点1", "要点2", "要点3"]
- `interview` 额外：`round`（一面/二面/三面/交叉面/HR面）、`role`（岗位）、`level`（校招/初级/中级/高级/专家）
- `code`：`function_name`、`test_cases`: [{"call": "f(1,2)", "expected": 3}]、`hidden_cases`（可选）

## 硬性要求（版权）

1. **全部原创**：不逐字复制任何真实考卷、竞赛题、LeetCode/面试真题、教辅、教材。
2. 引用诗词仅限**公有领域**（作者逝世已逾 50/70 年）。
3. 常识/公式/概念本身不受版权保护，但**表述必须自己写**。
4. 每题都要有 `reference`（解析/参考答案）和正确的 `answer`。
5. 代码题：题面自拟，测试用例自己构造，并给出 `hidden_cases` 若干。

## 输出

- 每个阶段写一个 `bank/<stage>.json`。
- 写完后运行 `python3 run.py validate` 校验（题目数、字段、id 唯一）。
- 不要写任何密钥、token、个人信息。

## 质量要求

- 覆盖每个学科/岗位，尽量让每个「阶段 × 学科/岗位」都有 ≥3 题（这样组卷时不会“一题定胜负”）。
- 难度按 easy/medium/hard 分布；主观题要有 2~4 个可评判的 rubric 要点。
- 面试题贴近真实：给场景、要追问、要权衡。
