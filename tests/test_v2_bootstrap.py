import tempfile
import unittest
from pathlib import Path
from unittest import mock

from llm247_v2.__main__ import _bootstrap_status, parse_args
from llm247_v2.core.models import ModelType
from llm247_v2.storage.model_registry import ModelRegistryStore


class TestBootstrapStatus(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = ModelRegistryStore(Path(self.tmp.name) / "models.db")

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_requires_setup_when_no_default_llm_exists(self):
        status = _bootstrap_status(self.store)

        self.assertFalse(status["ready"])
        self.assertTrue(status["requires_setup"])
        self.assertIn("default_llm", status["missing"])

    def test_is_ready_after_registering_one_llm(self):
        self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="default-model",
            api_key="secret-ak",
        )

        status = _bootstrap_status(self.store)

        self.assertTrue(status["ready"])
        self.assertFalse(status["requires_setup"])
        self.assertEqual(status["missing"], [])

    def test_parse_args_accepts_api_key_file(self):
        with mock.patch("sys.argv", ["llm247_v2", "--with-ui", "--api-key-file", "/tmp/api_key.yaml"]):
            args = parse_args()

        self.assertTrue(args.with_ui)
        self.assertEqual(args.api_key_file, "/tmp/api_key.yaml")

    def test_missing_api_key_file_is_ignored(self):
        from llm247_v2.__main__ import _import_models_from_api_key_file

        logger = mock.Mock()

        imported = _import_models_from_api_key_file(
            logger=logger,
            model_store=self.store,
            api_key_file="/tmp/does-not-exist-api_key.yaml",
        )

        self.assertEqual(imported, [])
        logger.warning.assert_called_once()


if __name__ == "__main__":
    unittest.main()
