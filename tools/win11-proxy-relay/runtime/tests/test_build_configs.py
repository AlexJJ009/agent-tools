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


if __name__ == "__main__":
    unittest.main()
