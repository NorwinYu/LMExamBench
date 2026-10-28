"""Evaluation profiles: job/level contexts with competency weights.

Profiles are user-definable. Edit ``profiles.json`` at the project root to add
or change jobs/roles/levels; the built-in defaults below only act as a fallback
when that file is missing.
"""
from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILES_FILE = os.path.join(ROOT, "profiles.json")

# Built-in fallback (mirrors profiles.json).
_LEVELS = ["校招", "初级", "中级", "高级", "专家"]
_LEVEL_ADJUST = {
    "校招": {"undergrad": 1.3, "leetcode": 1.3, "interview": 0.8, "ruankao": 0.6},
    "初级": {"undergrad": 1.1, "leetcode": 1.1, "interview": 1.0, "ruankao": 0.9},
    "中级": {},
    "高级": {"undergrad": 0.8, "leetcode": 0.9, "interview": 1.2, "ruankao": 1.1},
    "专家": {"undergrad": 0.6, "leetcode": 0.8, "interview": 1.3, "ruankao": 1.2},
}
_PROFILES = {
    "java-backend": {
        "name": "Java 后端工程师",
        "stages": {"undergrad": 0.30, "ruankao": 0.20, "interview": 0.35, "leetcode": 0.15},
        "roles": {"后端": 1.0, "基础架构": 0.6, "数据": 0.3, "测试": 0.2, "运维/SRE": 0.2},
        "capabilities": {"知识": 1.0, "理解": 1.0, "计算": 0.6, "推理": 1.0,
                         "编码": 1.3, "工程": 1.2, "表达": 0.8},
        "subjects": ["数据结构", "算法", "操作系统", "计算机网络", "数据库", "编译原理", "计算机组成"],
        "note": "偏工程与编码：JVM/并发/数据库/网络 + 系统设计 + 手撕代码",
    },
    "nlp-algorithm": {
        "name": "NLP 算法工程师",
        "stages": {"undergrad": 0.20, "master": 0.50, "interview": 0.30},
        "roles": {"机器学习/大模型": 1.0, "算法": 0.8, "数据": 0.4},
        "capabilities": {"知识": 1.0, "理解": 1.3, "计算": 0.8, "推理": 1.3,
                         "编码": 1.0, "工程": 1.0, "表达": 0.6},
        "subjects": ["数据结构", "算法", "高等数学", "概率论", "线性代数", "NLP", "机器学习"],
        "note": "偏模型与推理：数学基础 + NLP/大模型 + 手撕与实验能力",
    },
}


def _load():
    levels = list(_LEVELS)
    adjust = {k: dict(v) for k, v in _LEVEL_ADJUST.items()}
    profiles = {k: dict(v) for k, v in _PROFILES.items()}
    if os.path.isfile(PROFILES_FILE):
        try:
            with open(PROFILES_FILE, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            data = {}
        if isinstance(data.get("levels"), list) and data["levels"]:
            levels = [str(x) for x in data["levels"]]
        if isinstance(data.get("level_adjust"), dict):
            adjust = data["level_adjust"]
        if isinstance(data.get("profiles"), dict):
            profiles = data["profiles"]
    return levels, adjust, profiles


LEVELS, LEVEL_ADJUST, PROFILES = _load()


def resolve_profile(profile_id: str, level: str = "中级") -> dict:
    """Return a normalized spec: stage weights, roles, capabilities, subjects."""
    if profile_id not in PROFILES:
        raise ValueError(f"unknown profile: {profile_id}")
    base = PROFILES[profile_id]
    level = level if level in LEVELS else "中级"
    adjust = LEVEL_ADJUST.get(level, {})
    stages = {}
    for stage, weight in base.get("stages", {}).items():
        stages[stage] = float(weight) * float(adjust.get(stage, 1.0))
    total = sum(stages.values()) or 1.0
    stages = {k: round(v / total, 4) for k, v in stages.items()}
    return {
        "id": profile_id,
        "name": base.get("name", profile_id),
        "level": level,
        "stages": stages,
        "roles": dict(base.get("roles") or {}),
        "capabilities": dict(base.get("capabilities") or {}),
        "subjects": list(base.get("subjects") or []),
        "note": base.get("note", ""),
    }


def profile_public() -> dict:
    """Compact profile list for the UI."""
    out = {}
    for pid, p in PROFILES.items():
        out[pid] = {
            "name": p.get("name", pid),
            "stages": list(p.get("stages", {})),
            "roles": list(p.get("roles", {})),
            "subjects": p.get("subjects", []),
            "note": p.get("note", ""),
        }
    return {"levels": LEVELS, "profiles": out}


def match_question(q: dict, spec: dict) -> bool:
    stage = q.get("stage")
    if stage not in spec["stages"]:
        return False
    if stage == "interview" and q.get("role") not in spec["roles"]:
        return False
    return True


def filter_by_profile(questions: list[dict], spec: dict) -> list[dict]:
    return [q for q in questions if match_question(q, spec)]
