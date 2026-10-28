"""Core unit tests (stdlib unittest, no third-party deps).

Run:  python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.grader import (  # noqa: E402
    grade_choice, grade_fill, grade_code, grade_subjective,
    grade_multi, grade_judge,
)
from engine.scorer import aggregate  # noqa: E402
from engine.loader import load_bank, load_flows, sample_questions  # noqa: E402
from engine.audit import audit_questions, flow_coverage  # noqa: E402
from engine.report import render_report  # noqa: E402
from engine.compare import item_statistics, compare_runs  # noqa: E402
from engine.profiles import resolve_profile, filter_by_profile  # noqa: E402

BANK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bank")


class GraderTests(unittest.TestCase):
    def test_choice_formats(self):
        q = {"id": "t", "type": "choice", "points": 5, "answer": "B",
             "options": ["A. 甲", "B. 乙", "C. 丙", "D. 丁"]}
        for text in ("【答案】B", "答案是 B。", "所以选B", "最终答案：B", "B"):
            self.assertTrue(grade_choice(q, text)["correct"], text)
        self.assertFalse(grade_choice(q, "【答案】C")["correct"])
        self.assertFalse(grade_choice(q, "没有给出答案")["correct"])

    def test_fill(self):
        q = {"id": "f", "type": "fill", "points": 5, "answer": "9",
             "answers": ["9", "九"]}
        self.assertTrue(grade_fill(q, "结果是【答案】9")["correct"])
        self.assertTrue(grade_fill(q, "答案是九")["correct"])
        self.assertFalse(grade_fill(q, "【答案】8")["correct"])

    def test_code_pass_and_fail(self):
        q = {"id": "c", "type": "code", "points": 10,
             "test_cases": [{"call": "add(1, 2)", "expected": 3}]}
        good = "def add(a, b):\n    return a + b\n"
        bad = "def add(a, b):\n    return a - b\n"
        self.assertEqual(grade_code(q, good)["score"], 10.0)
        self.assertEqual(grade_code(q, bad)["score"], 0.0)

    def test_code_partial_credit(self):
        q = {"id": "c2", "type": "code", "points": 10,
             "test_cases": [{"call": "f(1)", "expected": 1},
                            {"call": "f(2)", "expected": 2}]}
        code = "def f(x):\n    return 1\n"  # passes first only
        self.assertAlmostEqual(grade_code(q, code)["score"], 5.0)

    def test_subjective_without_judge_is_ungraded(self):
        q = {"id": "s", "type": "solution", "points": 10, "rubric": ["要点"]}
        res = grade_subjective(q, "作答", judge_client=None)
        self.assertIsNone(res["score"])


class ScorerTests(unittest.TestCase):
    def _res(self, stage, score, mx, qtype="choice"):
        return {
            "id": f"{stage}-{score}", "stage": stage, "stage_name": stage,
            "subject": "x", "type": qtype, "points": mx,
            "grading": {"score": score, "max": mx, "method": "exact",
                        "correct": score == mx, "detail": {}},
            "error": None,
        }

    def test_weighted_average(self):
        cfg = {"weights": {"preset": "p",
                           "presets": {"p": {"a": 1.0, "b": 3.0}}}}
        results = [self._res("a", 10, 10), self._res("b", 0, 10)]
        # a=100%, b=0%, weighted by 1:3 -> 25%
        self.assertAlmostEqual(aggregate(results, cfg)["overall"]["weighted_percent"], 25.0)

    def test_ungraded_excluded(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"a": 1.0}}}}
        ungraded = {
            "id": "a-u", "stage": "a", "stage_name": "a", "subject": "x",
            "type": "solution", "points": 10,
            "grading": {"score": None, "max": 10, "method": "judge",
                        "correct": None, "detail": {}},
            "error": None,
        }
        results = [self._res("a", 10, 10), ungraded]
        out = aggregate(results, cfg)["overall"]
        self.assertEqual(out["n"], 2)
        self.assertEqual(out["graded_n"], 1)
        self.assertEqual(out["ungraded_n"], 1)
        self.assertAlmostEqual(out["percent"], 100.0)

    def test_bank_loads(self):
        questions = load_bank(BANK)
        ids = [q["id"] for q in questions]
        self.assertEqual(len(ids), len(set(ids)))


class SeqJudge:
    """Fake judge returning a scripted sequence of point-score lists."""

    def __init__(self, sequence):
        self.sequence = sequence
        self.calls = 0

    def chat(self, messages, **kwargs):
        import json
        scores = self.sequence[min(self.calls, len(self.sequence) - 1)]
        self.calls += 1
        points = [{"point": f"p{i}", "score": s, "reason": "fake"}
                  for i, s in enumerate(scores)]
        return {"content": json.dumps({"points": points, "total_comment": "fake"})}


class AdvancedGraderTests(unittest.TestCase):
    def test_multi_partial_credit(self):
        q = {"id": "m", "type": "multi", "points": 10, "answer": ["A", "B", "D"],
             "options": ["A. x", "B. y", "C. z", "D. w"]}
        self.assertAlmostEqual(grade_multi(q, "【答案】ABD")["score"], 10.0, places=3)
        self.assertAlmostEqual(grade_multi(q, "【答案】AB")["score"], 10 * 2 / 3, places=3)
        # a wrong option cancels one correct hit
        self.assertAlmostEqual(grade_multi(q, "【答案】ABC")["score"], 10 * 1 / 3, places=3)

    def test_judge_type(self):
        q = {"id": "j", "type": "judge", "points": 5, "answer": "错"}
        self.assertTrue(grade_judge(q, "理由…【答案】错")["correct"])
        self.assertTrue(grade_judge(q, "【答案】F")["correct"])
        self.assertFalse(grade_judge(q, "【答案】对")["correct"])

    def test_fill_numeric_tolerance(self):
        q = {"id": "n", "type": "fill", "points": 5, "answer": "3.14", "tolerance": 0.01}
        self.assertTrue(grade_fill(q, "【答案】3.14159")["correct"])
        self.assertFalse(grade_fill(q, "【答案】3.2")["correct"])

    def test_subjective_debias_and_self_judge(self):
        q = {"id": "s", "type": "solution", "points": 10,
             "question": "q", "rubric": ["a", "b", "c"]}
        judge = SeqJudge([[1, 0, 1], [0, 1, 1]])
        res = grade_subjective(q, "answer", judge, judge_model="m1",
                               debias=True, candidate_model="m1")
        self.assertTrue(res["detail"]["debias"])
        self.assertTrue(res["detail"]["self_judge"])
        self.assertAlmostEqual(res["score"], 10 * (1 + 0.5 + 0.5) / 3, places=3)
        self.assertAlmostEqual(res["detail"]["agreement"], round(1 - 2 / 3, 4), places=3)
        self.assertIn("pass2_scores", res["detail"])


class CapabilityScorerTests(unittest.TestCase):
    def _mk(self, caps, diff, score):
        return {"id": f"q-{caps}-{diff}-{score}", "stage": "a", "stage_name": "a",
                "subject": "x", "type": "choice", "capabilities": caps,
                "tags": [], "difficulty": diff, "points": 10,
                "grading": {"score": score, "max": 10, "method": "exact",
                            "correct": score == 10, "detail": {}},
                "error": None}

    def test_capabilities_and_difficulty(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"a": 1.0}}}}
        results = [self._mk(["推理"], "hard", 10),
                   self._mk(["推理"], "easy", 0),
                   self._mk(["编码"], "hard", 10)]
        out = aggregate(results, cfg)
        caps = {c["capability"]: c for c in out["capabilities"]}
        self.assertAlmostEqual(caps["推理"]["percent"], 50.0)
        self.assertAlmostEqual(caps["编码"]["percent"], 100.0)
        diffs = {d["difficulty"]: d for d in out["difficulties"]}
        self.assertAlmostEqual(diffs["hard"]["percent"], 100.0)
        self.assertAlmostEqual(diffs["easy"]["percent"], 0.0)


class PassAtKAndAuditTests(unittest.TestCase):
    def test_code_pass_at_k_and_hidden_cases(self):
        q = {"id": "pk", "type": "code", "points": 10,
             "test_cases": [{"call": "add(1, 2)", "expected": 3}],
             "hidden_cases": [{"call": "add(-1, 1)", "expected": 0}]}
        good = "def add(a, b):\n    return a + b\n"
        bad = "def add(a, b):\n    return 0\n"
        r = grade_code(q, [good, bad])
        self.assertEqual(r["detail"]["samples"], 2)
        self.assertEqual(r["detail"]["passed_all"], 1)
        self.assertAlmostEqual(r["detail"]["pass_at_k"], 1.0, places=3)
        self.assertEqual(r["detail"]["hidden_cases"], 1)
        # a sample that passes the visible case but fails the hidden one is not full
        cheat = "def add(a, b):\n    return 3\n"
        self.assertLess(grade_code(q, cheat)["fraction"], 1.0)

    def test_audit_near_duplicates_and_coverage(self):
        from engine.audit import audit_questions
        qs = [
            {"id": "a", "stage": "s", "question": "计算 1+1 的值并说明理由", "capabilities": ["计算"]},
            {"id": "b", "stage": "s", "question": "计算 1+1 的值并说明理由。", "capabilities": ["计算"]},
            {"id": "c", "stage": "s", "question": "完全不同的题目内容", "capabilities": ["理解"]},
        ]
        res = audit_questions(qs, threshold=0.8)
        self.assertEqual(res["total"], 3)
        pairs = {(d["a"], d["b"]) for d in res["duplicates"]}
        self.assertIn(("a", "b"), pairs)
        self.assertEqual(res["coverage"]["s"]["计算"], 2)

    def test_report_renders(self):
        record = {
            "id": "t1", "status": "done", "created_at": "2026-01-01",
            "config": {"model": {"name": "m"}},
            "summary": {
                "overall": {"weighted_percent": 80.0, "percent": 80.0, "coverage": 1.0,
                            "graded_n": 1, "n": 1,
                            "grade": {"letter": "B", "label": "良好"}},
                "stages": [{"id": "s", "name": "阶段", "percent": 80.0,
                            "earned": 8, "graded_total": 10, "weight": 1}],
                "capabilities": [], "difficulties": [], "judge": {},
            },
            "results": [{
                "id": "q1", "stage": "s", "stage_name": "阶段", "subject": "x",
                "type": "choice", "question": "题干", "options": ["A. 1"],
                "model_output": "【答案】A", "reference": "解析",
                "capabilities": ["知识"], "tags": [],
                "grading": {"score": 8, "max": 10, "method": "exact",
                            "detail": {"expected": "A", "got": "A"}},
            }],
        }
        out = render_report(record)
        self.assertIn("LMExamBench 评测报告", out)
        self.assertIn("q1", out)
        self.assertIn("80", out)


class CompareStatsTests(unittest.TestCase):
    def _rec(self, rid, fracs):
        return {
            "id": rid, "status": "done", "created_at": rid,
            "config": {"model": {"name": rid}},
            "summary": {"overall": {"weighted_percent": 50, "percent": 50,
                                    "coverage": 1.0,
                                    "grade": {"letter": "D", "label": "及格"}},
                        "stages": [], "capabilities": []},
            "results": [
                {"id": qid, "stage": "s", "subject": "x", "type": "choice",
                 "difficulty": "medium", "capabilities": ["知识"], "tags": [],
                 "grading": {"fraction": f, "score": f * 10, "max": 10}}
                for qid, f in fracs.items()
            ],
        }

    def test_item_statistics_discrimination(self):
        records = [
            self._rec("m1", {"q1": 1.0, "q2": 1.0}),
            self._rec("m2", {"q1": 1.0, "q2": 0.0}),
            self._rec("m3", {"q1": 0.0, "q2": 0.0}),
        ]
        stats = item_statistics(records)
        items = {it["id"]: it for it in stats["items"]}
        self.assertAlmostEqual(items["q1"]["p_value"], 2 / 3, places=3)
        self.assertAlmostEqual(items["q1"]["discrimination"], 0.5, places=3)
        self.assertAlmostEqual(items["q2"]["p_value"], 1 / 3, places=3)
        self.assertEqual(stats["runs"], ["m1", "m2", "m3"])

    def test_discrimination_needs_three_runs(self):
        records = [self._rec("a", {"q": 1.0}), self._rec("b", {"q": 0.0})]
        stats = item_statistics(records)
        self.assertIsNone(stats["items"][0]["discrimination"])
        self.assertIn("样本不足", stats["items"][0]["flags"])

    def test_compare_runs_matrix(self):
        r1 = self._rec("m1", {"q1": 1.0})
        r1["summary"]["stages"] = [{"id": "s", "name": "阶段", "percent": 100.0}]
        r1["summary"]["capabilities"] = [{"capability": "知识", "percent": 100.0}]
        r2 = self._rec("m2", {"q1": 0.0})
        r2["summary"]["stages"] = [{"id": "s", "name": "阶段", "percent": 0.0}]
        r2["summary"]["capabilities"] = [{"capability": "知识", "percent": 0.0}]
        res = compare_runs([r1, r2])
        self.assertEqual(len(res["runs"]), 2)
        stage = {s["id"]: s for s in res["stages"]}["s"]
        self.assertEqual(stage["values"]["m1"], 100.0)
        self.assertEqual(stage["values"]["m2"], 0.0)
        cap = {c["capability"]: c for c in res["capabilities"]}["知识"]
        self.assertEqual(cap["values"]["m1"], 100.0)

    def test_calibration(self):
        records = [
            self._rec("a", {"q": 1.0}),
            self._rec("b", {"q": 1.0}),
            self._rec("c", {"q": 0.0}),
        ]
        stats = item_statistics(records)
        self.assertEqual(stats["calibration"]["medium"]["n"], 1)
        self.assertAlmostEqual(stats["calibration"]["medium"]["mean_p"], 2 / 3, places=3)


class BankCoverageTests(unittest.TestCase):
    def test_stage_coverage(self):
        questions = load_bank(BANK)
        if not questions:
            self.skipTest("no question bank bundled")
        valid = {"primary", "junior", "senior", "undergrad", "master",
                 "ruankao", "interview", "leetcode"}
        for q in questions:
            self.assertIn(q["stage"], valid, q["id"])

    def test_interview_rounds(self):
        questions = load_bank(BANK)
        rounds = {q.get("round") for q in questions if q["stage"] == "interview"}
        if not rounds:
            self.skipTest("no interview questions")
        self.assertTrue(bool(rounds))

    def test_interview_roles(self):
        questions = load_bank(BANK)
        roles = {q.get("role") for q in questions if q["stage"] == "interview"}
        if not roles:
            self.skipTest("no interview questions")
        self.assertTrue(bool(roles))

    def test_interview_levels(self):
        questions = load_bank(BANK)
        levels = {q.get("level") for q in questions if q["stage"] == "interview"}
        if not levels:
            self.skipTest("no interview questions")
        self.assertTrue(levels.issubset({"校招", "初级", "中级", "高级", "专家"}))

    def test_flow_coverage(self):
        flows = load_flows(BANK)
        if not flows:
            self.skipTest("no interview flow metadata")
        questions = load_bank(BANK)
        cov = flow_coverage(questions, flows)
        self.assertTrue(cov)

    def test_levels_aggregation(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"interview": 1.0}}}}

        def rec(rid, level, score):
            return {"id": rid, "stage": "interview", "stage_name": "面试",
                    "subject": "x", "type": "interview", "level": level,
                    "round": "一面", "points": 10,
                    "capabilities": ["知识"], "tags": [],
                    "grading": {"score": score, "max": 10, "method": "judge",
                                "fraction": score / 10, "correct": score >= 6,
                                "detail": {}},
                    "error": None}

        out = aggregate([rec("a", "校招", 10), rec("b", "专家", 0)], cfg)
        levels = {r["level"]: r for r in out["levels"]}
        self.assertAlmostEqual(levels["校招"]["percent"], 100.0)
        self.assertAlmostEqual(levels["专家"]["percent"], 0.0)

    def test_roles_aggregation(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"interview": 1.0}}}}

        def rec(rid, role, score):
            return {"id": rid, "stage": "interview", "stage_name": "面试",
                    "subject": role, "type": "interview", "role": role,
                    "round": "一面", "points": 10,
                    "capabilities": ["知识"], "tags": [],
                    "grading": {"score": score, "max": 10, "method": "judge",
                                "fraction": score / 10, "correct": score >= 6,
                                "detail": {}},
                    "error": None}

        out = aggregate([rec("a", "后端", 10), rec("b", "前端", 0)], cfg)
        roles = {r["role"]: r for r in out["roles"]}
        self.assertAlmostEqual(roles["后端"]["percent"], 100.0)
        self.assertAlmostEqual(roles["前端"]["percent"], 0.0)

    def test_rounds_aggregation(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"interview": 1.0}}}}

        def rec(rid, rnd, score):
            return {"id": rid, "stage": "interview", "stage_name": "面试",
                    "subject": "x", "type": "interview", "round": rnd,
                    "points": 10, "capabilities": ["知识"], "tags": [],
                    "grading": {"score": score, "max": 10, "method": "judge",
                                "fraction": score / 10, "correct": score >= 6,
                                "detail": {}},
                    "error": None}

        out = aggregate([rec("i1", "一面", 10), rec("i2", "二面", 0)], cfg)
        rounds = {r["round"]: r for r in out["rounds"]}
        self.assertAlmostEqual(rounds["一面"]["percent"], 100.0)
        self.assertAlmostEqual(rounds["二面"]["percent"], 0.0)


    def test_sample_questions_seeded(self):
        from collections import Counter
        qs = load_bank(BANK)
        if len(qs) < 2:
            self.skipTest("not enough questions for sampling test")
        a = sample_questions(qs, 2, seed=42)
        b = sample_questions(qs, 2, seed=42)
        c = sample_questions(qs, 2, seed=7)
        self.assertEqual([x["id"] for x in a], [x["id"] for x in b])
        self.assertNotEqual([x["id"] for x in a], [x["id"] for x in c])
        counts = Counter(x["stage"] for x in a)
        self.assertTrue(all(v <= 2 for v in counts.values()), counts)


    def test_chapter_topic_present(self):
        questions = load_bank(BANK)
        if not questions:
            self.skipTest("no question bank bundled")
        self.assertTrue(all(q.get("chapter") for q in questions))
        self.assertTrue(all(q.get("topic") for q in questions))

    def test_topics_aggregation(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"s": 1.0}}}}

        def rec(rid, topic, score):
            return {"id": rid, "stage": "s", "stage_name": "s", "subject": "x",
                    "topic": topic, "type": "choice", "points": 10,
                    "capabilities": ["知识"], "tags": [],
                    "grading": {"score": score, "max": 10, "method": "exact",
                                "fraction": score / 10, "correct": score == 10,
                                "detail": {}},
                    "error": None}

        out = aggregate([rec("a", "加法", 10), rec("b", "加法", 0), rec("c", "乘法", 10)], cfg)
        topics = {t["topic"]: t for t in out["topics"]}
        self.assertAlmostEqual(topics["加法"]["percent"], 50.0)
        self.assertAlmostEqual(topics["乘法"]["percent"], 100.0)


    def test_role_weighted_interview(self):
        cfg = {"weights": {"preset": "p", "presets": {"p": {"interview": 1.0}},
                           "roles": {"后端": 3.0, "前端": 1.0}}}

        def rec(rid, role, score):
            return {"id": rid, "stage": "interview", "stage_name": "面试",
                    "subject": role, "role": role, "round": "一面", "type": "interview",
                    "points": 10, "capabilities": ["知识"], "tags": [],
                    "grading": {"score": score, "max": 10, "method": "judge",
                                "fraction": score / 10, "correct": score >= 6,
                                "detail": {}},
                    "error": None}

        out = aggregate([rec("a", "后端", 0), rec("b", "前端", 10)], cfg)
        stage = {s["id"]: s for s in out["stages"]}["interview"]
        # 后端 0% × 3 + 前端 100% × 1 => 25%
        self.assertAlmostEqual(stage["percent"], 25.0)
        self.assertTrue(stage.get("role_weighted"))


class ProfileTests(unittest.TestCase):
    def test_resolve_level_adjust(self):
        a = resolve_profile("java-backend", "校招")
        b = resolve_profile("java-backend", "专家")
        self.assertGreater(a["stages"]["undergrad"], b["stages"]["undergrad"])
        self.assertGreater(b["stages"]["interview"], a["stages"]["interview"])
        self.assertAlmostEqual(sum(a["stages"].values()), 1.0, places=2)

    def test_filter_by_profile(self):
        qs = [
            {"id": "u", "stage": "undergrad", "subject": "数据结构"},
            {"id": "p", "stage": "primary", "subject": "数学"},
            {"id": "i1", "stage": "interview", "role": "后端"},
            {"id": "i2", "stage": "interview", "role": "前端"},
        ]
        out = filter_by_profile(qs, resolve_profile("java-backend", "中级"))
        ids = {q["id"] for q in out}
        self.assertIn("u", ids)
        self.assertIn("i1", ids)
        self.assertNotIn("p", ids)
        self.assertNotIn("i2", ids)

    def test_profile_score_in_aggregate(self):
        cfg = {
            "weights": {"preset": "p", "presets": {"p": {"undergrad": 1.0, "interview": 1.0}}},
            "profile": {"id": "java-backend", "level": "中级"},
        }
        results = [
            {"id": "u", "stage": "undergrad", "stage_name": "大学", "subject": "数据结构",
             "type": "choice", "points": 10, "capabilities": ["知识"], "tags": [],
             "grading": {"score": 10, "max": 10, "method": "exact",
                         "fraction": 1.0, "correct": True, "detail": {}}, "error": None},
            {"id": "i", "stage": "interview", "stage_name": "面试", "subject": "后端",
             "role": "后端", "type": "interview", "points": 10,
             "capabilities": ["理解"], "tags": [],
             "grading": {"score": 0, "max": 10, "method": "judge",
                         "fraction": 0.0, "correct": False, "detail": {}}, "error": None},
        ]
        out = aggregate(results, cfg)
        p = out["profile"]
        self.assertEqual(p["id"], "java-backend")
        expected = (1.0 * 0.30 + 0.0 * 0.35) / (0.30 + 0.35)
        self.assertAlmostEqual(p["score"], round(expected * 100, 2))


if __name__ == "__main__":
    unittest.main()
