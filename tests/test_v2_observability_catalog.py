import unittest

from llm247_v2.observability.catalog import decode_activity_event, decode_discovery_event, decode_execution_event


class TestDiscoveryEventCatalog(unittest.TestCase):
    def test_decodes_new_candidate_found_event(self):
        decoded = decode_discovery_event({
            "module": "Discovery",
            "family": "candidate",
            "event_name": "candidate_found",
            "task_id": "t1",
            "detail": "[todo_scan] Fix parser bug",
        })

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["module"], "Discovery")
        self.assertEqual(decoded["family"], "candidate")
        self.assertEqual(decoded["event_name"], "candidate_found")
        self.assertEqual(decoded["task_id"], "t1")

    def test_decodes_new_queue_event_and_preserves_data(self):
        decoded = decode_discovery_event({
            "module": "Discovery",
            "family": "queue",
            "event_name": "candidate_queued",
            "task_id": "t1",
            "detail": "Fix parser bug (source=todo_scan)",
            "data": {
                "source": "todo_scan",
                "title": "Fix parser bug",
            },
        })

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["module"], "Discovery")
        self.assertEqual(decoded["family"], "queue")
        self.assertEqual(decoded["event_name"], "candidate_queued")
        self.assertEqual(decoded["data"]["source"], "todo_scan")

    def test_rejects_non_discovery_event(self):
        decoded = decode_discovery_event({
            "module": "Execution",
            "family": "tool_call",
            "event_name": "tool_call_started",
        })

        self.assertIsNone(decoded)


class TestExecutionEventCatalog(unittest.TestCase):
    def test_decodes_new_execution_tool_call_event(self):
        decoded = decode_execution_event({
            "module": "Execution",
            "family": "tool_call",
            "event_name": "tool_call_succeeded",
            "task_id": "t1",
            "detail": "edit_file src/app.py",
            "success": True,
            "data": {"tool_name": "edit_file"},
        })

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["module"], "Execution")
        self.assertEqual(decoded["family"], "tool_call")
        self.assertEqual(decoded["event_name"], "tool_call_succeeded")

    def test_decodes_new_execution_state_event(self):
        decoded = decode_execution_event({
            "module": "Execution",
            "family": "state",
            "event_name": "task_failed",
            "task_id": "t1",
            "detail": "test failure",
            "data": {"to_status": "failed"},
        })

        self.assertIsNotNone(decoded)
        assert decoded is not None
        self.assertEqual(decoded["action"], "task_failed")
        self.assertEqual(decoded["phase"], "execute")
        self.assertEqual(decoded["data"]["to_status"], "failed")

    def test_decode_activity_event_routes_discovery_and_execution(self):
        discovery = decode_activity_event({
            "module": "Discovery",
            "family": "candidate",
            "event_name": "candidate_found",
            "task_id": "t1",
        })
        execution = decode_activity_event({
            "module": "Execution",
            "family": "state",
            "event_name": "task_failed",
            "task_id": "t1",
        })

        self.assertEqual(discovery["module"], "Discovery")
        self.assertEqual(execution["module"], "Execution")


if __name__ == "__main__":
    unittest.main()
