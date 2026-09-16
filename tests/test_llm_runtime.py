import asyncio
import os
import sys
import tempfile
import types
import unittest

# The modules.hive package __init__ transitively imports
# modules.system.system_info, which requires the third-party `psutil`
# dependency that isn't installed in this project's venv. None of these
# tests exercise system_info (it only *calls* psutil functions at runtime),
# so register a minimal psutil module shim so the hive package imports
# cleanly - matching how the rest of the suite runs without psutil.
if "psutil" not in sys.modules:
    _psutil_shim = types.ModuleType("psutil")
    _psutil_shim.__all__ = []
    sys.modules["psutil"] = _psutil_shim

from modules.llmClient import LLMClient
from modules.hive import config as hive_config
from modules.hive.config import DEFAULT_CONFIG


class CloudRoutingClassificationTests(unittest.TestCase):
    """Cloud vs local reasoning classification is pure config inspection
    (no network contact). Ollama's ':cloud' model tag chooses the route."""

    def test_cloud_tag_is_classified_cloud(self):
        client = LLMClient(model="deepseek-v4-flash:cloud", api_type="ollama",
                           base_url="http://localhost:11434")
        self.assertTrue(client.is_cloud_routed)
        self.assertFalse(client.is_local)

    def test_local_tag_on_loopback_is_local(self):
        client = LLMClient(model="deepseek-v4-flash", api_type="ollama",
                           base_url="http://localhost:11434")
        self.assertFalse(client.is_cloud_routed)
        self.assertTrue(client.is_local)

    def test_non_loopback_endpoint_is_cloud(self):
        # Even a local-named-tag model is cloud if the endpoint is a remote host.
        client = LLMClient(model="deepseek-v4-flash", api_type="ollama",
                           base_url="http://10.0.0.5:11434")
        self.assertTrue(client.is_cloud_routed)
        self.assertFalse(client.is_local)

    def test_cloud_classification_is_case_insensitive(self):
        client = LLMClient(model="deepseek-v4-flash:CLOUD", api_type="ollama",
                           base_url="http://localhost:11434")
        self.assertTrue(client.is_cloud_routed)


class LocalVisionRefusalTests(unittest.TestCase):
    """describe_image() must refuse before any network call when this
    client is not local - screen/vision context must never leave the machine."""

    async def _describe(self, client):
        # A non-empty base64 payload that is never sent because is_local gates
        # first. Passing "not-really-base64" is fine - refusal precedes transport.
        return await client.describe_image("aW1hZ2U=", "describe the screen")

    def test_cloud_routed_client_refuses_vision(self):
        client = LLMClient(model="deepseek-v4-flash:cloud", api_type="ollama")
        with self.assertRaises(RuntimeError):
            asyncio.run(self._describe(client))

    def test_remote_endpoint_client_refuses_vision(self):
        client = LLMClient(model="gemma4:e4b", api_type="ollama",
                           base_url="http://10.0.0.5:11434")
        with self.assertRaises(RuntimeError):
            asyncio.run(self._describe(client))

    def test_local_client_is_not_refused(self):
        # Local client passes the is_local guard (the refusal is what we
        # assert on). We only check the guard decision, not the network call.
        client = LLMClient(model="gemma4:e4b", api_type="ollama",
                           base_url="http://localhost:11434")
        self.assertTrue(client.is_local)
        self.assertFalse(client.is_cloud_routed)


class ConfigAndDefaultDiagnosticTests(unittest.TestCase):
    """Repository defaults and the diagnostic helper that states the
    configured reasoning runtime without contacting the network."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old = os.environ.get("SARAH_HOME")
        os.environ["SARAH_HOME"] = self._tmp.name
        # Re-point the module-level constants to the temp home for this test.
        self._orig_config_path = hive_config.CONFIG_PATH
        hive_config.CONFIG_PATH = os.path.join(self._tmp.name, "hive_config.json")

    def tearDown(self):
        hive_config.CONFIG_PATH = self._orig_config_path
        if self._old is None:
            os.environ.pop("SARAH_HOME", None)
        else:
            os.environ["SARAH_HOME"] = self._old
        self._tmp.cleanup()

    def test_repository_default_is_ollama_cloud_reasoning(self):
        self.assertEqual(DEFAULT_CONFIG["api_type"], "ollama")
        self.assertEqual(DEFAULT_CONFIG["model"], "deepseek-v4-flash:cloud")
        self.assertIsNone(DEFAULT_CONFIG["base_url"])  # => LLMClient localhost default
        self.assertFalse(DEFAULT_CONFIG["auto_start_llama_server"])

    def test_default_reasoning_client_is_ollama_and_cloud(self):
        # No config file present -> defaults govern from_node_config.
        client = LLMClient.from_node_config()
        self.assertEqual(client.api_type, "ollama")
        self.assertEqual(client.model, "deepseek-v4-flash:cloud")
        self.assertEqual(client.base_url, "http://localhost:11434")
        self.assertTrue(client.is_cloud_routed)
        self.assertFalse(client.is_local)

    def test_diagnostic_reports_configured_runtime(self):
        client = LLMClient.from_node_config()
        report = client.describe_runtime()
        self.assertIn("api_type=ollama", report)
        self.assertIn("model=deepseek-v4-flash:cloud", report)
        self.assertIn("cloud-routed", report)
        self.assertIn("endpoint=http://localhost:11434", report)
        # Never any prompt content.
        self.assertNotIn("SYSTEM", report)

    def test_diagnostic_for_local_vision_model_is_local(self):
        client = LLMClient(model="gemma4:e4b", api_type="ollama",
                           base_url="http://localhost:11434")
        report = client.describe_runtime()
        self.assertIn("model=gemma4:e4b", report)
        self.assertIn("local", report)
        self.assertNotIn("cloud-routed", report)


if __name__ == "__main__":
    unittest.main()
