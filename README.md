# LMExamBench · 分层大模型考试评测框架

一个**本地优先、可离线运行**的大模型评测框架：把大模型当成“考生”，按
「学历阶段（小学→大学→硕士）× 学科」和「大厂岗位 × 职级 × 面试轮次」组织出题，
支持客观题规则判分、代码题用例判分、主观题 LLM 裁判，并给出
阶段/学科/岗位/能力/方案多维评分与可视化。

> 本仓库开源的是**评测框架与概念**，**不内置任何题库**（避免版权风险）。
> 题库请自行生成或编写，参见 [`skills/generate-bank/SKILL.md`](skills/generate-bank/SKILL.md)。

## 特性

- **分层出题**：教育线（小学/初中/高中/大学/硕士）+ 工程师线（软考/大厂面试/LeetCode）。
- **试卷模式**：`--paper N` 按「阶段 × 学科/岗位」每部分抽 N 题组卷，避免“一题定胜负”；样本不足自动标记。
- **岗位方案可配置**：编辑根目录 `profiles.json` 自定义岗位、职级、阶段/岗位/能力权重。
- **多判分方式**：客观题规则匹配（数值容差/多选部分分）、代码题子进程跑用例（pass@k + 隐藏用例）、主观题 LLM 裁判（双向判分 + 自我偏好检测）。
- **裁判解耦**：被测模型与裁判模型各自独立配置 base_url / api_key / model（本地或远程）。
- **可视化**：单次运行 / 多运行对比 / 评测与题库 / 设置 四个模式；能力雷达、学科/岗位/难度/轮次细分。
- **报告导出**：独立 HTML 与多页 PDF。
- **纯标准库实现**：后端仅用 Python 标准库 + 原生前端；PDF 导出需要 Pillow 与 Noto CJK 字体（可选）。

## 快速开始

```bash
# 1. 配置模型（OpenAI 兼容接口，本地或远程）
python3 - <<'PY'
import json
c = json.load(open('config.json', encoding='utf-8'))
c['model']['base_url'] = 'http://127.0.0.1:11434/v1'
c['model']['name'] = 'qwen2.5:7b'
c['judge']['base_url'] = c['model']['base_url']
c['judge']['model'] = c['model']['name']
json.dump(c, open('config.json', 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
PY

# 2. 生成/编写题库（原创），校验
#    见 skills/generate-bank/SKILL.md，或：
python3 tools/generate_bank.py
python3 run.py validate

# 3. 评测
python3 run.py run --paper 2 --seed 2026          # 整卷：每部分 2 题
python3 run.py run --profile java-backend --level 中级 --paper 3

# 4. 看板
python3 run.py serve                              # http://127.0.0.1:8000
```

> `config.json` 里的 `api_key` 请自行填写；**不要提交密钥**。运行记录会自动抹除密钥。

## 目录结构

```
lmeb/
├── config.json            # 模型/裁判/运行/权重（无密钥示例）
├── profiles.json          # 岗位方案与职级（可自定义）
├── bank/                  # 题库（本地，不入库）+ README
├── skills/generate-bank/  # 用 AI 生成原创题库的技能
├── engine/                # client/loader/prompts/runner/grader/scorer/audit/compare/report/profiles/paper
├── server/                # http.server + JSON API + 运行管理
├── web/                   # 看板（原生 JS + SVG）
├── run.py                 # CLI 入口
├── tools/                 # 可计算题生成器（可选）
├── tests/                 # 单测（不依赖内置题库）
└── LICENSE  NOTICE.md
```

## CLI

```bash
python3 run.py validate                       # 校验题库
python3 run.py run [options]                  # 评测
    --stages primary,junior                   # 只跑指定阶段
    --paper N                                 # 试卷模式：每阶段×学科/岗位抽 N 题
    --sample N  --seed S                      # 每阶段随机抽 N 题
    --profile java-backend|nlp-algorithm      # 岗位方案
    --level 校招|初级|中级|高级|专家
    --base-url URL --model NAME --api-key K   # 被测模型
    --judge-base-url URL --judge-model NAME   # 裁判模型（可不同于被测）
    --no-judge --no-debias --code-samples N
python3 run.py list                           # 列出运行
python3 run.py compare [RUN_ID...]            # 多运行对比 + 区分度/难度
python3 run.py export RUN_ID --format pdf     # 导出 HTML/PDF 报告
python3 run.py regrade RUN_ID                 # 用已存回答按当前规则重判
python3 run.py audit                          # 题库审计（近似重复/覆盖）
python3 run.py serve                          # 启动看板
```

## 评分模型

- 客观题（choice/judge/fill）：规则匹配；填空支持多答案与数值容差；多选按 `(命中−错选)/正确数` 部分给分。
- 代码题（code）：子进程跑用例；单样本按通过率，多样本按 pass@k；支持 `hidden_cases`。
- 主观题（solution/interview）：LLM 裁判按 rubric 逐要点 0~1 打分；`debias` 时正反序各判一次取均值。
- 聚合：阶段得分率 → 学科/岗位/能力维度 → 按阶段权重（或岗位方案 × 职级）加权总分。
- 每题不足 2 题的部分标记 `⚠ 样本不足`，建议扩题后再下结论。

## 题库 schema

见 [`skills/generate-bank/SKILL.md`](skills/generate-bank/SKILL.md) 与 [`bank/README.md`](bank/README.md)。

## 岗位方案（profiles.json）

```json
{
  "levels": ["校招", "初级", "中级", "高级", "专家"],
  "level_adjust": { "校招": {"undergrad": 1.3, "leetcode": 1.3, "interview": 0.8, "ruankao": 0.6} },
  "profiles": {
    "java-backend": {
      "name": "Java 后端工程师",
      "stages": {"undergrad": 0.3, "ruankao": 0.2, "interview": 0.35, "leetcode": 0.15},
      "roles": {"后端": 1.0, "基础架构": 0.6},
      "capabilities": {"编码": 1.3, "工程": 1.2},
      "subjects": ["数据结构", "算法", "操作系统", "计算机网络", "数据库"]
    }
  }
}
```

- `stages`：该岗位考哪些阶段、权重多少；
- `roles`：面试阶段按岗位的权重；
- `capabilities`：能力维度权重；
- `level_adjust`：职级对阶段权重的乘数（校招偏基础、专家偏系统设计）。

## Web API

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/health` / `/api/config` / `/api/settings` | 健康 / 默认配置 / 完整设置 |
| POST | `/api/settings` / `/api/test` | 保存设置 / 测试连通性 |
| GET | `/api/bank` / `/api/bank/audit` / `/api/profiles` | 题库 / 审计 / 岗位方案 |
| GET | `/api/runs` / `/api/runs/{id}` | 运行列表 / 详情 |
| POST | `/api/runs` | 发起评测 |
| DELETE | `/api/runs/{id}` | 删除运行 |
| GET | `/api/compare?ids=a,b` | 多运行对比 |
| GET | `/api/runs/{id}/export` / `/export.pdf` | 导出 HTML / PDF |

## 安全与边界

- **代码题会执行模型生成的 Python**（子进程 + 超时）。仅用于可信环境；可设置 `run.allow_code_exec=false`。
- 裁判（尤其与被测同模型时）可能高估分数；本框架会标记 `self_judge`。
- 样本不足时分数不可靠，请以“试卷模式 + 每题多题”为准。
- 请勿在 `config.json`、题库或提交内容中写入任何密钥。

## 版权

- 框架代码：MIT，见 [`LICENSE`](LICENSE)。
- **不内置题库**：请自行生成原创题，遵守版权；详见 [`NOTICE.md`](NOTICE.md) 与 [`skills/generate-bank/SKILL.md`](skills/generate-bank/SKILL.md)。
