import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from adapters.claude.native_hook import adapt, prepare

ROOT = Path(__file__).resolve().parents[1]
NATIVE = ROOT / "adapters/claude/native_hook.py"
NOTIFICATION = "<task-notification>\n<task-id>a0418ce7</task-id>\n<status>completed</status>\n</task-notification>"


def recorded_prompt(prompt_id, prompt="继续"):
    # Shape recorded from Claude Code 2.1.288 UserPromptSubmit stdin: no turn_id.
    return {"session_id": "77dbb470-32f6-46d7-a8cf-841e6d842ee9",
            "transcript_path": "/fixture/77dbb470-32f6-46d7-a8cf-841e6d842ee9.jsonl", "cwd": "/fixture/project",
            "prompt_id": prompt_id, "permission_mode": "default", "hook_event_name": "UserPromptSubmit", "prompt": prompt}


def run_native(event, *runtime):
    return subprocess.run([sys.executable, str(NATIVE), "--", *runtime], input=json.dumps(event),
                          text=True, capture_output=True)


def setUpModule():
    """Producers append to the agent-tools material ledger; keep it out of the user's data root."""
    global _LEDGER_TMP, _LEDGER_ENV
    import json as _json, os as _os, tempfile as _tempfile
    from pathlib import Path as _Path
    from unittest import mock as _mock
    _LEDGER_TMP = _tempfile.TemporaryDirectory(prefix='agent-tools-test-ledger-')
    config = _Path(_LEDGER_TMP.name) / 'config'
    (config / 'agent-tools').mkdir(parents=True)
    (config / 'agent-tools/config.json').write_text(_json.dumps({'data_root': str(_Path(_LEDGER_TMP.name) / 'data')}))
    _LEDGER_ENV = _mock.patch.dict(_os.environ, {'XDG_CONFIG_HOME': str(config), 'XDG_DATA_HOME': str(_Path(_LEDGER_TMP.name) / 'xdg-data')})
    _LEDGER_ENV.start()


def tearDownModule():
    _LEDGER_ENV.stop()
    _LEDGER_TMP.cleanup()


class NativeHookTests(unittest.TestCase):
    def test_bound_identity_and_decisions_survive(self):
        event = {"hook_event_name": "SessionStart", "session_id": "native-fixture", "cwd": "/fixture/project"}
        output = {"decision": "block", "reason": "original reason", "hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": "Read bound record; revision 2."}}
        result = adapt(event, copy.deepcopy(output), ["python", "/shared/learning-workflow-hook", "--state-root", "/fixture/state"])
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(result['reason'], output['reason'])
        self.assertIn('Native session_id=native-fixture;', result['hookSpecificOutput']['additionalContext'])
        self.assertIn(output['hookSpecificOutput']['additionalContext'], result['hookSpecificOutput']['additionalContext'])
        self.assertIn('/fixture/state', result['hookSpecificOutput']['additionalContext'])

    def test_prompt_context_is_not_padded_with_identity(self):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "native", "cwd": "/fixture"}
        self.assertEqual(adapt(event, {}, ["python", "/shared/learning-workflow-hook"]), {})

    def test_no_duplicate_unbound_identity(self):
        event = {"hook_event_name": "SessionStart", "session_id": "native", "cwd": "/fixture"}
        output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Native session_id=native; workspace=/fixture"}}
        self.assertEqual(adapt(event, copy.deepcopy(output), ['learning-workflow-hook']), output)

    def test_report_diagnostic_promoted_and_deny_unchanged(self):
        output = {"hookSpecificOutput": {"hookEventName": "Stop", "systemMessage": "original failure"}}
        self.assertEqual(adapt({'hook_event_name':'Stop'}, output, ['report_runtime.py']), {'systemMessage':'original failure'})
        deny = {'hookSpecificOutput': {'hookEventName':'PreToolUse', 'permissionDecision':'deny', 'permissionDecisionReason':'bound input pending'}}
        self.assertEqual(adapt({'hook_event_name':'PreToolUse'}, copy.deepcopy(deny), ['learning-workflow-hook']), deny)

    def test_task_notification_only_prompt_is_not_forwarded(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / "ran"
            runtime = [sys.executable, "-c", f"open({str(marker)!r}, 'w'); print('{{}}')"]
            for prompt in (NOTIFICATION, "\n" + NOTIFICATION + "\n" + NOTIFICATION + "\n"):
                result = run_native(recorded_prompt("p1", prompt), *runtime)
                self.assertEqual((result.returncode, json.loads(result.stdout)), (0, {}))
                self.assertFalse(marker.exists())
            # Real user text outside the envelopes is still user input.
            run_native(recorded_prompt("p1", NOTIFICATION + "\n继续"), *runtime)
            self.assertTrue(marker.exists())

    def test_non_json_runtime_output_degrades_to_message(self):
        result = run_native({"hook_event_name": "Stop"}, sys.executable, "-c", "print('Traceback: not json')")
        self.assertEqual(result.returncode, 0)
        self.assertIn("not a JSON object", json.loads(result.stdout)["systemMessage"])

    def test_identical_prompts_get_distinct_learning_inputs(self):
        from learning_workflow import hooks, runtime as r
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp); work = base / "project"; work.mkdir(); state = base / "hooks"
            query = base / "q.txt"; query.write_text("整理笔记")
            decision = {'activity': 'curation', 'interaction_mode': 'direct', 'workspace_context': 'repository',
                        'selected_skills': [], 'excluded_actions': [], 'material_refs': [], 'output_targets': ['notes'],
                        'rationale': 'fixture', 'unresolved': [], 'authorized_actions': ['curate'], 'project_id': 'fixture'}
            first, second = (dict(recorded_prompt(i), cwd=str(work)) for i in ("prompt-1", "prompt-2"))
            root = Path(r.init(query, decision, work, first["session_id"])['record'])
            hooks.bind(root, first["session_id"], work, state)
            count = lambda: len(r.read(root)['inputs'])
            before = count()
            hooks.process(first, state); hooks.process(second, state)
            self.assertEqual(count(), before + 1)  # the raw host payload collapses repeated prompts
            for event in (first, second, second):  # a retried submission stays idempotent
                hooks.process(prepare(event), state)
            self.assertEqual(count(), before + 3)


if __name__ == "__main__":
    unittest.main()
