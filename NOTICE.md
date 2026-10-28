# 版权与数据来源声明（NOTICE）

## 1. 代码许可

本仓库的**框架代码**（`engine/`、`server/`、`web/`、`run.py`、`tools/`、`tests/` 等）
以 **MIT License** 发布，见 [`LICENSE`](LICENSE)。

## 2. 题库

**本仓库不内置任何题库**。`bank/*.json` 属于本地、私有数据，已被 `.gitignore` 排除。

评测题目请自行生成或编写，并遵守：

- 题目为**原创**，或已获得授权；
- 不逐字复制真实考卷、竞赛题、教辅、LeetCode 官方题面、面试真题等；
- 引用诗词仅限**公有领域**作品；
- 常识、公式、概念本身不受版权保护，但**文字表述必须自己写**。

生成方法见 [`skills/generate-bank/SKILL.md`](skills/generate-bank/SKILL.md)。

若引入第三方公开数据集（如 C-Eval、GAOKAO-Bench、QualBench 等），请自行确认并遵守其许可
（部分仅限研究/非商业用途），并保留出处与署名。

## 3. 密钥与个人信息

- 本仓库不含任何 API Key、Token 或个人信息。
- 请在本地 `config.json` 中填写自己的密钥，**不要提交**。
- 运行记录（`runs/`）已自动抹除密钥；`runs/` 也被 `.gitignore` 排除。

## 4. 商标

文中出现的产品名、考试名与商标（Ollama、vLLM、LM Studio、软考、LeetCode 等）
归各自权利人所有，仅用于说明与兼容性描述。
