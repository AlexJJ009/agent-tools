"""Verify native hook merging and preservation of unrelated Claude settings."""
from copy import deepcopy
from pathlib import Path
import shlex
import unittest

from adapters.claude import hooks


class ClaudeHooksTests(unittest.TestCase):
    home = Path("/tmp/claude-hook-profile")

    def test_native_commands_reuse_shared_runtimes(self):
        groups = hooks.hook_groups(self.home)
        self.assertEqual(set(groups), set(hooks.EVENTS))
        self.assertNotIn("Interrupt", groups)
        self.assertNotIn("SessionEnd", groups)
        self.assertEqual(len(groups["Stop"]), 3)
        self.assertEqual(len(groups["PreToolUse"]), 2)
        for event, event_groups in groups.items():
            for group in event_groups:
                for handler in group["hooks"]:
                    self.assertNotIn("additionalContextLimit", handler)
                    self.assertEqual(handler["type"], "command")
                    self.assertEqual(handler["timeout"], 30)
                    self.assertTrue(shlex.split(handler["command"]))
        commands = [group["hooks"][0]["command"] for group in groups["Stop"]]
        self.assertIn("learning-workflow-hook", commands[0])
        self.assertIn("agent_workflow.hooks", commands[1])
        self.assertIn("report_runtime.py", commands[2])

    def test_install_idempotent_preserves_auth_env_and_foreign_hooks(self):
        foreign = {"env": {"ANTHROPIC_API_KEY": "test-only"}, "permissions": {"allow": ["Read"]},
                   "model": "user-model", "hooks": {
                       "SessionStart": [{"matcher": "startup", "hooks": [
                           {"type": "command", "command": "echo foreign", "timeout": 9}]}],
                       "SessionEnd": [{"hooks": [{"type": "command", "command": "echo bye"}]}],
                       "Notification": []}}
        previous = deepcopy(foreign)
        installed = hooks.merge_install(foreign, self.home)
        self.assertEqual(foreign, previous)
        self.assertEqual(hooks.merge_install(installed, self.home), installed)
        self.assertEqual(hooks.check(installed, self.home)["status"], "pass")
        self.assertEqual(hooks.remove_owned(installed, self.home), foreign)

    def test_mixed_group_keeps_foreign_handlers_and_group_fields(self):
        managed = hooks.hook_groups(self.home)["Stop"][0]["hooks"][0]
        foreign = {"type": "command", "command": "echo custom", "statusMessage": "learning-workflow/1"}
        settings = {"hooks": {"Stop": [{"hooks": [managed, foreign], "matcher": "custom", "other": 1}]}}
        preserved = {"hooks": {"Stop": [{"hooks": [foreign], "matcher": "custom", "other": 1}]}}
        self.assertEqual(hooks.remove_owned(settings, self.home), preserved)
        installed = hooks.merge_install(settings, self.home)
        self.assertEqual(installed["hooks"]["Stop"][0], preserved["hooks"]["Stop"][0])
        hooks.check(installed, self.home)

    def test_marker_or_command_as_data_does_not_claim_ownership(self):
        command = hooks.hook_groups(self.home)["Stop"][0]["hooks"][0]["command"]
        settings = {"hooks": {"Stop": [{"hooks": [
            {"type": "command", "command": shlex.join(["echo", command]), "statusMessage": "learning-workflow/1"},
            {"type": "prompt", "command": command}]}]}}
        self.assertEqual(hooks.remove_owned(settings, self.home), settings)

    def test_check_rejects_removed_duplicated_or_changed_definitions(self):
        installed = hooks.merge_install({}, self.home)
        for mutation in ("removed", "duplicated", "changed", "unsupported"):
            damaged = deepcopy(installed)
            groups = damaged["hooks"]["Stop"]
            if mutation == "removed":
                groups.pop()
            elif mutation == "duplicated":
                groups.append(deepcopy(groups[0]))
            elif mutation == "changed":
                groups[0]["hooks"][0]["additionalContextLimit"] = 2500
            else:
                damaged["hooks"]["Interrupt"] = [groups.pop()]
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                hooks.check(damaged, self.home)
            hooks.check(hooks.merge_install(damaged, self.home), self.home)

    def test_malformed_refused_without_mutating_input(self):
        for settings in ([], {"hooks": None}, {"hooks": {"Stop": {}}},
                         {"hooks": {"Stop": [None]}}, {"hooks": {"Stop": [{"hooks": [None]}]}}):
            before = deepcopy(settings)
            with self.subTest(settings=settings):
                for operation in (hooks.merge_install, hooks.remove_owned, hooks.check):
                    with self.assertRaises(ValueError):
                        operation(settings, self.home)
                self.assertEqual(settings, before)


if __name__ == "__main__":
    unittest.main()
