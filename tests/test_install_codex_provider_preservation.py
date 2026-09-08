import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]


def extract_shell_function(script: str, name: str, next_name: str) -> str:
    start = script.index(f"{name}() {{")
    end = script.index(f"\n{next_name}() {{", start)
    return script[start:end].rstrip()


class InstallCodexProviderPreservationTests(unittest.TestCase):
    def test_configure_defaults_preserves_existing_provider_endpoint_and_auth(self):
        install_text = (ROOT / "install.sh").read_text(encoding="utf-8")
        function = extract_shell_function(
            install_text,
            "configure_codex_defaults",
            "configure_codex_features",
        )

        with tempfile.TemporaryDirectory() as tmp:
            codex_home = Path(tmp) / ".codex"
            codex_home.mkdir()
            config = codex_home / "config.toml"
            config.write_text(
                textwrap.dedent(
                    """
                    model_provider = "custom"

                    [model_providers.custom]
                    name = "dragtokens"
                    base_url = "https://dragtokens.com/v1"
                    requires_openai_auth = false
                    env_key = "OPENAI_API_KEY"
                    supports_websockets = false
                    stream_idle_timeout_ms = 1
                    """
                ).lstrip(),
                encoding="utf-8",
            )
            runner = Path(tmp) / "run.sh"
            runner.write_text(
                textwrap.dedent(
                    f"""
                    set -euo pipefail
                    select_python_bin() {{ PYTHON_BIN=python3; }}
                    CODEX_HOME={codex_home}
                    CODEX_STREAM_IDLE_TIMEOUT_MS=1800000
                    CODEX_STREAM_MAX_RETRIES=20
                    CODEX_MODEL_CONTEXT_WINDOW=500000
                    CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT=430000
                    CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT_SCOPE=total
                    CODEX_MODEL_PROVIDER_ID=custom
                    CODEX_APPROVAL_POLICY=on-request
                    CODEX_SANDBOX_MODE=workspace-write
                    CODEX_APPROVALS_REVIEWER=guardian_subagent
                    CODEX_MODEL=gpt-5.5
                    CODEX_MODEL_REASONING_EFFORT=high
                    CODEX_SERVICE_TIER=priority
                    {function}
                    configure_codex_defaults
                    configure_codex_defaults
                    """
                ),
                encoding="utf-8",
            )

            subprocess.run(["bash", str(runner)], check=True, text=True)
            text = config.read_text(encoding="utf-8")
            preamble, provider = text.split("[model_providers.custom]", 1)

            self.assertIn("model_context_window = 500000", preamble)
            self.assertIn("model_auto_compact_token_limit = 430000", preamble)
            self.assertIn('model_auto_compact_token_limit_scope = "total"', preamble)
            self.assertIn('name = "dragtokens"', provider)
            self.assertIn('base_url = "https://dragtokens.com/v1"', provider)
            self.assertIn("requires_openai_auth = false", provider)
            self.assertIn('env_key = "OPENAI_API_KEY"', provider)
            self.assertIn("supports_websockets = true", provider)
            self.assertIn('wire_api = "responses"', provider)
            self.assertIn("stream_idle_timeout_ms = 1800000", provider)
            self.assertIn("stream_max_retries = 20", provider)
            self.assertEqual(provider.count("supports_websockets"), 1)
            self.assertEqual(provider.count("stream_idle_timeout_ms"), 1)


if __name__ == "__main__":
    unittest.main()
