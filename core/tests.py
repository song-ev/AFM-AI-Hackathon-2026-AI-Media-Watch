"""Provider configuration must never silently select a shared endpoint."""
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from core import llm
from core.exceptions import ModuleDependencyError


@override_settings(
    LLM_API_KEY="", LLM_BASE_URL="", LLM_MODEL="",
    ANTHROPIC_API_KEY="", ANTHROPIC_BASE_URL="", ANTHROPIC_MODEL="",
)
class ProviderConfigurationTests(SimpleTestCase):
    def test_empty_config_does_not_call_a_provider(self):
        self.assertFalse(llm.llm_is_configured())
        with patch.object(llm, "_get_openai_client") as factory:
            with self.assertRaises(ModuleDependencyError):
                llm.call_llm("test")
            factory.assert_not_called()

    @override_settings(LLM_API_KEY="test-placeholder")
    def test_key_alone_requires_endpoint_and_model(self):
        self.assertFalse(llm.llm_is_configured())
        with self.assertRaisesRegex(ModuleDependencyError, "LLM_BASE_URL.*LLM_MODEL"):
            llm.call_llm("test")

    @override_settings(ANTHROPIC_API_KEY="test-placeholder", ANTHROPIC_MODEL="test-model")
    def test_anthropic_has_no_implicit_endpoint(self):
        with self.assertRaisesRegex(ModuleDependencyError, "ANTHROPIC_BASE_URL"):
            llm.call_llm("test")

    @override_settings(
        LLM_API_KEY="test-placeholder", LLM_BASE_URL="https://llm.example.invalid/v1",
        LLM_MODEL="test-model",
    )
    def test_openai_client_uses_user_endpoint_and_model(self):
        factory = Mock()
        factory.return_value.chat.completions.create.return_value.choices = [
            SimpleNamespace(message=SimpleNamespace(content="reply"))
        ]
        with patch.object(llm, "_OPENAI_CLIENT", None), patch.dict(
            "sys.modules", {"openai": SimpleNamespace(OpenAI=factory)}
        ):
            self.assertTrue(llm.llm_is_configured())
            self.assertEqual(llm.call_llm("test"), "reply")
        self.assertEqual(factory.call_args.kwargs["base_url"], "https://llm.example.invalid/v1")
        self.assertEqual(factory.return_value.chat.completions.create.call_args.kwargs["model"], "test-model")

    @override_settings(
        ANTHROPIC_API_KEY="test-placeholder", ANTHROPIC_BASE_URL="https://llm.example.invalid",
        ANTHROPIC_MODEL="test-model",
    )
    def test_anthropic_client_uses_user_endpoint_and_model(self):
        factory = Mock()
        factory.return_value.messages.create.return_value.content = [SimpleNamespace(text="reply")]
        with patch.dict("sys.modules", {"anthropic": SimpleNamespace(Anthropic=factory)}):
            self.assertTrue(llm.llm_is_configured())
            self.assertEqual(llm.call_llm("test"), "reply")
        self.assertEqual(factory.call_args.kwargs["base_url"], "https://llm.example.invalid")
        self.assertEqual(factory.return_value.messages.create.call_args.kwargs["model"], "test-model")

    @override_settings(LLM_API_KEY="test-placeholder")
    def test_provider_errors_do_not_expose_credentials(self):
        with patch.object(llm, "_call_openai", side_effect=RuntimeError("private-token-value")):
            with self.assertLogs("aimw", level="WARNING") as log:
                with self.assertRaises(ModuleDependencyError) as raised:
                    llm.call_llm("test")
        self.assertNotIn("private-token-value", str(raised.exception))
        self.assertNotIn("private-token-value", " ".join(log.output))
