# AGENTS.md — 给 AI 编码代理的项目说明

> 一份让 AI agent 快速理解并安全操作本仓库的指南。人类开发者也可参考。

## 这是什么

LMExamBench：本地优先、分层的大模型考试评测框架。把 LLM 当成“考生”，按
「学历阶段（小学→初中→高中→大学→硕士）× 学科」和「大厂岗位 × 职级 × 面试轮次」出题评测，
客观题规则判分、代码题跑用例、主观题 LLM 裁判，输出阶段/学科/岗位/能力/方案多维评分与 HTML/PDF 报告。

技术栈：**纯 Python 标准库后端**（`urllib` + `http.server` + `concurrent.futures`）+ **原生 JS/SVG 前端**（无构建）。
PDF 导出额外需要 Pillow 与 Noto CJK 字体（可选）。

## 目录

```
run.py                 CLI 入口（validate/run/list/audit/export/regrade/compare/serve）
engine/                client/loader/prompts/runner/grader/scorer/audit/compare/report/report_pdf/profiles/paper
server/app.py          http.server + JSON API + 运行管理
web/                   看板（index.html / app.js / style.css，无打包）
config.json            模型/裁判/运行/权重（api_key 必须留空）
profiles.json          岗位方案与职级（用户可编辑）
bank/                  题库（不入库，见「红线」）
skills/generate-bank/  生成原创题库的技能（SKILL.md）
tools/                 可计算题生成器（generate_bank.py / generate_master.py）
tests/                 单测（不依赖内置题库）
```

## 常用命令

```bash
python3 run.py validate                    # 校验题库
python3 run.py run --paper 2 --seed 2026   # 整卷评测（每部分 2 题）
python3 run.py run --profile java-backend --level 中级 --paper 3
python3 run.py serve                       # 看板 → http://127.0.0.1:8000
python3 run.py export RUN_ID --format pdf  # 导出 HTML/PDF
python3 run.py compare [RUN_ID ...]        # 多运行对比
python3 run.py regrade RUN_ID              # 用已存回答重判
python3 run.py audit                       # 题库审计（近似重复/覆盖）
python3 tools/generate_bank.py             # 生成可计算题

# 修改后自检：
python3 -m py_compile engine/*.py server/*.py run.py tools/*.py
python3 tests/test_core.py                 # 单测（unittest，无 pytest 也可跑）
node --check web/app.js                    # 若改过前端
```

## 硬性红线（必须遵守）

1. **绝不提交任何 API Key / Token**：`config.json` 的 `api_key` 必须为空字符串 `""`。
2. **绝不提交题库**：`bank/*.json` 是本地私有数据（版权），已被 `.gitignore` 排除。
3. **绝不提交运行记录**：`runs/*` 已被 `.gitignore` 排除，仅保留 `runs/.gitkeep`。
4. **绝不硬编码**密钥、主机名、真实模型名到代码或文档。
5. 提交前确认：`git status` 干净、`git grep -iE "sk-|api_key.*[^\"']{8,}"` 无命中。

## 初始化（全新克隆后）

1. **配置模型**：编辑 `config.json` 的 `model.base_url / name / api_key` 与 `judge.*`
   （被测模型与裁判模型可不同），或执行 README「快速开始」里的内联 Python 片段。
2. **生成/编写题库**：见 `skills/generate-bank/SKILL.md`，或 `python3 tools/generate_bank.py`；
   然后 `python3 run.py validate` 确认无误。
3. **评测**：`python3 run.py run --paper N`（或看板里发起）。
4. **看板**：`python3 run.py serve` → http://127.0.0.1:8000 。

## 关键实现位置

- 阶段列表：`engine/loader.py` 的 `STAGES`（8 个阶段，无博士）。
- 能力维度：`engine/taxonomy.py` 的 `CAPABILITIES`（知识/理解/计算/推理/编码/工程/表达）。
- 岗位方案与职级：`engine/profiles.py` 读取根目录 `profiles.json`（用户可增删岗位）。
- 判分：`engine/grader.py`（客观题容差/多选部分分、代码题 pass@k、主观题 LLM 裁判 + debias）。
- 聚合与加权：`engine/scorer.py`（阶段→学科/岗位/轮次/职级/能力/难度，样本不足标记）。
- 组卷：`engine/paper.py`（`--paper N` 按「阶段 × 学科/岗位」每部分抽 N 题）。

## 约定

- 后端保持 **stdlib-only**，不要引入第三方网络/服务器依赖（PDF 的 Pillow 除外）。
- 前端无构建，改 `web/app.js` 后刷新页面即生效；不要新增打包工具链。
- 题库、运行记录、`__pycache__`、`config.json` 里的密钥都属于“不该进 git”的内容。
