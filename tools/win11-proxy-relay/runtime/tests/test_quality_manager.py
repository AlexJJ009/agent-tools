import importlib.util
from dataclasses import replace
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest import mock


RUNTIME_DIR = Path(__file__).resolve().parents[1]
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))
SCRIPT = RUNTIME_DIR / "quality-manager.py"
SPEC = importlib.util.spec_from_file_location("quality_manager", SCRIPT)
quality_manager = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = quality_manager
SPEC.loader.exec_module(quality_manager)


def args(**overrides):
    base = {
        "switch_hold_seconds": 600,
        "quarantine_seconds": 600,
        "challenger_improvement": 0.20,
        "required_challenger_streak": 2,
        "api_timeout": 1,
        "delay_probes": 3,
        "delay_timeout_ms": 4000,
        "max_workers": 1,
        "shortlist_size": 3,
        "speed_ttl_seconds": 1800,
        "failure_memory_seconds": 1800,
        "max_speed_nodes_per_pool": 3,
        "speed_timeout": 1,
        "speed_url": quality_manager.SPEED_URL,
        "speed_bytes": quality_manager.SPEED_BYTES,
        "production_health_probes": 3,
        "production_health_timeout": 1,
        "current_failed_checks": 3,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def metric(node, median, jitter=10, failures=0, mbps=10):
    delay = {
        "node": node,
        "ok": failures <= 1,
        "median_ms": median,
        "p95_ms": median + jitter,
        "jitter_ms": jitter,
        "request_failure_ratio": failures / 3,
    }
    speed = {"node": node, "ok": True, "mbps": mbps}
    scored = quality_manager.score_candidate(delay, speed)
    return {"node": node, **scored, "delay": delay, "speed": speed}


def feitu_metric(node, median, jitter=10, failures=0, mbps=10):
    delay = {
        "node": node,
        "ok": failures == 0,
        "median_ms": median,
        "p95_ms": median + jitter,
        "jitter_ms": jitter,
        "request_failure_ratio": failures / 3,
    }
    speed = {"node": node, "ok": True, "mbps": mbps}
    scored = quality_manager.score_candidate(delay, speed, quality_manager.POOLS[1])
    return {"node": node, **scored, "delay": delay, "speed": speed}


class QualityManagerDecisionTests(unittest.TestCase):
    def setUp(self):
        self.pool = quality_manager.POOLS[0]

    def test_score_rejects_lossish_request_failures(self):
        delay = {
            "node": "poor",
            "ok": False,
            "median_ms": 100,
            "p95_ms": 100,
            "jitter_ms": 0,
            "request_failure_ratio": 2 / 3,
        }
        scored = quality_manager.score_candidate(delay, {"ok": True, "mbps": 100})
        self.assertFalse(scored["eligible"])
        self.assertEqual(scored["reason"], "failure_ratio_gt_1_of_3")

    def test_feitu_score_rejects_any_current_sample_failure(self):
        delay = {
            "node": "fast-flaky",
            "ok": True,
            "median_ms": 30,
            "p95_ms": 40,
            "jitter_ms": 10,
            "request_failure_ratio": 1 / 3,
        }
        scored = quality_manager.score_candidate(delay, {"ok": True, "mbps": 500}, quality_manager.POOLS[1])
        self.assertFalse(scored["eligible"])
        self.assertEqual(scored["reason"], "nonzero_request_failures")

    def test_feitu_bandwidth_matters_more_than_rtt_after_reliability_gate(self):
        slow_rtt_fast_download = feitu_metric("slow-rtt-fast-download", 500, jitter=30, mbps=200)
        fast_rtt_slow_download = feitu_metric("fast-rtt-slow-download", 30, jitter=5, mbps=1)
        self.assertTrue(slow_rtt_fast_download["eligible"])
        self.assertTrue(fast_rtt_slow_download["eligible"])
        self.assertLess(slow_rtt_fast_download["score"], fast_rtt_slow_download["score"])

    def test_feitu_slow_reliable_beats_fast_flaky_by_eligibility(self):
        slow_reliable = feitu_metric("slow-reliable", 700, jitter=20, failures=0, mbps=5)
        fast_flaky = feitu_metric("fast-flaky", 20, jitter=5, failures=1, mbps=500)
        ranked = sorted([item for item in [slow_reliable, fast_flaky] if item["eligible"]], key=lambda item: item["score"])
        self.assertEqual([item["node"] for item in ranked], ["slow-reliable"])

    def test_score_accepts_perfect_zero_failure_sample(self):
        delay = {
            "node": "perfect",
            "ok": True,
            "median_ms": 90,
            "p95_ms": 95,
            "jitter_ms": 5,
            "request_failure_ratio": 0.0,
        }
        scored = quality_manager.score_candidate(delay, {"ok": True, "mbps": 50})
        self.assertTrue(scored["eligible"])
        self.assertLess(scored["score"], 120)

    def test_score_rejects_missing_or_failed_speed(self):
        delay = {
            "node": "untested",
            "ok": True,
            "median_ms": 80,
            "p95_ms": 90,
            "jitter_ms": 10,
            "request_failure_ratio": 0.0,
        }
        missing = quality_manager.score_candidate(delay, None)
        failed = quality_manager.score_candidate(delay, {"ok": False, "error": "chatgpt_trace_not_us"})
        self.assertFalse(missing["eligible"])
        self.assertEqual(missing["reason"], "speed_not_verified")
        self.assertFalse(failed["eligible"])
        self.assertEqual(failed["reason"], "speed_not_verified")

    def test_site_payload_validators_require_expected_json(self):
        hf = b'{"model_type":"gpt2"}'
        pypi = b'{"info":{"name":"six","version":"1.17.0"}}'
        self.assertEqual(quality_manager.site_payload_ok("hf_config", 200, hf), (True, None))
        self.assertEqual(quality_manager.site_payload_ok("pypi_six_json", 200, pypi), (True, None))
        self.assertFalse(quality_manager.site_payload_ok("pypi_six_json", 404, b'{"message":"Not Found"}')[0])
        self.assertFalse(quality_manager.site_payload_ok("pypi_six_json", 200, b'{"info":{"name":"six","version":"1.16.0"}}')[0])

    def test_speed_budget_is_rolling_thirty_minutes(self):
        state = {"speed_attempts": [1000, 1100, 1199, -1000]}
        remaining = quality_manager.speed_budget_remaining(
            state,
            1200,
            SimpleNamespace(speed_ttl_seconds=1800, max_speed_nodes_per_pool=3),
        )
        self.assertEqual(remaining, 0)
        self.assertEqual(state["speed_attempts"], [1000.0, 1100.0, 1199.0])

    def test_picks_best_from_native_fallback(self):
        ranked = sorted([metric("poor", 450, mbps=2), metric("good", 80, mbps=40)], key=lambda item: item["score"])
        state = {}
        decision = quality_manager.decide_selection(
            pool=self.pool,
            pool_state=state,
            current=self.pool.native_fallback,
            ranked=ranked,
            ts=1000,
            args=args(),
        )
        self.assertEqual(decision["target"], "good")
        self.assertEqual(decision["action"], "select_best_from_fallback")

    def test_hysteresis_requires_two_confirmed_improvements(self):
        current = metric("current", 300, mbps=5)
        challenger = metric("challenger", 80, mbps=50)
        ranked = sorted([current, challenger], key=lambda item: item["score"])
        state = {"last_switch_ts": 0}
        first = quality_manager.decide_selection(
            pool=self.pool,
            pool_state=state,
            current="current",
            ranked=ranked,
            ts=2000,
            args=args(),
        )
        second = quality_manager.decide_selection(
            pool=self.pool,
            pool_state=state,
            current="current",
            ranked=ranked,
            ts=2300,
            args=args(),
        )
        self.assertEqual(first["target"], "current")
        self.assertEqual(first["action"], "wait_challenger_confirmation")
        self.assertEqual(second["target"], "challenger")
        self.assertEqual(second["action"], "switch_challenger_better")

    def test_hold_timer_blocks_non_failed_challenger_switch(self):
        current = metric("current", 300, mbps=5)
        challenger = metric("challenger", 80, mbps=50)
        ranked = sorted([current, challenger], key=lambda item: item["score"])
        state = {"last_switch_ts": 1000}
        decision = quality_manager.decide_selection(
            pool=self.pool,
            pool_state=state,
            current="current",
            ranked=ranked,
            ts=1200,
            args=args(),
        )
        self.assertEqual(decision["target"], "current")
        self.assertEqual(decision["action"], "hold_current")

    def test_unhealthy_current_switches_immediately(self):
        ranked = [metric("replacement", 100, mbps=20)]
        state = {"last_switch_ts": 1200}
        decision = quality_manager.decide_selection(
            pool=self.pool,
            pool_state=state,
            current="dead-current",
            ranked=ranked,
            ts=1210,
            args=args(),
        )
        self.assertEqual(decision["target"], "replacement")
        self.assertEqual(decision["action"], "switch_current_unhealthy")

    def test_feitu_does_not_fallback_to_native_without_ranked_candidates(self):
        state = {}
        decision = quality_manager.decide_selection(
            pool=quality_manager.POOLS[1],
            pool_state=state,
            current="held-leaf",
            ranked=[],
            ts=1000,
            args=args(),
        )
        self.assertEqual(decision["target"], "held-leaf")
        self.assertEqual(decision["action"], "no_verified_alternative_hold_current")

    def test_quarantine_clears_speed_cache_and_blocks_candidate(self):
        pool_state = {
            "speed_cache": {
                "dead": {
                    "node": "dead",
                    "ok": True,
                    "status": 200,
                    "bytes": quality_manager.SPEED_BYTES,
                    "expected_bytes": quality_manager.SPEED_BYTES,
                    "measured_at_ts": 990,
                }
            }
        }
        entry = quality_manager.quarantine_node(pool_state, "dead", 1000, args(), "failed")
        self.assertEqual(entry["until_ts"], 1600)
        self.assertNotIn("dead", pool_state["speed_cache"])
        ranked = [metric("dead", 50, mbps=50), metric("alive", 90, mbps=20)]
        decision = quality_manager.decide_selection(
            pool=quality_manager.POOLS[1],
            pool_state=pool_state,
            current="current",
            ranked=ranked,
            ts=1001,
            args=args(),
        )
        self.assertEqual(decision["target"], "alive")
        self.assertEqual(decision["action"], "switch_current_unhealthy")

    def test_assessment_does_not_resurrect_cached_speed_outside_shortlist(self):
        pool = quality_manager.POOLS[1]
        state = {
            "pools": {
                pool.name: {
                    "speed_cache": {
                        "stale-fast": {
                            "node": "stale-fast",
                            "ok": True,
                            "status": 200,
                            "bytes": quality_manager.SPEED_BYTES,
                            "expected_bytes": quality_manager.SPEED_BYTES,
                            "mbps": 100,
                            "measured_at_ts": 1000,
                        }
                    },
                    "speed_attempts": [1000, 1001, 1002],
                }
            }
        }
        delays = [
            {"node": "short-a", "ok": True, "median_ms": 100, "p95_ms": 100, "jitter_ms": 0, "request_failure_ratio": 0.0},
            {"node": "short-b", "ok": True, "median_ms": 110, "p95_ms": 110, "jitter_ms": 0, "request_failure_ratio": 0.0},
            {"node": "short-c", "ok": True, "median_ms": 120, "p95_ms": 120, "jitter_ms": 0, "request_failure_ratio": 0.0},
            {"node": "stale-fast", "ok": True, "median_ms": 130, "p95_ms": 130, "jitter_ms": 0, "request_failure_ratio": 0.0},
        ]
        with (
            mock.patch.object(quality_manager, "now_ts", return_value=1200),
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(
                quality_manager,
                "discover_members",
                return_value=(
                    ["short-a", "short-b", "short-c", "stale-fast"],
                    None,
                    {"now": "held-leaf", "all": ["feitu-auto", "held-leaf", "short-a", "short-b", "short-c", "stale-fast"]},
                ),
            ),
            mock.patch.object(quality_manager, "measure_delays", return_value=delays),
            mock.patch.object(quality_manager, "site_payload_health", return_value={"ok": True, "request_failure_ratio": 0.0}),
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.assess_pool(pool, state, args(max_speed_nodes_per_pool=3), mock.Mock())
        self.assertEqual(event["action"], "no_verified_alternative_hold_current")
        self.assertEqual(event["selector_after"], "held-leaf")
        self.assertEqual(event["ranked"], [])
        self.assertFalse(any(call.args[1] == pool.managed_selector for call in put_selector.call_args_list))

    def test_assessment_holds_current_when_speed_budget_misses_recent_https_healthy_current(self):
        pool = quality_manager.POOLS[1]
        state = {
            "pools": {
                pool.name: {
                    "last_current_https": {"node": "current", "ok": True, "checked_at_ts": 1190},
                    "speed_cache": {
                        "challenger": {
                            "node": "challenger",
                            "ok": True,
                            "status": 200,
                            "bytes": quality_manager.SPEED_BYTES,
                            "expected_bytes": quality_manager.SPEED_BYTES,
                            "mbps": 100,
                            "measured_at_ts": 1190,
                        }
                    },
                    "speed_attempts": [1000, 1001, 1002],
                }
            }
        }
        delays = [
            {"node": "current", "ok": True, "median_ms": 80, "p95_ms": 80, "jitter_ms": 0, "request_failure_ratio": 0.0},
            {"node": "challenger", "ok": True, "median_ms": 90, "p95_ms": 90, "jitter_ms": 0, "request_failure_ratio": 0.0},
        ]
        with (
            mock.patch.object(quality_manager, "now_ts", return_value=1200),
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(
                quality_manager,
                "discover_members",
                return_value=(["current", "challenger"], None, {"now": "current", "all": ["feitu-auto", "current", "challenger"]}),
            ),
            mock.patch.object(quality_manager, "measure_delays", return_value=delays),
            mock.patch.object(quality_manager, "site_payload_health", return_value={"ok": True, "request_failure_ratio": 0.0}),
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.assess_pool(pool, state, args(max_speed_nodes_per_pool=3), mock.Mock())
        self.assertEqual(event["action"], "hold_current_recent_https_healthy_missing_speed")
        self.assertEqual(event["selector_after"], "current")
        self.assertFalse(any(call.args[1] == pool.managed_selector for call in put_selector.call_args_list))

    def test_assessment_does_not_resurrect_known_bad_cached_speed_without_fresh_site_success(self):
        pool = quality_manager.POOLS[1]
        state = {
            "pools": {
                pool.name: {
                    "last_failures": {"bad-fast": {"node": "bad-fast", "failed_at_ts": 1190, "reason": "current_check_failed"}},
                    "speed_cache": {
                        "bad-fast": {
                            "node": "bad-fast",
                            "ok": True,
                            "status": 200,
                            "bytes": quality_manager.SPEED_BYTES,
                            "expected_bytes": quality_manager.SPEED_BYTES,
                            "mbps": 500,
                            "measured_at_ts": 1190,
                        }
                    },
                }
            }
        }
        delays = [
            {"node": "bad-fast", "ok": True, "median_ms": 20, "p95_ms": 20, "jitter_ms": 0, "request_failure_ratio": 0.0},
        ]
        failed_site = {"ok": False, "request_failure_ratio": 1.0, "errors": ["hf_config:TimeoutError"]}
        with (
            mock.patch.object(quality_manager, "now_ts", return_value=1200),
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(
                quality_manager,
                "discover_members",
                return_value=(["current", "bad-fast"], None, {"now": "current", "all": ["feitu-auto", "current", "bad-fast"]}),
            ),
            mock.patch.object(quality_manager, "measure_delays", return_value=delays),
            mock.patch.object(quality_manager, "site_payload_health", return_value=failed_site),
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.assess_pool(pool, state, args(), mock.Mock())
        self.assertEqual(event["ranked"], [])
        self.assertEqual(event["action"], "no_verified_alternative_hold_current")
        self.assertIn("bad-fast", state["pools"][pool.name]["quarantine"])
        self.assertNotIn("bad-fast", state["pools"][pool.name]["speed_cache"])
        self.assertFalse(any(call.args[1] == pool.managed_selector for call in put_selector.call_args_list))

    def test_current_check_expands_native_fallback_and_uses_production_health(self):
        pool = quality_manager.POOLS[1]
        state = {"pools": {pool.name: {}}}
        get_selector_results = [
            {"now": "feitu-auto", "all": ["feitu-auto", "verified-alt"]},
            {"now": "feitu-quality", "all": ["feitu-quality", "manual-sg"]},
            {"now": "native-leaf", "all": ["native-leaf", "verified-alt"]},
        ]
        with (
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(quality_manager, "get_selector", side_effect=get_selector_results),
            mock.patch.object(quality_manager, "production_https_health", return_value={"ok": True}),
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.check_current_pool(pool, state, args(), mock.Mock())
        self.assertEqual(event["native_fallback_now"], "native-leaf")
        self.assertEqual(event["action"], "fallback_current_healthy")
        put_selector.assert_not_called()

    def test_current_check_uses_production_health_for_explicit_leaf(self):
        pool = quality_manager.POOLS[1]
        state = {"pools": {pool.name: {}}}
        with (
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(
                quality_manager,
                "get_selector",
                side_effect=[
                    {"now": "selected-leaf", "all": ["feitu-auto", "selected-leaf"]},
                    {"now": "feitu-quality", "all": ["feitu-quality", "manual-sg"]},
                ],
            ),
            mock.patch.object(quality_manager, "production_https_health", return_value={"ok": True}) as production_health,
            mock.patch.object(quality_manager, "probe_node_delay") as probe_delay,
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.check_current_pool(pool, state, args(), mock.Mock())
        self.assertEqual(event["action"], "current_production_healthy")
        production_health.assert_called_once()
        probe_delay.assert_not_called()
        put_selector.assert_not_called()

    def test_current_check_skips_when_outer_selector_is_manual(self):
        pool = quality_manager.POOLS[1]
        state = {"pools": {pool.name: {"current_failed_checks": 2}}}
        with (
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(
                quality_manager,
                "get_selector",
                side_effect=[
                    {"now": "selected-leaf", "all": ["feitu-auto", "selected-leaf"]},
                    {"now": "manual-sg", "all": ["feitu-quality", "manual-sg"]},
                ],
            ),
            mock.patch.object(quality_manager, "production_https_health") as production_health,
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.check_current_pool(pool, state, args(), mock.Mock())
        self.assertEqual(event["action"], "skip_manual_outer_selection")
        self.assertEqual(state["pools"][pool.name]["current_failed_checks"], 2)
        production_health.assert_not_called()
        put_selector.assert_not_called()

    def test_current_check_quarantines_failed_fallback_leaf_and_recovers_verified_alternative(self):
        pool = quality_manager.POOLS[1]
        state = {
            "pools": {
                pool.name: {
                    "current_failed_checks": 2,
                    "speed_cache": {
                        "native-leaf": {
                            "node": "native-leaf",
                            "ok": True,
                            "status": 200,
                            "bytes": quality_manager.SPEED_BYTES,
                            "expected_bytes": quality_manager.SPEED_BYTES,
                            "measured_at_ts": 1190,
                        },
                        "verified-alt": {
                            "node": "verified-alt",
                            "ok": True,
                            "status": 200,
                            "bytes": quality_manager.SPEED_BYTES,
                            "expected_bytes": quality_manager.SPEED_BYTES,
                            "mbps": 20,
                            "measured_at_ts": 1195,
                        },
                    },
                }
            }
        }
        get_selector_results = [
            {"now": "feitu-auto", "all": ["feitu-auto", "native-leaf", "verified-alt"]},
            {"now": "feitu-quality", "all": ["feitu-quality", "manual-sg"]},
            {"now": "native-leaf", "all": ["native-leaf", "verified-alt"]},
        ]
        with (
            mock.patch.object(quality_manager, "now_ts", return_value=1200),
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(quality_manager, "get_selector", side_effect=get_selector_results),
            mock.patch.object(
                quality_manager,
                "production_https_health",
                return_value={"ok": False, "request_failure_ratio": 1.0, "errors": ["TimeoutError"]},
            ),
            mock.patch.object(
                quality_manager,
                "verify_recovery_path",
                return_value={
                    "node": "verified-alt",
                    "ok": True,
                    "status": 200,
                    "bytes": quality_manager.SPEED_BYTES,
                    "expected_bytes": quality_manager.SPEED_BYTES,
                    "mbps": 30,
                    "measured_at_ts": 1200,
                },
            ) as verify_recovery_path,
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.check_current_pool(pool, state, args(), mock.Mock())
        self.assertEqual(event["action"], "switch_to_freshly_verified_after_current_failure")
        self.assertEqual(event["selector_after"], "verified-alt")
        self.assertIn("native-leaf", state["pools"][pool.name]["quarantine"])
        self.assertNotIn("native-leaf", state["pools"][pool.name]["speed_cache"])
        verify_recovery_path.assert_called_once_with("http://api", pool, "verified-alt", mock.ANY)
        put_selector.assert_called_once_with("http://api", "feitu-quality", "verified-alt", 1)

    def test_current_check_does_not_put_recovery_when_fresh_verification_fails(self):
        pool = quality_manager.POOLS[1]
        state = {
            "pools": {
                pool.name: {
                    "current_failed_checks": 2,
                    "speed_cache": {
                        "verified-alt": {
                            "node": "verified-alt",
                            "ok": True,
                            "status": 200,
                            "bytes": quality_manager.SPEED_BYTES,
                            "expected_bytes": quality_manager.SPEED_BYTES,
                            "mbps": 20,
                            "measured_at_ts": 1195,
                        },
                    },
                }
            }
        }
        get_selector_results = [
            {"now": "feitu-auto", "all": ["feitu-auto", "native-leaf", "verified-alt"]},
            {"now": "feitu-quality", "all": ["feitu-quality", "manual-sg"]},
            {"now": "native-leaf", "all": ["native-leaf", "verified-alt"]},
        ]
        with (
            mock.patch.object(quality_manager, "now_ts", return_value=1200),
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(quality_manager, "get_selector", side_effect=get_selector_results),
            mock.patch.object(
                quality_manager,
                "production_https_health",
                return_value={"ok": False, "request_failure_ratio": 1.0, "errors": ["TimeoutError"]},
            ),
            mock.patch.object(
                quality_manager,
                "verify_recovery_path",
                return_value={
                    "node": "verified-alt",
                    "ok": False,
                    "status": 0,
                    "error": "fresh_probe_failed",
                    "measured_at_ts": 1200,
                },
            ),
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.check_current_pool(pool, state, args(), mock.Mock())
        self.assertEqual(event["action"], "no_verified_alternative_hold_current")
        self.assertEqual(event["selector_after"], "feitu-auto")
        self.assertIn("native-leaf", state["pools"][pool.name]["quarantine"])
        self.assertIn("verified-alt", state["pools"][pool.name]["quarantine"])
        put_selector.assert_not_called()

    def test_emergency_recovery_does_not_require_bulk_speed_budget(self):
        state = {'last_assessment_ts': 1190, 'last_assessment': {'delay_metrics': [
            {'node': 'candidate', 'ok': True, 'request_failure_ratio': 0, 'median_ms': 120}]}}
        candidates = quality_manager.recovery_candidates_from_verified_cache(state, ['dead', 'candidate'], 'dead', 1200, args())
        self.assertEqual([x['node'] for x in candidates], ['candidate'])
        self.assertIsNone(candidates[0]['speed'])
        with mock.patch.object(quality_manager, 'verify_recovery_path', return_value={'ok': True}):
            selected = quality_manager.freshly_verify_recovery('http://api', quality_manager.POOLS[1], state, candidates, 1200, args())
        self.assertEqual(selected['node'], 'candidate')
        self.assertIsNone(selected['speed'])

    def test_feitu_recovery_candidates_keep_miaomiao_backup_inside_cap(self):
        pool = quality_manager.POOLS[1]
        state = {
            "speed_cache": {
                "feitu-a": {
                    "node": "feitu-a",
                    "ok": True,
                    "status": 200,
                    "bytes": quality_manager.SPEED_BYTES,
                    "expected_bytes": quality_manager.SPEED_BYTES,
                    "mbps": 50,
                    "measured_at_ts": 1200,
                },
                "feitu-b": {
                    "node": "feitu-b",
                    "ok": True,
                    "status": 200,
                    "bytes": quality_manager.SPEED_BYTES,
                    "expected_bytes": quality_manager.SPEED_BYTES,
                    "mbps": 40,
                    "measured_at_ts": 1199,
                },
                "feitu-c": {
                    "node": "feitu-c",
                    "ok": True,
                    "status": 200,
                    "bytes": quality_manager.SPEED_BYTES,
                    "expected_bytes": quality_manager.SPEED_BYTES,
                    "mbps": 30,
                    "measured_at_ts": 1198,
                },
                "miaomiao-ok": {
                    "node": "miaomiao-ok",
                    "ok": True,
                    "status": 200,
                    "bytes": quality_manager.SPEED_BYTES,
                    "expected_bytes": quality_manager.SPEED_BYTES,
                    "mbps": 100,
                    "measured_at_ts": 1197,
                },
            }
        }
        candidates = quality_manager.recovery_candidates_from_verified_cache(
            state,
            ["dead", "feitu-a", "feitu-b", "feitu-c", "miaomiao-ok"],
            "dead",
            1201,
            args(),
            pool=pool,
        )
        self.assertEqual(len(candidates), 3)
        self.assertIn("miaomiao-ok", [item["node"] for item in candidates])

    def test_feitu_speed_budget_not_spent_on_failed_site_candidate_before_backup(self):
        pool = quality_manager.POOLS[1]
        state = {"pools": {pool.name: {"speed_attempts": [1000, 1001]}}}
        delays = [
            {"node": "feitu-bad", "ok": True, "median_ms": 50, "p95_ms": 50, "jitter_ms": 0, "request_failure_ratio": 0.0},
            {"node": "miaomiao-good", "ok": True, "median_ms": 60, "p95_ms": 60, "jitter_ms": 0, "request_failure_ratio": 0.0},
            {"node": "feitu-other", "ok": True, "median_ms": 70, "p95_ms": 70, "jitter_ms": 0, "request_failure_ratio": 0.0},
        ]

        def fake_site_health(port, probes, timeout):
            node = fake_site_health.nodes.pop(0)
            if node == "feitu-bad":
                return {"ok": False, "request_failure_ratio": 1.0, "errors": ["hf_config:TimeoutError"]}
            return {"ok": True, "request_failure_ratio": 0.0, "errors": []}

        fake_site_health.nodes = ["feitu-bad", "miaomiao-good", "feitu-other"]

        def fake_speed(api_url, measured_pool, node, measured_args):
            return {
                "node": node,
                "ok": True,
                "status": 200,
                "bytes": quality_manager.SPEED_BYTES,
                "expected_bytes": quality_manager.SPEED_BYTES,
                "mbps": 100,
                "measured_at_ts": 1200,
            }

        with (
            mock.patch.object(quality_manager, "now_ts", return_value=1200),
            mock.patch.object(quality_manager, "choose_api", return_value=("http://api", None)),
            mock.patch.object(
                quality_manager,
                "discover_members",
                return_value=(
                    ["current", "feitu-bad", "miaomiao-good", "feitu-other"],
                    None,
                    {"now": "current", "all": ["feitu-auto", "current", "feitu-bad", "miaomiao-good", "feitu-other"]},
                ),
            ),
            mock.patch.object(quality_manager, "measure_delays", return_value=delays),
            mock.patch.object(quality_manager, "site_payload_health", side_effect=fake_site_health),
            mock.patch.object(quality_manager, "measure_speed", side_effect=fake_speed) as measure_speed,
            mock.patch.object(quality_manager, "verify_recovery_path", return_value={"ok": True}),
            mock.patch.object(quality_manager, "put_selector") as put_selector,
        ):
            event = quality_manager.assess_pool(pool, state, args(), mock.Mock())

        self.assertEqual(event["speed_metrics"]["feitu-bad"]["skipped"], "fresh_site_probe_failed")
        self.assertTrue(event["speed_metrics"]["miaomiao-good"]["ok"])
        self.assertEqual([call.args[2] for call in measure_speed.call_args_list], ["miaomiao-good"])
        self.assertEqual(event["decision"]["target"], "miaomiao-good")
        managed_writes = [call for call in put_selector.call_args_list if call.args[1] == "feitu-quality"]
        self.assertEqual(len(managed_writes), 1)
        self.assertEqual(managed_writes[0].args, ("http://api", "feitu-quality", "miaomiao-good", 1))

    def test_ai_native_fallback_without_production_port_uses_real_delay(self):
        pool = replace(quality_manager.POOLS[0], production_port=None)
        with (mock.patch.object(quality_manager, 'choose_api', return_value=('http://api', None)),
              mock.patch.object(quality_manager, 'get_selector', side_effect=[{'now': pool.native_fallback}, {'now': 'ai-leaf'}]),
              mock.patch.object(quality_manager, 'probe_node_delay', return_value={'ok': True}) as probe):
            result = quality_manager.check_current_pool(pool, {}, args(), mock.Mock())
        self.assertEqual(result['action'], 'current_healthy')
        probe.assert_called_once()

    def test_outer_selectors_are_not_managed_by_config(self):
        managed = {pool.managed_selector for pool in quality_manager.POOLS}
        measured = {pool.measure_selector for pool in quality_manager.POOLS}
        untouched = {"us-ai", "ai-auto-fallback", "server-feitu"}
        self.assertEqual(managed, {"ai-quality", "feitu-quality"})
        self.assertEqual(measured, {"ai-measure", "feitu-measure"})
        self.assertTrue(untouched.isdisjoint(managed | measured))

    def test_settings_ports_build_portable_pools(self):
        settings = quality_manager.DEFAULT_SETTINGS | {
            "main_controller_ports": [18001, 18002],
            "controller_port": 18003,
            "local_proxy_port": 18097,
            "ai_primary_port": 18011,
            "ai_measure_port": 18013,
            "feitu_measure_port": 18014,
        }
        pools = quality_manager.build_pools(settings)
        self.assertEqual(pools[0].api_candidates, ("http://127.0.0.1:18001", "http://127.0.0.1:18002"))
        self.assertEqual(pools[0].production_port, 18011)
        self.assertEqual(pools[0].measurement_port, 18013)
        self.assertEqual(pools[1].api_candidates, ("http://127.0.0.1:18003",))
        self.assertEqual(pools[1].production_port, 18097)
        self.assertEqual(pools[1].measurement_port, 18014)



class SubscriptionFallbackTests(unittest.TestCase):
    def test_miaomiao_reserved_when_feitu_fills_latency_shortlist(self):
        items = [{"node": "feitu-" + str(i)} for i in range(8)] + [{"node": "miaomiao-1"}]
        chosen = quality_manager.subscription_shortlist(quality_manager.POOLS[1], items, 3)
        self.assertEqual([x["node"] for x in chosen], ["feitu-0", "miaomiao-1", "feitu-1"])

    def test_failed_feitu_uses_verified_miaomiao(self):
        result = quality_manager.decide_selection(pool=quality_manager.POOLS[1], pool_state={}, current="feitu-bad", ranked=[{"node":"miaomiao-good", "score":100}], ts=1000, args=args())
        self.assertEqual(result["target"], "miaomiao-good")

    def test_healthy_feitu_preferred_over_faster_backup(self):
        result = quality_manager.decide_selection(pool=quality_manager.POOLS[1], pool_state={}, current=None, ranked=[{"node":"miaomiao-good", "score":10},{"node":"feitu-good", "score":100}], ts=1000, args=args())
        self.assertEqual(result["target"], "feitu-good")

    def test_quarantined_primary_does_not_block_backup(self):
        state={"quarantine":{"feitu-bad":{"until_ts":2000}}}
        result=quality_manager.decide_selection(pool=quality_manager.POOLS[1],pool_state=state,current=None,ranked=[{"node":"feitu-bad","score":10},{"node":"miaomiao-good","score":100}],ts=1000,args=args())
        self.assertEqual(result["target"],"miaomiao-good")


class BenchmarkFallbackTests(unittest.TestCase):
    def test_server_benchmark_403_uses_valid_hf_payload(self):
        import json
        vocab = {str(i): i for i in range(50256)}
        vocab["<|endoftext|>"] = 50256
        body = json.dumps({"model": {"vocab": vocab, "merges": ["a b"] * 50000}}, separators=(',', ':')).encode().ljust(1355256, b' ')
        denied = quality_manager.error.HTTPError('https://speed.cloudflare.com', 403, 'Forbidden', {}, None)
        with mock.patch.object(quality_manager, 'put_selector'), mock.patch.object(quality_manager, 'proxy_fetch', side_effect=[denied, (200, body, 2.0)]):
            result = quality_manager.measure_speed('http://api', quality_manager.POOLS[1], 'miaomiao-good', args())
        self.assertTrue(result['ok'])
        self.assertTrue(result['benchmark_fallback'])
        self.assertEqual(result['expected_bytes'], 1355256)

    def test_benchmark_fallback_rejects_wrong_payload(self):
        denied = quality_manager.error.HTTPError('https://speed.cloudflare.com', 403, 'Forbidden', {}, None)
        with mock.patch.object(quality_manager, 'put_selector'), mock.patch.object(quality_manager, 'proxy_fetch', side_effect=[denied, (200, b'{}'.ljust(1355256, b' '), 2.0)]):
            result = quality_manager.measure_speed('http://api', quality_manager.POOLS[1], 'miaomiao-good', args())
        self.assertFalse(result['ok'])

if __name__ == "__main__":
    unittest.main()
