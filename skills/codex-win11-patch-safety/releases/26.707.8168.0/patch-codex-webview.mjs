// Captured feature-signature patcher for OpenAI.Codex 26.707.8168.0.
// This candidate must not be activated until recipe.json promotionRequirements pass.
import fs from "node:fs";
import path from "node:path";

const root = process.argv[2];
if (!root) throw new Error("Usage: node patch-codex-webview.mjs <unpacked-app-dir>");

const assets = path.join(root, "webview", "assets");
const report = {
  patched: [],
  skipped: [],
  warnings: [],
  official: [],
  files: {},
};

function read(file) {
  return fs.readFileSync(file, "utf8");
}

function write(file, text) {
  fs.writeFileSync(file, text);
  report.patched.push(path.relative(root, file).replaceAll("\\", "/"));
}

function findOne(prefix, required = true) {
  const files = fs.readdirSync(assets).filter((name) => name.startsWith(prefix) && name.endsWith(".js"));
  if (files.length === 0) {
    const message = `missing ${prefix}*.js`;
    if (required) throw new Error(message);
    report.warnings.push(message);
    return null;
  }
  files.sort((a, b) => fs.statSync(path.join(assets, b)).size - fs.statSync(path.join(assets, a)).size);
  return path.join(assets, files[0]);
}

function replaceOnce(file, label, source, target, required = true) {
  let text = read(file);
  if (text.includes(target)) {
    report.skipped.push(`${label}: already patched`);
    return false;
  }
  if (!text.includes(source)) {
    const message = `${label}: source pattern not found`;
    if (required) throw new Error(message);
    report.warnings.push(message);
    return false;
  }
  text = text.replace(source, target);
  write(file, text);
  return true;
}

const service = findOne("use-service-tier-settings-");
if (service) {
  report.files.serviceTierSettings = path.basename(service);
  replaceOnce(
    service,
    "API key Fast UI auth gate",
    "o=a?.authMethod===`chatgpt`,",
    "o=a?.authMethod===`chatgpt`||a?.authMethod===`apikey`,",
  );
  replaceOnce(
    service,
    "API key Fast UI loading gate",
    "f=!!a?.isLoading||o&&d,p=o&&!f&&u!=null&&u?.requirements?.featureRequirements?.fast_mode!==!1",
    "f=!!a?.isLoading||o&&a?.authMethod===`chatgpt`&&d,p=o&&!f&&(a?.authMethod===`apikey`||u!=null&&u?.requirements?.featureRequirements?.fast_mode!==!1)",
  );
}

const readTier = findOne("read-service-tier-for-request-");
if (readTier) {
  report.files.readServiceTier = path.basename(readTier);
  replaceOnce(
    readTier,
    "API key service tier request gate",
    "if(n!==`chatgpt`)return!1;",
    "if(n!==`chatgpt`&&n!==`apikey`)return!1;if(n===`apikey`)return!0;",
  );
}

const modelQueries = findOne("model-queries-");
if (modelQueries) {
  report.files.modelQueries = path.basename(modelQueries);
  replaceOnce(
    modelQueries,
    "default enabled reasoning efforts",
    "R=[`low`,`medium`,`high`,`xhigh`]",
    "R=[`low`,`medium`,`high`,`xhigh`,`max`,`ultra`]",
  );
}

const modelList = findOne("model-list-filter-");
if (modelList) {
  report.files.modelListFilter = path.basename(modelList);
  replaceOnce(
    modelList,
    "inject GPT-5.6 models when app-server list is stale",
    "function r({authMethod:e,availableModels:n,defaultModel:r,enabledReasoningEfforts:i,includeUltraReasoningEffort:a,models:o,useHiddenModels:s}){let c=[],l=null,u=s&&e!==`amazonBedrock`,d=o.some(e=>e.supportedReasoningEfforts.some(({reasoningEffort:e})=>e===`max`)),f=a&&o.some(e=>e.supportedReasoningEfforts.some(({reasoningEffort:e})=>e===`ultra`));",
    "function r({authMethod:e,availableModels:n,defaultModel:r,enabledReasoningEfforts:i,includeUltraReasoningEffort:a,models:o,useHiddenModels:s}){let h=e=>({reasoningEffort:e,description:`${e} effort`}),g=[{model:`gpt-5.6-sol`,displayName:`GPT-5.6-Sol`,description:`Latest frontier agentic coding model.`,hidden:!1,isDefault:!1,defaultReasoningEffort:`low`,supportedReasoningEfforts:[h(`low`),h(`medium`),h(`high`),h(`xhigh`),h(`max`),h(`ultra`)],serviceTiers:[{id:`priority`,name:`Fast`,description:`1.5x speed, increased usage`}],additionalSpeedTiers:[`fast`]},{model:`gpt-5.6-terra`,displayName:`GPT-5.6-Terra`,description:`Balanced agentic coding model for everyday work.`,hidden:!1,isDefault:!1,defaultReasoningEffort:`medium`,supportedReasoningEfforts:[h(`low`),h(`medium`),h(`high`),h(`xhigh`),h(`max`),h(`ultra`)],serviceTiers:[{id:`priority`,name:`Fast`,description:`1.5x speed, increased usage`}],additionalSpeedTiers:[`fast`]},{model:`gpt-5.6-luna`,displayName:`GPT-5.6-Luna`,description:`Fast and affordable agentic coding model.`,hidden:!1,isDefault:!1,defaultReasoningEffort:`medium`,supportedReasoningEfforts:[h(`low`),h(`medium`),h(`high`),h(`xhigh`),h(`max`)],serviceTiers:[{id:`priority`,name:`Fast`,description:`1.5x speed, increased usage`}],additionalSpeedTiers:[`fast`]}];for(let e of g)o.some(t=>t.model===e.model)||o.push(e);let c=[],l=null,u=s&&e!==`amazonBedrock`,d=o.some(e=>e.supportedReasoningEfforts.some(({reasoningEffort:e})=>e===`max`)),f=a&&o.some(e=>e.supportedReasoningEfforts.some(({reasoningEffort:e})=>e===`ultra`));",
  );
  replaceOnce(
    modelList,
    "allow injected GPT-5.6 through stale availableModels",
    "if(u?n.has(r.model):!r.hidden)",
    "if(u?n.has(r.model)||r.model?.startsWith?.(`gpt-5.6-`):!r.hidden)",
  );
  replaceOnce(
    modelList,
    "show Ultra when model supports it",
    "let n=a?r.supportedReasoningEfforts:r.supportedReasoningEfforts.filter(({reasoningEffort:e})=>e!==`ultra`)",
    "let n=r.supportedReasoningEfforts",
  );
}

const allAssets = fs.readdirSync(assets).filter((name) => name.endsWith(".js"));
const assetText = allAssets.map((name) => read(path.join(assets, name))).join("\n");
for (const marker of [
  ["official max/ultra validator", "e===`max`||e===`ultra`"],
  ["official next-turn model settings", "update-thread-settings-for-next-turn"],
  ["official default model config writer", "set-default-model-config-for-host"],
]) {
  if (!assetText.includes(marker[1])) throw new Error(`${marker[0]} was not found in this build`);
  report.official.push(marker[0]);
}

if (report.warnings.length > 0) throw new Error(report.warnings.join("; "));

console.log(JSON.stringify(report, null, 2));
