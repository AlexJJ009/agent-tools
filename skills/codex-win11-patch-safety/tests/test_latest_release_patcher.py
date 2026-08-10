import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parents[1]
PATCHER = ROOT / "releases" / "26.721.4979.0" / "patch-codex-webview.mjs"
UI_SOURCE = "function bYr(e){let t=(0,xYr.c)(6),n=Y(BD),r=e?.hostId??n,i=kM(r),a=i?.authMethod===`chatgpt`,o=i?.authMethod??null,s;t[0]!==r||t[1]!==o?(s={authMethod:o,hostId:r},t[0]=r,t[1]=o,t[2]=s):s=t[2];let{data:c,isPending:l}=Bo(QE,s),u=!!i?.isLoading||a&&l,d=a&&!u&&c!=null&&c?.requirements?.featureRequirements?.fast_mode!==!1,f;return t[3]!==u||t[4]!==d?(f={isServiceTierAllowed:d,isLoading:u},t[3]=u,t[4]=d,t[5]=f):f=t[5],f}"
REQUEST_SOURCE = "async function FWi(e,t){let n=await MWi(e,t);if(n!==`chatgpt`)return!1;let r=await Y8n(t,{priority:`critical`});return e.query.setData(QE,{authMethod:n,hostId:t},r),r.requirements?.featureRequirements?.fast_mode!==!1}"
TIER_SOURCE = "function Qer(e,t,n=!0){if(!n)return null;if(t==null){let t=e?.defaultServiceTier??null;return t==null?null:Zer(e,t)}return t===itr?null:t}"


class LatestReleasePatcherTests(unittest.TestCase):
    def make_fixture(self, root: Path) -> Path:
        assets = root / "webview" / "assets"
        assets.mkdir(parents=True)
        markers = (
            "function n3r(e){return e==null?`service_tier`:`profiles.${e}.service_tier`}"
            "function Ger(e,t){return t==null?null:t===`fast`?Jer(e):e?.serviceTiers?.find(e=>e.id===t)??null}"
            "gpt-5.6-sol gpt-5.6-terra gpt-5.6-luna "
            "function j6r(e){return e!==`chatgpt`&&e!==`apikey`&&e!==`amazonBedrock`}"
        )
        (assets / "app-initial-fixture.js").write_text(
            UI_SOURCE + REQUEST_SOURCE + TIER_SOURCE + markers,
            encoding="utf-8",
        )
        return root

    def run_patcher(self, fixture: Path):
        return subprocess.run(
            ["node", str(PATCHER), str(fixture)],
            text=True,
            capture_output=True,
            check=False,
        )

    def test_patcher_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory))
            first = self.run_patcher(fixture)
            self.assertEqual(first.returncode, 0, first.stderr)
            second = self.run_patcher(fixture)
            self.assertEqual(second.returncode, 0, second.stderr)
            report = json.loads(second.stdout)
            self.assertEqual(len(report["skipped"]), 3)

    def test_unsupported_configured_tier_is_suppressed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory))
            result = self.run_patcher(fixture)
            self.assertEqual(result.returncode, 0, result.stderr)
            asset = next((fixture / "webview" / "assets").glob("*.js"))
            text = asset.read_text(encoding="utf-8")
            start = text.index("function Qer(")
            end = text.index("}gpt-5.6-sol", start) + 1
            function = text[start:end]
            probe = subprocess.run(
                [
                    "node",
                    "-e",
                    "const itr='default';"
                    "const Zer=(m,t)=>m?.serviceTiers?.some(x=>x.id===t)?t:null;"
                    + function
                    + ";if(Qer({serviceTiers:[{id:'priority'}]},'priority')!=='priority')process.exit(1);"
                    + "if(Qer({serviceTiers:[]},'priority')!==null)process.exit(2);",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(probe.returncode, 0, probe.stderr)

    def test_missing_signature_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            fixture = self.make_fixture(Path(directory))
            asset = next((fixture / "webview" / "assets").glob("*.js"))
            asset.write_text(asset.read_text(encoding="utf-8").replace("function Qer", "function missingQer"), encoding="utf-8")
            result = self.run_patcher(fixture)
            self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
