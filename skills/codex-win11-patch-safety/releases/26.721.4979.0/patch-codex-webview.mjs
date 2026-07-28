// Feature-signature patcher for OpenAI.Codex 26.721.4979.0.
// This candidate only forces Fast availability for ChatGPT/API-key auth.
import fs from "node:fs";
import path from "node:path";

const root = process.argv[2];
if (!root) throw new Error("Usage: node patch-codex-webview.mjs <unpacked-app-dir>");

const assets = path.join(root, "webview", "assets");
const report = {
  patched: [],
  skipped: [],
  official: [],
  files: {},
};

function read(file) {
  return fs.readFileSync(file, "utf8");
}

function write(file, text) {
  fs.writeFileSync(file, text);
  const relative = path.relative(root, file).replaceAll("\\", "/");
  if (!report.patched.includes(relative)) report.patched.push(relative);
}

function findAssetWithAll(label, signatures) {
  const matches = fs.readdirSync(assets)
    .filter((name) => name.endsWith(".js"))
    .map((name) => path.join(assets, name))
    .filter((file) => {
      const text = read(file);
      return signatures.every((signature) => text.includes(signature));
    });
  if (matches.length !== 1) {
    throw new Error(`${label}: expected one matching asset, found ${matches.length}`);
  }
  return matches[0];
}

function replaceExact(file, label, source, target) {
  let text = read(file);
  if (text.includes(target)) {
    report.skipped.push(`${label}: already patched`);
    return;
  }
  const count = text.split(source).length - 1;
  if (count !== 1) throw new Error(`${label}: expected one source signature, found ${count}`);
  text = text.replace(source, target);
  write(file, text);
}

const appInitial = findAssetWithAll("Fast service-tier implementation", [
  "function bYr(e)",
  "async function FWi(e,t)",
  "function n3r(e){return e==null?`service_tier`:`profiles.${e}.service_tier`}",
  "function Qer(e,t,n=!0)",
]);
report.files.appInitial = path.basename(appInitial);

replaceExact(
  appInitial,
  "force Fast UI for ChatGPT and API-key auth",
  "function bYr(e){let t=(0,xYr.c)(6),n=Y(BD),r=e?.hostId??n,i=kM(r),a=i?.authMethod===`chatgpt`,o=i?.authMethod??null,s;t[0]!==r||t[1]!==o?(s={authMethod:o,hostId:r},t[0]=r,t[1]=o,t[2]=s):s=t[2];let{data:c,isPending:l}=Bo(QE,s),u=!!i?.isLoading||a&&l,d=a&&!u&&c!=null&&c?.requirements?.featureRequirements?.fast_mode!==!1,f;return t[3]!==u||t[4]!==d?(f={isServiceTierAllowed:d,isLoading:u},t[3]=u,t[4]=d,t[5]=f):f=t[5],f}",
  "function bYr(e){let t=(0,xYr.c)(6),n=Y(BD),r=e?.hostId??n,i=kM(r),a=i?.authMethod===`chatgpt`||i?.authMethod===`apikey`,o=i?.authMethod??null,s;t[0]!==r||t[1]!==o?(s={authMethod:o,hostId:r},t[0]=r,t[1]=o,t[2]=s):s=t[2];let{data:c,isPending:l}=Bo(QE,s),u=!!i?.isLoading,d=a&&!u,f;return t[3]!==u||t[4]!==d?(f={isServiceTierAllowed:d,isLoading:u},t[3]=u,t[4]=d,t[5]=f):f=t[5],f}",
);

replaceExact(
  appInitial,
  "force request-time service tier for ChatGPT and API-key auth",
  "async function FWi(e,t){let n=await MWi(e,t);if(n!==`chatgpt`)return!1;let r=await Y8n(t,{priority:`critical`});return e.query.setData(QE,{authMethod:n,hostId:t},r),r.requirements?.featureRequirements?.fast_mode!==!1}",
  "async function FWi(e,t){let n=await MWi(e,t);return n===`chatgpt`||n===`apikey`}",
);

replaceExact(
  appInitial,
  "suppress unsupported configured service tiers",
  "function Qer(e,t,n=!0){if(!n)return null;if(t==null){let t=e?.defaultServiceTier??null;return t==null?null:Zer(e,t)}return t===itr?null:t}",
  "function Qer(e,t,n=!0){if(!n)return null;if(t==null){let t=e?.defaultServiceTier??null;return t==null?null:Zer(e,t)}return t===itr?null:Zer(e,t)}",
);

const finalText = read(appInitial);
for (const [label, marker] of [
  ["profile-aware service tier config", "function n3r(e){return e==null?`service_tier`:`profiles.${e}.service_tier`}"],
  ["model service-tier capability resolver", "function Ger(e,t){return t==null?null:t===`fast`?Jer(e):e?.serviceTiers?.find(e=>e.id===t)??null}"],
  ["official GPT-5.6 Sol", "gpt-5.6-sol"],
  ["official GPT-5.6 Terra", "gpt-5.6-terra"],
  ["official GPT-5.6 Luna", "gpt-5.6-luna"],
  ["official API-key plugin support", "function j6r(e){return e!==`chatgpt`&&e!==`apikey`&&e!==`amazonBedrock`}"],
]) {
  if (!finalText.includes(marker)) throw new Error(`${label}: official marker missing`);
  report.official.push(label);
}

console.log(JSON.stringify(report, null, 2));
