import unittest

from llm247_v2.models import Directive, Task, TaskSourceConfig
from llm247_v2.value import (
    TaskValue,
    assess_task_value_heuristic,
    format_value_log,
    rank_and_filter,
    should_skip_discovery,
)


class TestHeuristicAssessment(unittest.TestCase):
    def _make_task(self, **kwargs):
        defaults = dict(id="t1", title="Fix bug", description="Fix a bug in utils.py:42", source="todo_scan")
        defaults.update(kwargs)
        return Task(**defaults)

    def test_bug_task_high_severity(self):
        task = self._make_task(title="Fix BUG in parser", source="lint_check")
        v = assess_task_value_heuristic(task, Directive())
        severity = next(d for d in v.dimensions if d.name == "severity")
        self.assertGreaterEqual(severity.score, 0.8)

    def test_todo_task_medium_severity(self):
        task = self._make_task(title="Resolve TODO in utils.py", source="todo_scan")
        v = assess_task_value_heuristic(task, Directive())
        severity = next(d for d in v.dimensions if d.name == "severity")
        self.assertGreaterEqual(severity.score, 0.4)

    def test_alignment_with_focus(self):
        directive = Directive(focus_areas=["testing", "documentation"])
        task = self._make_task(title="Add tests for parser", source="test_gap")
        v = assess_task_value_heuristic(task, directive)
        alignment = next(d for d in v.dimensions if d.name == "alignment")
        self.assertGreaterEqual(alignment.score, 0.5)

    def test_no_focus_areas(self):
        task = self._make_task()
        v = assess_task_value_heuristic(task, Directive())
        alignment = next(d for d in v.dimensions if d.name == "alignment")
        self.assertEqual(alignment.score, 0.5)

    def test_actionability_with_file_ref(self):
        task = self._make_task(description="File: src/parser.py\nLine: 42\nContent: TODO fix")
        v = assess_task_value_heuristic(task, Directive())
        act = next(d for d in v.dimensions if d.name == "actionability")
        self.assertGreaterEqual(act.score, 0.7)

    def test_should_execute_flag(self):
        task = self._make_task(title="Fix syntax error", source="lint_check", description="File: x.py\nLine: 1")
        v = assess_task_value_heuristic(task, Directive(focus_areas=["code_quality"]))
        self.assertTrue(v.should_execute)


class TestRankAndFilter(unittest.TestCase):
    def test_ranks_by_score(self):
        t1 = Task(id="t1", title="Low", description="x", source="manual")
        t2 = Task(id="t2", title="High", description="x", source="manual")
        values = [
            TaskValue("t1", 0.3, [], "skip", False),
            TaskValue("t2", 0.8, [], "execute", True),
        ]
        result = rank_and_filter([t1, t2], values, max_tasks=5)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].id, "t2")

    def test_filters_low_value(self):
        t1 = Task(id="t1", title="Low", description="x", source="manual")
        values = [TaskValue("t1", 0.1, [], "skip", False)]
        result = rank_and_filter([t1], values, max_tasks=5)
        self.assertEqual(len(result), 0)

    def test_max_tasks_limit(self):
        tasks = [Task(id=f"t{i}", title=f"T{i}", description="x", source="manual") for i in range(10)]
        values = [TaskValue(f"t{i}", 0.8, [], "execute", True) for i in range(10)]
        result = rank_and_filter(tasks, values, max_tasks=3)
        self.assertEqual(len(result), 3)


class TestSkipDiscovery(unittest.TestCase):
    def test_skip_when_queue_full(self):
        self.assertTrue(should_skip_discovery(10, threshold=5))

    def test_no_skip_when_queue_empty(self):
        self.assertFalse(should_skip_discovery(0, threshold=5))

    def test_boundary(self):
        self.assertTrue(should_skip_discovery(5, threshold=5))
        self.assertFalse(should_skip_discovery(4, threshold=5))


class TestFormatValueLog(unittest.TestCase):
    def test_format(self):
        from llm247_v2.value import ValueDimension
        values = [
            TaskValue("abc12345", 0.75, [ValueDimension("impact", 0.8, "test")], "execute", True),
        ]
        log = format_value_log(values)
        self.assertIn("abc12345", log)
        self.assertIn("0.750", log)


if __name__ == "__main__":
    unittest.main()
