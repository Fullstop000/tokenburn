import tempfile
import unittest
from pathlib import Path

from llm247_v2.core.models import ModelBindingPoint, ModelType
from llm247_v2.storage.model_registry import MODEL_BINDING_SPECS, ModelRegistryStore


class TestModelRegistryStore(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "models.db"
        self.store = ModelRegistryStore(self.db_path)

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_register_and_list_models(self):
        model = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="gpt-test",
            api_key="secret-ak",
            desc="Primary planner model",
        )

        models = self.store.list_models()

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].id, model.id)
        self.assertEqual(models[0].model_name, "gpt-test")
        self.assertEqual(models[0].api_key, "secret-ak")
        self.assertEqual(models[0].desc, "Primary planner model")

    def test_list_models_filters_by_type(self):
        self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://llm.example.com/v1",
            model_name="planner-model",
            api_key="llm-ak",
            desc="LLM for planning",
        )
        self.store.register_model(
            model_type=ModelType.EMBEDDING.value,
            api_path="https://embed.example.com/api/v3/embeddings/multimodal",
            model_name="embed-model",
            api_key="embed-ak",
            desc="Embedding model",
        )

        llm_models = self.store.list_models(model_type=ModelType.LLM.value)
        embedding_models = self.store.list_models(model_type=ModelType.EMBEDDING.value)

        self.assertEqual(len(llm_models), 1)
        self.assertEqual(llm_models[0].model_name, "planner-model")
        self.assertEqual(len(embedding_models), 1)
        self.assertEqual(embedding_models[0].model_name, "embed-model")
        self.assertEqual(
            embedding_models[0].api_path,
            "https://embed.example.com/api/v3/embeddings/multimodal",
        )
        self.assertEqual(embedding_models[0].base_url, "")

    def test_register_embedding_requires_api_path(self):
        model = self.store.register_model(
            model_type=ModelType.EMBEDDING.value,
            api_path="https://embed.example.com/api/v3/embeddings/multimodal",
            model_name="embed-model",
            api_key="embed-ak",
            desc="Multimodal embedding model",
        )

        self.assertEqual(model.api_path, "https://embed.example.com/api/v3/embeddings/multimodal")
        self.assertEqual(model.base_url, "")

    def test_register_embedding_rejects_missing_api_path(self):
        with self.assertRaisesRegex(ValueError, "api_path"):
            self.store.register_model(
                model_type=ModelType.EMBEDDING.value,
                model_name="embed-model",
                api_key="embed-ak",
                desc="Broken embedding model",
            )

    def test_set_and_get_binding(self):
        model = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Planner model",
        )

        self.store.set_binding(ModelBindingPoint.EXECUTION.value, model.id)
        bindings = self.store.list_bindings()

        self.assertEqual(bindings[ModelBindingPoint.EXECUTION.value].model_id, model.id)

    def test_get_default_model_returns_latest_registered_llm(self):
        first = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="older-model",
            api_key="secret-ak-1",
            desc="Older",
        )
        second = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v2",
            model_name="newer-model",
            api_key="secret-ak-2",
            desc="Newer",
        )

        default_model = self.store.get_default_model(ModelType.LLM.value)

        self.assertIsNotNone(default_model)
        self.assertEqual(default_model.id, second.id)
        self.assertNotEqual(default_model.id, first.id)

    def test_clear_binding(self):
        model = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Planner model",
        )
        self.store.set_binding(ModelBindingPoint.EXECUTION.value, model.id)

        self.store.set_binding(ModelBindingPoint.EXECUTION.value, "")
        bindings = self.store.list_bindings()

        self.assertNotIn(ModelBindingPoint.EXECUTION.value, bindings)

    def test_update_model_preserves_secret_when_api_key_blank(self):
        model = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Planner model",
        )

        updated = self.store.update_model(
            model.id,
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v2",
            model_name="planner-model-v2",
            api_key="",
            desc="Updated planner model",
        )

        self.assertEqual(updated.id, model.id)
        self.assertEqual(updated.base_url, "https://example.com/v2")
        self.assertEqual(updated.model_name, "planner-model-v2")
        self.assertEqual(updated.api_key, "secret-ak")
        self.assertEqual(updated.desc, "Updated planner model")

    def test_delete_model_removes_related_bindings(self):
        model = self.store.register_model(
            model_type=ModelType.LLM.value,
            base_url="https://example.com/v1",
            model_name="planner-model",
            api_key="secret-ak",
            desc="Planner model",
        )
        self.store.set_binding(ModelBindingPoint.EXECUTION.value, model.id)

        self.store.delete_model(model.id)

        self.assertIsNone(self.store.get_model(model.id))
        self.assertIsNone(self.store.get_binding(ModelBindingPoint.EXECUTION.value))

    def test_binding_specs_cover_current_runtime_points(self):
        binding_points = {spec.binding_point for spec in MODEL_BINDING_SPECS}

        self.assertIn(ModelBindingPoint.EXECUTION.value, binding_points)
        self.assertIn(ModelBindingPoint.TASK_VALUE.value, binding_points)
        self.assertIn(ModelBindingPoint.DISCOVERY_GENERATION.value, binding_points)
        self.assertIn(ModelBindingPoint.INTEREST_DRIVEN_DISCOVERY.value, binding_points)
        self.assertIn(ModelBindingPoint.WEB_SEARCH_DISCOVERY.value, binding_points)
        self.assertIn(ModelBindingPoint.LEARNING_EXTRACTION.value, binding_points)
        self.assertIn(ModelBindingPoint.EXPERIENCE_MERGE.value, binding_points)


if __name__ == "__main__":
    unittest.main()
