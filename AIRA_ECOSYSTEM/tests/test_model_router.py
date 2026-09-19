"""
tests/test_model_router.py — unit test Sprint 1 (Task Classifier, Router,
Policy, failover). Memakai DB sementara dan client palsu — TIDAK menyentuh
database asli maupun provider LLM.

Jalankan dari root AIRA_ECOSYSTEM/:
    python -m unittest tests.test_model_router -v
"""

import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.rei.provider_client import ProviderClient, call_model
from core.events import event_bus
from core.model_policy import ModelPolicy
from core.model_router import ModelRouter
from core.model_store import ModelStore
from core.model_types import TaskClassification
from core.task_classifier import TaskClassifier, parse_classification

# model_id sengaja palsu (test/...) - bukan ID provider sungguhan.
FAKE_MODELS = [
    ("gemma3", "ollama", "test/gemma3", "Gemma 3", "general", 8192),
    ("glm", "openrouter", "test/glm-5.2", "GLM 5.2", "coding", 128000),
    ("nemotron_super", "openrouter", "test/nemotron-super", "Nemotron Super", "networking", 128000),
    ("nemotron_ultra", "openrouter", "test/nemotron-ultra", "Nemotron Ultra", "reasoning", 256000),
    ("nano_omni", "openrouter", "test/nano-omni", "Nano Omni", "vision", 32000),
]
ROUTING = {
    "general": "gemma3", "reasoning": "nemotron_ultra", "coding": "glm", "networking": "nemotron_super",
    "vision": "nano_omni", "voice": "gemma3", "retrieval": "gemma3", "automation": "gemma3",
}


def make_env(tmp: str):
    store = ModelStore(Path(tmp) / "router_test.db", seed=False)

    for custom_id, provider, model_id, name, label, ctx in FAKE_MODELS:
        result = store.create_model(provider, model_id, name, label, ctx, True, custom_id=custom_id)
        assert result["success"], result

    for label, model_id in ROUTING.items():
        assert store.set_default_model(label, model_id)["success"]

    assert store.set_policy(fallback_model_id="gemma3", retry_provider=0)["success"]

    policy = ModelPolicy(store)
    return store, policy, ModelRouter(store, policy)


class EventCapture:
    def __init__(self, *names):
        self.names, self.events, self._tokens = names, [], []

    def __enter__(self):
        for name in self.names:
            self._tokens.append((name, event_bus.subscribe(name, lambda e: self.events.append((e.event, e.data)))))
        return self

    def __exit__(self, *exc):
        for name, token in self._tokens:
            event_bus.unsubscribe(name, token)

    def of(self, name):
        return [data for event, data in self.events if event == name]


class FakeClient:
    def __init__(self, content=None, error=None):
        self.content, self.error, self.calls = content, error, []

    def chat(self, provider, model, messages, tools=None, **kwargs):
        self.calls.append({"provider": provider, "model": model, "messages": messages, **kwargs})
        if self.error:
            return {"error": self.error, "error_type": "other"}
        return {"message": {"role": "assistant", "content": self.content}, "usage": None}


class TestParse(unittest.TestCase):

    def test_valid_json(self):
        result = parse_classification(
            '{"primary_label":"coding","confidence":0.97,"requires_tools":true,'
            '"requires_vision":false,"requires_voice":false}'
        )
        self.assertEqual((result.primary_label, result.confidence, result.requires_tools), ("coding", 0.97, True))

    def test_strips_think_block_and_code_fence(self):
        raw = '<think>hmm {"a":1}</think>\n```json\n{"primary_label":"networking","confidence":0.8}\n```'
        self.assertEqual(parse_classification(raw).primary_label, "networking")

    def test_garbage_falls_back(self):
        self.assertEqual(parse_classification("bukan json").to_dict(), TaskClassification.fallback().to_dict())
        self.assertEqual(parse_classification(None).primary_label, "general")

    def test_invalid_label_falls_back(self):
        result = parse_classification('{"primary_label":"cooking","confidence":0.9}')
        self.assertEqual((result.primary_label, result.confidence), ("general", 0.5))

    def test_confidence_is_clamped(self):
        self.assertEqual(parse_classification('{"primary_label":"coding","confidence":7}').confidence, 1.0)


class TestClassifier(unittest.TestCase):

    def test_uses_general_model_and_publishes_event(self):
        with tempfile.TemporaryDirectory() as tmp, EventCapture("task.classified") as cap:
            _, _, router = make_env(tmp)
            client = FakeClient('{"primary_label":"coding","confidence":0.97}')

            result = TaskClassifier(router=router, client=client).classify("Refactor FastAPI")

            self.assertEqual(result.primary_label, "coding")
            self.assertEqual(client.calls[0]["model"], "test/gemma3")   # model label general
            self.assertEqual(cap.of("task.classified"), [{"label": "coding", "confidence": 0.97}])

    def test_provider_error_falls_back_to_general(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, router = make_env(tmp)
            result = TaskClassifier(router=router, client=FakeClient(error="boom")).classify("apa saja")
            self.assertEqual((result.primary_label, result.confidence), ("general", 0.5))


class TestAcceptance(unittest.TestCase):

    def _select(self, label):
        with tempfile.TemporaryDirectory() as tmp:
            _, _, router = make_env(tmp)
            return router.select(TaskClassification(primary_label=label, confidence=0.9))

    def test1_coding_routes_to_glm(self):
        self.assertEqual(self._select("coding").display_name, "GLM 5.2")

    def test2_networking_routes_to_nemotron_super(self):
        self.assertEqual(self._select("networking").display_name, "Nemotron Super")

    def test3_reasoning_routes_to_nemotron_ultra(self):
        self.assertEqual(self._select("reasoning").display_name, "Nemotron Ultra")

    def test4_disabled_glm_falls_back_to_gemma_with_event(self):
        with tempfile.TemporaryDirectory() as tmp, EventCapture("model.fallback", "model.selected") as cap:
            store, _, router = make_env(tmp)
            self.assertTrue(store.update_model("glm", enabled=False)["success"])

            selected = router.select(TaskClassification(primary_label="coding", confidence=0.95))

            self.assertEqual(selected.display_name, "Gemma 3")
            fallback = cap.of("model.fallback")[0]
            self.assertEqual((fallback["from"], fallback["to"]), ("glm", "gemma3"))
            self.assertEqual(cap.of("model.selected")[0]["label"], "coding")


class TestPolicy(unittest.TestCase):

    def test_context_exceeded_prefers_larger_model_same_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, policy, router = make_env(tmp)
            store.create_model("openrouter", "test/glm-long", "GLM Long", "coding", 200000, True, custom_id="glm_long")

            glm = router.select(TaskClassification(primary_label="coding"))
            chosen = policy.check_context(glm, estimated_tokens=150000)

            self.assertEqual(chosen.id, "glm_long")

    def test_context_exceeded_without_candidate_uses_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, EventCapture("model.fallback") as cap:
            _, policy, router = make_env(tmp)
            glm = router.select(TaskClassification(primary_label="coding"))

            chosen = policy.check_context(glm, estimated_tokens=200000)

            self.assertEqual(chosen.id, "gemma3")
            self.assertEqual(cap.of("model.fallback")[0]["reason"], "context_exceeded")

    def test_small_prompt_keeps_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            _, policy, router = make_env(tmp)
            glm = router.select(TaskClassification(primary_label="coding"))
            self.assertEqual(policy.check_context(glm, 1000).id, "glm")


class TestFailover(unittest.TestCase):

    def test_provider_failure_switches_to_fallback(self):
        with tempfile.TemporaryDirectory() as tmp, EventCapture("model.fallback", "model.failed") as cap:
            _, policy, router = make_env(tmp)
            glm = router.select(TaskClassification(primary_label="coding"))

            replies = [
                {"error": "429", "error_type": "rate_limit"},
                {"message": {"role": "assistant", "content": "ok", "tool_calls": []}, "usage": None},
            ]

            with mock.patch.object(ProviderClient, "chat", side_effect=replies) as chat:
                result = call_model([{"role": "user", "content": "hi"}], [], glm, policy=policy, router=router)

            self.assertEqual(result["model"]["id"], "gemma3")
            self.assertEqual(chat.call_args_list[0].kwargs["model"], "test/glm-5.2")
            self.assertEqual(chat.call_args_list[1].kwargs["model"], "test/gemma3")
            self.assertEqual(len(cap.of("model.failed")), 1)
            self.assertEqual(cap.of("model.fallback")[0]["from"], "glm")


class TestStore(unittest.TestCase):

    def test_cannot_delete_model_in_use(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _, _ = make_env(tmp)
            result = store.delete_model("glm")
            self.assertFalse(result["success"])
            self.assertTrue(result["in_use"])

    def test_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            store, _, _ = make_env(tmp)
            self.assertFalse(store.create_model("nope", "x", "X")["success"])
            self.assertFalse(store.create_model("ollama", "x", "X", label="cooking")["success"])
            self.assertFalse(store.set_default_model("coding", "tidak_ada")["success"])


if __name__ == "__main__":
    unittest.main()