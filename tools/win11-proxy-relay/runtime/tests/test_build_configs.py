import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unittest


RUNTIME_DIR = Path(__file__).resolve().parents[1]
if str(RUNTIME_DIR) not in sys.path:
    sys.path.insert(0, str(RUNTIME_DIR))
SPEC = importlib.util.spec_from_file_location("build_configs", RUNTIME_DIR / "build-configs.py")
build_configs = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(build_configs)


def row(**overrides):
    base = {
        "IndexId": "1",
        "Remarks": "miaomiao-us",
        "Address": "example.invalid",
        "Port": 443,
        "ConfigType": 5,
        "Password": "00000000-0000-4000-8000-000000000000",
        "Username": "",
        "Id": "",
        "Network": "tcp",
        "StreamSecurity": "reality",
        "AllowInsecure": "false",
        "Sni": "www.example.com",
        "Alpn": "",
        "Fingerprint": "chrome",
        "PublicKey": "public-key",
        "ShortId": "abcd",
        "SpiderX": "/",
        "Flow": "",
        "Security": "",
        "ProtoExtra": '{"Flow":"xtls-rprx-vision","VlessEncryption":"none"}',
    }
    base.update(overrides)
    return base


class BuildConfigsTests(unittest.TestCase):
    def make_profile_db(self, path):
        con = sqlite3.connect(path)
        con.executescript(
            """
            CREATE TABLE SubItem (Id TEXT, Remarks TEXT, Enabled INTEGER);
            CREATE TABLE ProfileItem (
              IndexId TEXT, ConfigType INTEGER, Subid TEXT, Remarks TEXT, Address TEXT,
              Port INTEGER, Password TEXT, Username TEXT, Network TEXT, HeaderType TEXT,
              RequestHost TEXT, Path TEXT, StreamSecurity TEXT, AllowInsecure TEXT,
              Sni TEXT, Alpn TEXT, Fingerprint TEXT, PublicKey TEXT, ShortId TEXT,
              SpiderX TEXT, ProtoExtra TEXT, Flow TEXT, Id TEXT, Security TEXT
            );
            """
        )
        con.row_factory = sqlite3.Row
        return con

    def insert_profile(self, con, item):
        columns = list(item)
        con.execute(
            f"INSERT INTO ProfileItem ({','.join(columns)}) VALUES ({','.join('?' for _ in columns)})",
            tuple(item[column] for column in columns),
        )

    def test_vless_reality_conversion_uses_v2rayn_fields(self):
        node, info = build_configs.convert_profile_row(row(), "miaomiao", re.compile("台湾"))
        self.assertEqual(info["reason"], "included")
        self.assertEqual(node["tag"], "miaomiao-1")
        self.assertEqual(node["type"], "vless")
        self.assertEqual(node["uuid"], "00000000-0000-4000-8000-000000000000")
        self.assertEqual(node["flow"], "xtls-rprx-vision")
        self.assertEqual(node["packet_encoding"], "xudp")
        self.assertEqual(node["tls"]["server_name"], "www.example.com")
        self.assertEqual(node["tls"]["utls"]["fingerprint"], "chrome")
        self.assertEqual(node["tls"]["reality"]["public_key"], "public-key")
        self.assertEqual(node["tls"]["reality"]["short_id"], "abcd")
        self.assertNotIn("spider_x", node["tls"]["reality"])

    def test_filters_taiwan_and_metadata_error_rows(self):
        pattern = re.compile("台湾|台灣", re.IGNORECASE)
        for remarks, reason in [
            ("台湾 01", "blocked_by_policy"),
            ("当出现较长时间error时请更新订阅", "metadata_row"),
            ("剩余" + "流量 100GB", "metadata_row"),
        ]:
            node, info = build_configs.convert_profile_row(row(Remarks=remarks), "miaomiao", pattern)
            self.assertIsNone(node)
            self.assertEqual(info["reason"], reason)

    def test_qq_fingerprint_matches_v2rayn_sing_box_output(self):
        node, _ = build_configs.convert_profile_row(row(Fingerprint="qq"), "miaomiao", re.compile("台湾"))
        self.assertEqual(node["tls"]["utls"]["fingerprint"], "chrome")

    def test_server_only_build_does_not_require_main_template(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            v2 = root / "v2rayN"
            state = root / "state"
            (v2 / "guiConfigs").mkdir(parents=True)
            state.mkdir()
            db = v2 / "guiConfigs" / "guiNDB.db"
            con = sqlite3.connect(db)
            con.executescript(
                """
                CREATE TABLE SubItem (Id TEXT, Remarks TEXT, Enabled INTEGER);
                CREATE TABLE ProfileItem (
                  IndexId TEXT, ConfigType INTEGER, Subid TEXT, Remarks TEXT, Address TEXT,
                  Port INTEGER, Password TEXT, Username TEXT, Network TEXT, HeaderType TEXT,
                  RequestHost TEXT, Path TEXT, StreamSecurity TEXT, AllowInsecure TEXT,
                  Sni TEXT, Alpn TEXT, Fingerprint TEXT, PublicKey TEXT, ShortId TEXT,
                  SpiderX TEXT, ProtoExtra TEXT, Flow TEXT, Id TEXT, Security TEXT
                );
                """
            )
            con.execute("INSERT INTO SubItem VALUES (?,?,?)", ("feitu-sub", "feitu", 1))
            con.execute("INSERT INTO SubItem VALUES (?,?,?)", ("miao-sub", "miaomiao", 1))
            con.execute(
                "INSERT INTO ProfileItem VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "1", 3, "feitu-sub", "hk", "example.invalid", 443, "ss-pass", "", "",
                    "", "", "", "", "false", "", "", "", "", "", "", '{"SsMethod":"aes-128-gcm"}', "", "", "",
                ),
            )
            con.execute(
                "INSERT INTO ProfileItem VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    "2", 5, "miao-sub", "us", "example.invalid", 443,
                    "00000000-0000-4000-8000-000000000000", "", "tcp", "none", "", "",
                    "reality", "false", "www.example.com", "", "chrome", "public-key",
                    "abcd", "/", "{}", "", "", "",
                ),
            )
            con.commit()
            con.close()

            settings = {
                "v2rayn_dir": str(v2),
                "state_dir": str(state),
                "local_proxy_port": 19097,
                "controller_port": 19003,
                "feitu_measure_port": 19014,
            }
            build_configs.build(settings)
            config = json.loads((state / "server-config.json").read_text(encoding="utf-8"))
            labels = json.loads((state / "node-labels.json").read_text(encoding="utf-8"))
            sources = json.loads((state / "node-sources.json").read_text(encoding="utf-8"))

        outbounds = {item["tag"]: item for item in config["outbounds"]}
        self.assertIn("feitu-1", outbounds["feitu-auto"]["outbounds"])
        self.assertIn("miaomiao-2", outbounds["feitu-auto"]["outbounds"])
        self.assertEqual(labels["miaomiao-2"], "us")
        self.assertEqual(sources["miaomiao-2"]["source"], "miaomiao")

    def test_rebuild_main_ai_pool_replaces_old_leaf_nodes(self):
        tun = {
            "outbounds": [
                {"type": "direct", "tag": "direct"},
                {"type": "vless", "tag": "us-home-1", "server": "old.invalid"},
                {"type": "vless", "tag": "lgx-marz-vless", "server": "old.invalid"},
                {"type": "urltest", "tag": "us-ai-auto-READONLY",
                 "outbounds": ["us-home-1", "lgx-marz-vless"]},
                {"type": "selector", "tag": "us-ai",
                 "outbounds": ["us-ai-auto-READONLY", "us-home-1", "lgx-marz-vless"]},
                {"type": "selector", "tag": "ai-quality", "outbounds": ["us-home-1"]},
                {"type": "selector", "tag": "ai-measure", "outbounds": ["us-home-1"]},
                {"type": "selector", "tag": "ai-auto-fallback", "outbounds": ["ai-quality", "proxy"]},
            ]
        }
        nodes = [
            {"type": "shadowsocks", "tag": "ai-node-1", "server": "bwg.invalid",
             "server_port": 44301, "method": "aes-128-gcm", "password": "secret"},
            {"type": "shadowsocks", "tag": "ai-node-2", "server": "bwg.invalid",
             "server_port": 44401, "method": "aes-128-gcm", "password": "secret"},
        ]

        rebuilt = build_configs.rebuild_main_ai_pool(tun, nodes)
        outbounds = {item["tag"]: item for item in rebuilt["outbounds"]}

        self.assertNotIn("us-home-1", outbounds)
        self.assertNotIn("lgx-marz-vless", outbounds)
        self.assertEqual(outbounds["us-ai-auto-READONLY"]["outbounds"], ["ai-node-1", "ai-node-2"])
        self.assertEqual(
            outbounds["us-ai"]["outbounds"],
            ["ai-auto-fallback", "proxy"],
        )
        self.assertEqual(outbounds["ai-measure"]["outbounds"], ["ai-node-1", "ai-node-2"])
        self.assertEqual(
            build_configs.rebuild_main_ai_pool(rebuilt, nodes),
            rebuilt,
        )

    def test_stable_ai_tag_ignores_v2rayn_index_and_credential_rotation(self):
        first = row(
            IndexId="volatile-1", Subid="subscription-1", Remarks="BWG to OVH",
            Address="bwg.invalid", Port=44301, Password="old-secret",
            ConfigType=3, Security="aes-128-gcm",
        )
        refreshed = row(
            IndexId="volatile-2", Subid="subscription-2", Remarks="BWG to OVH",
            Address="bwg.invalid", Port=44301, Password="new-secret",
            Username="new-username", Id="new-uuid",
            ConfigType=3, Security="aes-128-gcm",
        )

        self.assertEqual(
            build_configs.stable_ai_tag(first, "搬瓦工"),
            build_configs.stable_ai_tag(refreshed, "搬瓦工"),
        )
        self.assertRegex(
            build_configs.stable_ai_tag(first, "搬瓦工"),
            r"^ai-node-[0-9a-f]{16}$",
        )

    def test_stable_ai_tag_ignores_display_remark_changes(self):
        first = row(
            Remarks="BWG to OVH old label", Address="bwg.invalid", Port=44301,
            ConfigType=3, Security="aes-128-gcm",
        )
        renamed = dict(first)
        renamed.update(IndexId="new-index", Remarks="BWG to OVH new label")

        self.assertEqual(
            build_configs.stable_ai_tag(first, "搬瓦工"),
            build_configs.stable_ai_tag(renamed, "搬瓦工"),
        )

    def test_stable_ai_tag_changes_with_network_identity(self):
        first = row(Remarks="BWG to OVH", Address="bwg.invalid", Port=44301)
        moved = row(Remarks="BWG to OVH", Address="bwg.invalid", Port=44401)

        self.assertNotEqual(
            build_configs.stable_ai_tag(first, "搬瓦工"),
            build_configs.stable_ai_tag(moved, "搬瓦工"),
        )

    def test_stable_ai_tag_covers_effective_non_secret_protocol_identity(self):
        cases = [
            (
                row(ConfigType=3, Security="aes-128-gcm", ProtoExtra="{}"),
                {"Security": "chacha20-ietf-poly1305"},
            ),
            (
                row(ConfigType=11, Sni="a.example", Alpn="h2", AllowInsecure="false"),
                {"Alpn": "http/1.1"},
            ),
            (
                row(ConfigType=5, PublicKey="public-a", ShortId="aaaa", Fingerprint="qq"),
                {"PublicKey": "public-b"},
            ),
            (
                row(ConfigType=5, PublicKey="public-a", ShortId="aaaa", Fingerprint="qq"),
                {"ShortId": "bbbb"},
            ),
            (
                row(ConfigType=5, PublicKey="public-a", ShortId="aaaa", Fingerprint="qq"),
                {"Fingerprint": "firefox"},
            ),
            (
                row(ConfigType=5, Flow="", ProtoExtra='{"Flow":"xtls-rprx-vision"}'),
                {"ProtoExtra": "{}"},
            ),
        ]
        for original, changes in cases:
            with self.subTest(changes=changes):
                changed = dict(original)
                changed.update(changes)
                self.assertNotEqual(
                    build_configs.stable_ai_tag(original, "搬瓦工"),
                    build_configs.stable_ai_tag(changed, "搬瓦工"),
                )

    def test_stable_ai_tag_normalizes_equivalent_vless_identity(self):
        first = row(
            ConfigType=5, Flow="", ProtoExtra='{"Flow":"xtls-rprx-vision"}',
            Fingerprint="qq", Network="TCP", StreamSecurity="REALITY",
        )
        equivalent = dict(first)
        equivalent.update(
            IndexId="new-index", Flow="xtls-rprx-vision", ProtoExtra="{}",
            Fingerprint="chrome", Network="tcp", StreamSecurity="reality",
        )
        self.assertEqual(
            build_configs.stable_ai_tag(first, "搬瓦工"),
            build_configs.stable_ai_tag(equivalent, "搬瓦工"),
        )

    def test_subscription_nodes_are_ordered_by_stable_tag(self):
        con = self.make_profile_db(":memory:")
        con.execute("INSERT INTO SubItem VALUES (?,?,?)", ("bwg-sub", "搬瓦工", 1))
        candidates = [
            row(Remarks="BWG A", Address="bwg.invalid", Port=44301),
            row(Remarks="BWG B", Address="bwg.invalid", Port=44401),
        ]
        ordered = sorted(
            candidates,
            key=lambda item: build_configs.stable_ai_tag(item, "搬瓦工"),
            reverse=True,
        )
        for ordinal, item in enumerate(ordered):
            item.update(IndexId=str(ordinal), Subid="bwg-sub")
            self.insert_profile(con, item)

        nodes, _, _ = build_configs.collect_subscription_nodes(
            con, ["搬瓦工"], re.compile("台湾")
        )

        tags = [node["tag"] for node in nodes]
        self.assertEqual(tags, sorted(tags))

    def test_filtered_subscription_row_does_not_parse_malformed_proto_extra(self):
        con = self.make_profile_db(":memory:")
        con.execute("INSERT INTO SubItem VALUES (?,?,?)", ("bwg-sub", "搬瓦工", 1))
        self.insert_profile(
            con,
            row(
                IndexId="blocked", Subid="bwg-sub", Remarks="台湾 blocked",
                ProtoExtra="{not-json",
            ),
        )
        self.insert_profile(
            con,
            row(
                IndexId="included", Subid="bwg-sub", Remarks="BWG included",
                ConfigType=3, ProtoExtra='{"SsMethod":"aes-128-gcm"}',
                Security="aes-128-gcm",
            ),
        )

        nodes, _, blocked = build_configs.collect_subscription_nodes(
            con, ["搬瓦工"], re.compile("台湾")
        )

        self.assertEqual(len(nodes), 1)
        self.assertEqual(blocked[0]["reason"], "blocked_by_policy")

    def test_selected_proxy_uses_durable_gui_config_without_generated_config(self):
        with tempfile.TemporaryDirectory() as temp:
            v2 = Path(temp) / "v2rayN"
            (v2 / "guiConfigs").mkdir(parents=True)
            (v2 / "guiConfigs" / "guiNConfig.json").write_text(
                json.dumps({"IndexId": "selected-1", "SubIndexId": "sub-1"}),
                encoding="utf-8",
            )
            con = self.make_profile_db(":memory:")
            self.insert_profile(
                con,
                row(
                    IndexId="selected-1", ConfigType=3, Subid="sub-1", Remarks="fallback",
                    Address="fallback.invalid", Port=1443, Password="ss-pass", Security="aes-128-gcm",
                    ProtoExtra='{"SsMethod":"aes-128-gcm"}',
                ),
            )
            proxy = build_configs.selected_proxy_outbound(con, v2, re.compile("台湾"))

        self.assertEqual(proxy["tag"], "proxy")
        self.assertEqual(proxy["type"], "shadowsocks")
        self.assertEqual(proxy["server"], "fallback.invalid")
        self.assertFalse((v2 / "binConfigs" / "config.json").exists())

    def test_selected_proxy_requires_one_matching_profile(self):
        for count in (0, 2):
            with self.subTest(count=count), tempfile.TemporaryDirectory() as temp:
                v2 = Path(temp) / "v2rayN"
                (v2 / "guiConfigs").mkdir(parents=True)
                (v2 / "guiConfigs" / "guiNConfig.json").write_text(
                    json.dumps({"IndexId": "duplicate"}), encoding="utf-8"
                )
                con = self.make_profile_db(":memory:")
                for ordinal in range(count):
                    self.insert_profile(
                        con,
                        row(IndexId="duplicate", Remarks=f"node-{ordinal}"),
                    )
                with self.assertRaisesRegex(RuntimeError, f"found {count}"):
                    build_configs.selected_proxy_outbound(con, v2, re.compile("台湾"))

    def test_main_only_stages_runtime_without_rewriting_relay_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            v2 = root / "v2rayN"
            state = root / "state"
            (v2 / "guiConfigs").mkdir(parents=True)
            state.mkdir()
            (v2 / "guiConfigs" / "guiNConfig.json").write_text(
                json.dumps({"IndexId": "fallback-1"}), encoding="utf-8"
            )
            relay_marker = '{"preserve":"dedicated-relay"}\n'
            (state / "server-config.json").write_text(relay_marker, encoding="utf-8")
            con = self.make_profile_db(v2 / "guiConfigs" / "guiNDB.db")
            con.execute(
                "CREATE TABLE FullConfigTemplateItem "
                "(Enabled INTEGER, Remarks TEXT, AddProxyOnly INTEGER, Config TEXT, TunConfig TEXT)"
            )
            con.execute("INSERT INTO SubItem VALUES (?,?,?)", ("bwg-sub", "搬瓦工", 1))
            self.insert_profile(
                con,
                row(
                    IndexId="ai-1", ConfigType=3, Subid="bwg-sub", Remarks="BWG to OVH",
                    Address="bwg.invalid", Port=44301, Password="ai-pass", Security="aes-128-gcm",
                    ProtoExtra='{"SsMethod":"aes-128-gcm"}',
                ),
            )
            self.insert_profile(
                con,
                row(
                    IndexId="fallback-1", ConfigType=3, Subid="other-sub", Remarks="fallback",
                    Address="fallback.invalid", Port=443, Password="fallback-pass", Security="aes-128-gcm",
                    ProtoExtra='{"SsMethod":"aes-128-gcm"}',
                ),
            )
            tun = {
                "inbounds": [{"type": "tun", "tag": "tun-in"}],
                "outbounds": [
                    {"type": "direct", "tag": "direct"},
                    {"type": "selector", "tag": "proxy", "outbounds": ["direct"]},
                    {"type": "urltest", "tag": "us-ai-auto-READONLY", "outbounds": ["old-node"]},
                    {"type": "selector", "tag": "us-ai", "outbounds": ["old-node"]},
                    {"type": "shadowsocks", "tag": "old-node", "server": "old.invalid"},
                ],
                "route": {"rules": []},
                "experimental": {
                    "clash_api": {"external_controller": "127.0.0.1:7903"},
                    "cache_file": {"enabled": True, "store_fakeip": True},
                },
            }
            con.execute(
                "INSERT INTO FullConfigTemplateItem VALUES (?,?,?,?,?)",
                (1, "sing-box", 1, json.dumps(tun), json.dumps(tun)),
            )
            con.commit()
            con.close()
            settings = {
                "v2rayn_dir": str(v2), "state_dir": str(state),
                "main_ai_subscriptions": ["搬瓦工"], "main_controller_ports": [7903, 7902],
                "ai_primary_port": 17911, "ai_fallback_port": 17912, "ai_measure_port": 17913,
            }

            build_configs.build(settings, with_main_templates=True, main_only=True)

            self.assertEqual((state / "server-config.json").read_text(encoding="utf-8"), relay_marker)
            runtime = json.loads((state / "tun-runtime.json").read_text(encoding="utf-8"))
            runtime_outbounds = {item["tag"]: item for item in runtime["outbounds"]}
            self.assertEqual(runtime_outbounds["proxy"]["server"], "fallback.invalid")
            expected_tag = build_configs.stable_ai_tag(
                row(
                    IndexId="another-volatile-id", ConfigType=3,
                    Subid="another-subscription-id", Remarks="BWG to OVH",
                    Address="bwg.invalid", Port=44301, Password="rotated-ai-pass",
                    Security="aes-128-gcm", ProtoExtra='{"SsMethod":"aes-128-gcm"}',
                ),
                "搬瓦工",
            )
            self.assertIn(expected_tag, runtime_outbounds)


if __name__ == "__main__":
    unittest.main()
