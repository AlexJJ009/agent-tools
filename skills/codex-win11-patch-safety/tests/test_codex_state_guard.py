import importlib.util
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "codex_state_guard.py"
SPEC = importlib.util.spec_from_file_location("codex_state_guard", MODULE_PATH)
guard = importlib.util.module_from_spec(SPEC)
assert SPEC.loader
SPEC.loader.exec_module(guard)
AUDIT_PATH = Path(__file__).parents[1] / "scripts" / "audit_patch_script.py"
AUDIT_SPEC = importlib.util.spec_from_file_location("audit_patch_script", AUDIT_PATH)
audit_script = importlib.util.module_from_spec(AUDIT_SPEC)
assert AUDIT_SPEC.loader
AUDIT_SPEC.loader.exec_module(audit_script)


class GuardTests(unittest.TestCase):
    def make_home(self, root: Path) -> Path:
        home = root / "User"
        (home / ".codex" / "sessions").mkdir(parents=True)
        (home / ".ssh").mkdir(parents=True)
        (home / ".cc-switch").mkdir(parents=True)
        (home / "AppData" / "Roaming" / "Codex").mkdir(parents=True)
        (home / ".codex" / "auth.json").write_text('{"tokens":"secret"}', encoding="utf-8")
        (home / ".codex" / "config.toml").write_text(
            'model_provider = "custom"\nmodel = "gpt-5.6-terra"\n'
            '[model_providers.custom]\nbase_url = "https://example.invalid/v1"\nenv_key = "OPENAI_API_KEY"\n',
            encoding="utf-8",
        )
        (home / ".codex" / ".codex-global-state.json").write_text('{"projects":["one"]}', encoding="utf-8")
        (home / ".codex" / "sessions" / "one.jsonl").write_text(
            json.dumps({"type": "session_meta", "payload": {"model_provider": "custom"}}) + "\n",
            encoding="utf-8",
        )
        (home / ".ssh" / "config").write_text("Host example\n", encoding="utf-8")
        (home / ".ssh" / "id_ed25519").write_text("private", encoding="utf-8")
        (home / ".cc-switch" / "settings.json").write_text(
            json.dumps({"preserveCodexOfficialAuthOnSwitch": True}), encoding="utf-8"
        )
        self.make_state_db(home / ".codex" / "state_5.sqlite", ["custom", "custom"])
        self.make_table_db(home / ".codex" / "memories_1.sqlite", "jobs", 2)
        self.make_table_db(home / ".codex" / "goals_1.sqlite", "thread_goals", 1)
        self.make_table_db(home / ".codex" / "logs_2.sqlite", "logs", 3)
        self.make_cc_db(home / ".cc-switch" / "cc-switch.db")
        return home

    def make_state_db(self, path: Path, providers: list[str]) -> None:
        with sqlite3.connect(path) as db:
            db.execute("create table threads(id text, model_provider text)")
            db.executemany("insert into threads values(?,?)", [(str(i), item) for i, item in enumerate(providers)])

    def make_cc_db(self, path: Path) -> None:
        with sqlite3.connect(path) as db:
            db.execute("create table settings(key text,value text)")
            db.execute(
                "insert into settings values('common_config_codex',?)",
                ('model_catalog_json="x"\nservice_tier="priority"\nmodel_reasoning_effort="xhigh"\n',),
            )
            db.execute(
                "create table providers(id text,app_type text,category text,is_current integer,settings_config text)"
            )
            db.execute(
                "insert into providers values('default','codex','custom',1,?)",
                (json.dumps({"config": 'model_provider="custom"\n'}),),
            )

    def make_table_db(self, path: Path, table: str, count: int) -> None:
        with sqlite3.connect(path) as db:
            db.execute(f'create table "{table}"(id integer)')
            db.executemany(f'insert into "{table}" values(?)', [(item,) for item in range(count)])

    def test_manifest_detects_destructive_changes(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            before = guard.build_manifest(home)
            (home / ".codex" / "auth.json").write_text("", encoding="utf-8")
            (home / ".ssh" / "id_ed25519").unlink()
            (home / ".codex" / "sessions" / "one.jsonl").unlink()
            (home / ".codex" / "state_5.sqlite").unlink()
            self.make_state_db(home / ".codex" / "state_5.sqlite", ["custom"])
            result = guard.compare_manifests(before, guard.build_manifest(home))
            self.assertFalse(result["ok"])
            joined = "\n".join(result["failures"])
            self.assertIn("became empty", joined)
            self.assertIn("SSH private key count decreased", joined)
            self.assertIn("session JSONL count decreased", joined)
            self.assertIn("SQLite row count decreased", joined)

    def test_directory_same_count_replacement_and_file_rewrite_fail(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            before = guard.build_manifest(home)
            session = home / ".codex" / "sessions" / "one.jsonl"
            session.unlink()
            (session.parent / "replacement.jsonl").write_text("replacement\n", encoding="utf-8")
            (home / ".codex" / ".codex-global-state.json").write_text('{"projects":[]}', encoding="utf-8")
            result = guard.compare_manifests(before, guard.build_manifest(home))
            self.assertFalse(result["ok"])
            joined = "\n".join(result["failures"])
            self.assertIn("protected directory files disappeared", joined)
            self.assertIn("protected file content changed", joined)

    def test_session_append_is_allowed_but_rewrite_is_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            before = guard.build_manifest(home)
            session = home / ".codex" / "sessions" / "one.jsonl"
            with session.open("a", encoding="utf-8") as handle:
                handle.write('{"type":"event"}\n')
            self.assertTrue(guard.compare_manifests(before, guard.build_manifest(home))["ok"])
            session.write_text("rewritten but still long enough to avoid a truncation-only check\n", encoding="utf-8")
            result = guard.compare_manifests(before, guard.build_manifest(home))
            self.assertFalse(result["ok"])
            self.assertRegex("\n".join(result["failures"]), r"session (file was truncated|existing content was rewritten)")

    def test_config_allows_only_patch_whitelist(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            before = guard.build_manifest(home)
            config = home / ".codex" / "config.toml"
            config.write_text(
                'model_provider = "custom"\nmodel = "gpt-5.6-terra"\nservice_tier = "priority"\n'
                '[model_providers.custom]\nbase_url = "https://example.invalid/v1"\nenv_key = "OPENAI_API_KEY"\n',
                encoding="utf-8",
            )
            self.assertTrue(guard.compare_manifests(before, guard.build_manifest(home))["ok"])
            config.write_text(
                'model_provider = "other"\nmodel = "gpt-5.6-terra"\nservice_tier = "priority"\n'
                '[model_providers.custom]\nbase_url = "https://example.invalid/v1"\nenv_key = "OPENAI_API_KEY"\n',
                encoding="utf-8",
            )
            result = guard.compare_manifests(before, guard.build_manifest(home))
            self.assertFalse(result["ok"])
            self.assertIn("unapproved config.toml changes", "\n".join(result["failures"]))

    def test_missing_or_invalid_model_catalog_dependency_fails_closed(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = self.make_home(root)
            catalog = root / "model-catalog.json"
            catalog.write_text('{"models":[{"slug":"gpt-test"}]}', encoding="utf-8")
            config = home / ".codex" / "config.toml"
            config.write_text(
                f'model_catalog_json = "{catalog}"\n' + config.read_text(encoding="utf-8"),
                encoding="utf-8",
            )
            before = guard.build_manifest(home)
            self.assertFalse(guard.manifest_health_failures(before))

            catalog.unlink()
            missing = guard.build_manifest(home)
            self.assertIn(
                "config external dependency is missing: model_catalog_json",
                guard.manifest_health_failures(missing),
            )
            self.assertFalse(guard.compare_manifests(before, missing)["ok"])
            args = type("Args", (), {"user_home": home, "output": root / "config-health.json"})()
            self.assertEqual(guard.command_config_health(args), 2)
            self.assertFalse(json.loads(args.output.read_text(encoding="utf-8"))["ok"])

            catalog.write_text("not json", encoding="utf-8")
            invalid = guard.build_manifest(home)
            self.assertIn(
                "config external dependency is invalid: model_catalog_json",
                guard.manifest_health_failures(invalid),
            )

    def test_marketplace_path_normalization_requires_exact_explicit_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            config = home / ".codex" / "config.toml"
            config.write_text(
                config.read_text(encoding="utf-8")
                + "\n[marketplaces.openai-curated-remote-local]\n"
                + "source_type = \"local\"\n"
                + "source = \"/mnt/c/Users/Alex Mercer/Downloads/Report/CodexPatched/plugin-marketplace\"\n",
                encoding="utf-8",
            )
            before = guard.build_manifest(home)
            windows_root = r"C:\Users\Alex Mercer\Downloads\Report\CodexPatched\plugin-marketplace"
            config.write_text(
                config.read_text(encoding="utf-8").replace(
                    'source = "/mnt/c/Users/Alex Mercer/Downloads/Report/CodexPatched/plugin-marketplace"',
                    "source = '\\\\?\\C:\\Users\\Alex Mercer\\Downloads\\Report\\CodexPatched\\plugin-marketplace'",
                )
                + 'last_updated = "2026-07-28T00:00:00Z"\n',
                encoding="utf-8",
            )
            after = guard.build_manifest(home)
            self.assertFalse(guard.compare_manifests(before, after)["ok"])
            self.assertTrue(
                guard.compare_manifests(
                    before,
                    after,
                    {"openai-curated-remote-local": windows_root},
                )["ok"]
            )
            self.assertFalse(
                guard.compare_manifests(
                    before,
                    after,
                    {"openai-curated-remote-local": r"C:\wrong"},
                )["ok"]
            )
            self.assertFalse(
                guard.compare_manifests(
                    before,
                    after,
                    {"openai-curated-remote-local": "/mnt/c/Users/Alex Mercer/plugin-marketplace"},
                )["ok"]
            )

    def test_auth_and_cc_switch_semantics_do_not_expose_secrets(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            manifest_text = json.dumps(guard.build_manifest(home))
            self.assertNotIn('"tokens": "secret"', manifest_text)
            with sqlite3.connect(home / ".cc-switch" / "cc-switch.db") as db:
                db.execute("update providers set settings_config=? where id='default'", (json.dumps({"api_key": "sk-private", "config": 'model_provider="custom"\n'}),))
            manifest_text = json.dumps(guard.build_manifest(home))
            self.assertNotIn("sk-private", manifest_text)

    def test_memory_goal_rows_and_ssh_content_are_immutable(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            before = guard.build_manifest(home)
            with sqlite3.connect(home / ".codex" / "memories_1.sqlite") as db:
                db.execute("delete from jobs where id=0")
            (home / ".ssh" / "config").write_text("Host changed\n", encoding="utf-8")
            result = guard.compare_manifests(before, guard.build_manifest(home))
            self.assertFalse(result["ok"])
            joined = "\n".join(result["failures"])
            self.assertIn("memories_1.sqlite:jobs", joined)
            self.assertIn("SSH config content changed", joined)

    def test_project_memory_and_planning_are_compared(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = self.make_home(root)
            project = root / "project"
            (project / "memory").mkdir(parents=True)
            (project / "AGENTS.md").write_text("rules\n", encoding="utf-8")
            (project / "memory" / "decision.md").write_text("keep\n", encoding="utf-8")
            before = guard.build_manifest(home, (project,))
            (project / "memory" / "decision.md").unlink()
            result = guard.compare_manifests(before, guard.build_manifest(home, (project,)))
            self.assertFalse(result["ok"])
            self.assertIn("project memory/planning files disappeared", "\n".join(result["failures"]))
            project_failures = result["failures"]
            category_ok = not any(
                any(name in item for name in ("state_5.sqlite", "memories_1.sqlite", "goals_1.sqlite", "logs_2.sqlite", "codex-dev.db", "sessions", "project memory/planning", "project root"))
                for item in project_failures
            )
            self.assertFalse(category_ok)

    def test_verify_parser_has_no_ssh_skip_escape_hatch(self):
        parser = guard.build_parser()
        with self.assertRaises(SystemExit):
            parser.parse_args(["verify", "--user-home", "x", "--baseline", "y", "--skip-ssh-resolve"])

    def test_cc_switch_common_config_allows_patch_keys_only(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            before = guard.build_manifest(home)
            with sqlite3.connect(home / ".cc-switch" / "cc-switch.db") as db:
                db.execute(
                    "update settings set value=? where key='common_config_codex'",
                    ('model_catalog_json="y"\nservice_tier="priority"\nmodel_reasoning_effort="xhigh"\n',),
                )
            self.assertTrue(guard.compare_manifests(before, guard.build_manifest(home))["ok"])
            with sqlite3.connect(home / ".cc-switch" / "cc-switch.db") as db:
                db.execute(
                    "update settings set value=? where key='common_config_codex'",
                    ('model_catalog_json="y"\nservice_tier="priority"\nmodel_reasoning_effort="xhigh"\nmodel_provider="other"\n',),
                )
            result = guard.compare_manifests(before, guard.build_manifest(home))
            self.assertFalse(result["ok"])
            self.assertIn("unapproved CC Switch", "\n".join(result["failures"]))

    def test_snapshot_is_restorable_and_does_not_change_source(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = self.make_home(root)
            before = guard.build_manifest(home)
            backup = root / "backup"
            guard.copy_protected(home, backup)
            after = guard.build_manifest(home)
            self.assertTrue(guard.compare_manifests(before, after)["ok"])
            self.assertTrue((backup / "payload" / ".ssh" / "id_ed25519").exists())
            self.assertTrue((backup / "payload" / ".codex" / "state_5.sqlite").exists())

    def test_snapshot_rejects_an_unreadable_protected_database(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = self.make_home(root)
            (home / ".codex" / "logs_2.sqlite").write_text("not sqlite", encoding="utf-8")
            args = type("Args", (), {"user_home": home, "backup_root": root / "backup", "project_root": []})()
            self.assertEqual(guard.command_snapshot(args), 2)

    def test_snapshot_copies_project_memory_and_planning(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = self.make_home(root)
            project = root / "project"
            (project / "memory").mkdir(parents=True)
            (project / "AGENTS.md").write_text("rules\n", encoding="utf-8")
            (project / "memory" / "decision.md").write_text("keep\n", encoding="utf-8")
            destination = root / "backup"
            args = type("Args", (), {"user_home": home, "backup_root": destination, "project_root": [project]})()
            self.assertEqual(guard.command_snapshot(args), 0)
            snapshot = next(item for item in destination.iterdir() if item.is_dir())
            self.assertTrue((snapshot / "project-payload" / "project-001" / "AGENTS.md").exists())
            self.assertTrue((snapshot / "project-payload" / "project-001" / "memory" / "decision.md").exists())

    def test_checkpoint_deduplicates_unchanged_state(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            home = self.make_home(root)
            backup = root / "checkpoints"
            args = type("Args", (), {"user_home": home, "backup_root": backup})()
            self.assertEqual(guard.command_checkpoint(args), 0)
            first = sorted(item for item in backup.iterdir() if item.is_dir())
            self.assertEqual(guard.command_checkpoint(args), 0)
            second = sorted(item for item in backup.iterdir() if item.is_dir())
            self.assertEqual(first, second)
            (home / ".ssh" / "config").write_text("Host changed\n", encoding="utf-8")
            self.assertEqual(guard.command_checkpoint(args), 0)
            third = sorted(item for item in backup.iterdir() if item.is_dir())
            self.assertEqual(len(third), len(first) + 1)

    def test_launcher_lint_rejects_isolated_profile(self):
        self.assertFalse(guard.lint_launcher('--user-data-dir="C:\\tmp\\profile"')["ok"])
        self.assertTrue(guard.lint_launcher("")["ok"])

    def test_static_audit_rejects_profile_override_and_protected_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            unsafe = Path(temp) / "unsafe.ps1"
            unsafe.write_text(
                'Start-Process app.exe -ArgumentList "--user-data-dir=x"\n'
                'Remove-Item "$env:USERPROFILE\\.ssh" -Recurse\n',
                encoding="utf-8",
            )
            result = audit_script.audit([unsafe])
            self.assertFalse(result["ok"])
            self.assertEqual({item["rule"] for item in result["findings"]}, {"profile_override", "destructive_protected_path"})

    def test_cc_switch_audit_is_read_only_and_reports_non_target(self):
        with tempfile.TemporaryDirectory() as temp:
            home = self.make_home(Path(temp))
            with sqlite3.connect(home / ".codex" / "state_5.sqlite") as db:
                db.execute("insert into threads values('mock','mock')")
            result = guard.audit_cc_switch(home, "custom")
            self.assertFalse(result["ok"])
            self.assertEqual(result["stateProviderCounts"]["mock"], 1)
            self.assertEqual(result["commonConfigMissingKeys"], [])
            self.assertTrue(result["preserveCodexOfficialAuthOnSwitch"])


if __name__ == "__main__":
    unittest.main()
