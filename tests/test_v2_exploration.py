import tempfile
import time
import unittest
from pathlib import Path

from llm247_v2.core.constitution import _default_constitution
from llm247_v2.discovery.exploration import (
    BUILTIN_STRATEGIES,
    ExplorationMap,
    AreaStatus,
    load_exploration_map,
    record_strategy_result,
    save_exploration_map,
    scan_complexity,
    select_strategy,
)
from llm247_v2.core.models import Directive, TaskSourceConfig


class TestExplorationMap(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "emap.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_save_and_load(self):
        emap = ExplorationMap()
        emap.areas["src/utils"] = AreaStatus(path="src/utils", explore_count=3, tasks_found=5)
        emap.total_cycles = 10
        save_exploration_map(self.path, emap)

        loaded = load_exploration_map(self.path)
        self.assertEqual(loaded.total_cycles, 10)
        self.assertIn("src/utils", loaded.areas)
        self.assertEqual(loaded.areas["src/utils"].tasks_found, 5)

    def test_load_missing(self):
        emap = load_exploration_map(Path("/nonexistent/emap.json"))
        self.assertEqual(emap.total_cycles, 0)
        self.assertEqual(len(emap.areas), 0)

    def test_load_corrupt(self):
        self.path.write_text("not json", encoding="utf-8")
        emap = load_exploration_map(self.path)
        self.assertEqual(emap.total_cycles, 0)


class TestRecordStrategyResult(unittest.TestCase):
    def test_updates_map(self):
        emap = ExplorationMap()
        record_strategy_result(emap, "todo_sweep", ["src/"], 5)
        self.assertEqual(emap.total_cycles, 1)
        self.assertIn("src/", emap.areas)
        self.assertEqual(emap.areas["src/"].tasks_found, 5)
        self.assertEqual(len(emap.strategy_history), 1)

    def test_accumulates(self):
        emap = ExplorationMap()
        record_strategy_result(emap, "todo_sweep", ["src/"], 3)
        record_strategy_result(emap, "test_coverage", ["src/"], 2)
        self.assertEqual(emap.total_cycles, 2)
        self.assertEqual(emap.areas["src/"].tasks_found, 5)


class TestSelectStrategy(unittest.TestCase):
    def test_returns_strategy(self):
        emap = ExplorationMap()
        directive = Directive()
        constitution = _default_constitution()
        strategy = select_strategy(emap, directive, constitution, queued_task_count=0)
        self.assertIsNotNone(strategy)
        self.assertIn(strategy.name, BUILTIN_STRATEGIES)

    def test_todo_sweep_when_queue_full(self):
        emap = ExplorationMap()
        directive = Directive()
        constitution = _default_constitution()
        strategy = select_strategy(emap, directive, constitution, queued_task_count=10)
        self.assertEqual(strategy.name, "todo_sweep")

    def test_deep_review_every_5_cycles(self):
        emap = ExplorationMap(total_cycles=4)
        record_strategy_result(emap, "x", [], 0)
        directive = Directive()
        constitution = _default_constitution()
        strategy = select_strategy(emap, directive, constitution, queued_task_count=0)
        self.assertEqual(strategy.name, "deep_module_review")


class TestScanComplexity(unittest.TestCase):
    def test_finds_long_files(self):
        tmp = tempfile.TemporaryDirectory()
        workspace = Path(tmp.name)
        src = workspace / "src" / "pkg"
        src.mkdir(parents=True)
        (src / "big.py").write_text("\n".join([f"x_{i} = {i}" for i in range(400)]), encoding="utf-8")
        (src / "small.py").write_text("x = 1\n", encoding="utf-8")

        findings = scan_complexity(workspace, max_lines=300)
        big_files = [f for f in findings if "big.py" in f["file"]]
        self.assertGreater(len(big_files), 0)
        tmp.cleanup()


if __name__ == "__main__":
    unittest.main()
