import copy
import unittest

from adapters.claude.native_hook import adapt


class NativeHookTests(unittest.TestCase):
    def test_bound_identity_and_decisions_survive(self):
        event = {"hook_event_name": "UserPromptSubmit", "session_id": "native-fixture", "cwd": "/fixture/project"}
        output = {"decision": "block", "reason": "original reason", "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit", "additionalContext": "Read bound record; revision 2."}}
        result = adapt(event, copy.deepcopy(output), ["python", "/shared/learning-workflow-hook", "--state-root", "/fixture/state"])
        self.assertEqual(result['decision'], 'block')
        self.assertEqual(result['reason'], output['reason'])
        self.assertIn('Native session_id=native-fixture;', result['hookSpecificOutput']['additionalContext'])
        self.assertIn(output['hookSpecificOutput']['additionalContext'], result['hookSpecificOutput']['additionalContext'])
        self.assertIn('/fixture/state', result['hookSpecificOutput']['additionalContext'])

    def test_no_duplicate_unbound_identity(self):
        event = {"hook_event_name": "SessionStart", "session_id": "native", "cwd": "/fixture"}
        output = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "Native session_id=native; workspace=/fixture"}}
        self.assertEqual(adapt(event, copy.deepcopy(output), ['learning-workflow-hook']), output)

    def test_report_diagnostic_promoted_and_deny_unchanged(self):
        output = {"hookSpecificOutput": {"hookEventName": "Stop", "systemMessage": "original failure"}}
        self.assertEqual(adapt({'hook_event_name':'Stop'}, output, ['report_runtime.py']), {'systemMessage':'original failure'})
        deny = {'hookSpecificOutput': {'hookEventName':'PreToolUse', 'permissionDecision':'deny', 'permissionDecisionReason':'bound input pending'}}
        self.assertEqual(adapt({'hook_event_name':'PreToolUse'}, copy.deepcopy(deny), ['learning-workflow-hook']), deny)
