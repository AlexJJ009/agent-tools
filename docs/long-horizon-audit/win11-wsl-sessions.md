# Win11 / WSL 长会话只读审计

> 范围：仅审计 `019fadf2-db57-7da1-bfc3-b0e9856cf521`、`019fc840-0dca-7db0-8f34-5b128433642f`、`019fae69-7bc9-72a2-8acd-2c730be96540`。本文不是跨会话综合报告，也不是解决方案 PRD。

## 0. 审计任务拆解与执行边界

### 0.1 任务拆解

1. 识别 Win11 native 与 WSL 的独立 `CODEX_HOME`、CLI 和 rollout，禁止串用 profile。
2. 对每条会话发送一次只读审计 resume；明确禁止继续旧目标、修改文件或运行 installer。
3. resume 返回不完整、超时或语义错配时，停止等待，转为流式解析 JSONL。
4. 从 JSONL 重建原始目标、用户追加目标、关键执行节点、验收声明和未完成项。
5. 只读核对相关仓库的 Git 边界、当前文件状态及 rollout 中出现的 commit/PR/制品证据。
6. 逐会话区分事实、推断和未确认项，并提出当时应采用的可独立验收拆分。

### 0.2 Host / profile 证明

| 环境 | 事实 |
|---|---|
| WSL | `CODEX_HOME=/home/alex_mercer/.codex`；CLI `/home/alex_mercer/.local/bin/codex`，版本 `0.146.0`。两条 WSL rollout 均位于该 profile 的 `sessions/`。 |
| Win11 native | `USERPROFILE=C:\Users\Alex Mercer`，`CODEX_HOME` 环境变量未显式设置，因此 native profile 是 `C:\Users\Alex Mercer\.codex`。目标 rollout 位于该目录。正在运行的 App 内嵌 app-server 是 `...\app\resources\codex.exe`，取证时 PID 为 `5808`；另有用户目录下的 native CLI `C:\Users\Alex Mercer\AppData\Local\OpenAI\Codex\bin\d7e8094cfb76a267\codex.exe`。 |
| Win11 会话归属 | rollout 第 1 行的 `cwd` 是 `C:\Users\Alex Mercer\Documents\agentdesk-v20260728-windows-amd64`，`originator=Codex Desktop`。没有用 WSL `CODEX_HOME` resume 该会话。 |

AppX 安装目录内的 `codex.exe` 从外部 PowerShell 直接执行时返回 `Access is denied`；改用用户目录下的 native CLI 后成功出现 `thread.started`。这次 native resume 在约 60 秒后仍在做只读仓库扫描，按审计约束主动中止并转 JSONL，没有继续等待。

### 0.3 Resume 命令与结果

WSL 使用：

```bash
codex exec resume \
  -c 'sandbox_mode="read-only"' \
  -c 'approval_policy="never"' \
  --json -o /tmp/audit-<session>.txt \
  <session-id> '<只读审计提示>'
```

Win11 使用 native PowerShell，显式设置：

```powershell
$env:CODEX_HOME = 'C:\Users\Alex Mercer\.codex'
Set-Location 'C:\Users\Alex Mercer\Documents\agentdesk-v20260728-windows-amd64'
& 'C:\Users\Alex Mercer\AppData\Local\OpenAI\Codex\bin\d7e8094cfb76a267\codex.exe' `
  exec resume -c 'sandbox_mode="read-only"' -c 'approval_policy="never"' `
  --json 019fadf2-db57-7da1-bfc3-b0e9856cf521 '<只读审计提示>'
```

结果：

- `019fae69...`：resume 完成，返回结构化审计；再以原始 JSONL 核对。
- `019fc840...`：resume 完成，但把 PPT 会话错误识别成 Base URL/fleet 会话。该输出不能用于审计原任务，只能作为“长会话恢复发生任务语义错配”的故障证据。
- `019fadf2...`：native resume 成功进入线程并做只读扫描，但未在短时限内产出 final；主动中止后以 JSONL 审计。

子代理路由要求是 GPT-5.5、medium reasoning；当前可用的子代理接口没有 GPT-5.5 override，因此本审计使用当前继承的同级高能力模型。没有把模型不可用伪装成已满足。

---

## 1. Win11 `019fadf2-db57-7da1-bfc3-b0e9856cf521`

### 1.1 证据位置与规模

- Rollout：`C:\Users\Alex Mercer\.codex\sessions\2026\07\29\rollout-2026-07-29T05-56-42-019fadf2-db57-7da1-bfc3-b0e9856cf521.jsonl`
- WSL 可读路径：`/mnt/c/Users/Alex Mercer/.codex/sessions/2026/07/29/rollout-2026-07-29T05-56-42-019fadf2-db57-7da1-bfc3-b0e9856cf521.jsonl`
- 规模：58,870 行，约 149 MB；72 次 `context_compacted`，61 个 `session_meta`，79 条用户消息、1,040 条 assistant 消息。
- 时间：2026-07-29 至 2026-08-03；不是一次小开发，而是连续约五天的产品探索、实现、验收、文档和发布工作。

### 1.2 原始目标

#### 事实

rollout 第 9 行的原始请求主要是做技术决策和现状调查：

1. 判断 AgentDesk Evaluation 应在已安装 AgentDesk 的 Win11 运行，还是迁到 WSL。
2. 评估 Promptfoo 与其他 evaluation 框架。
3. 检查 OpenResponses 监听、现有 46 条腾讯表格任务、同事的 token benchmark 脚本，以及不同 Agent 产品的兼容边界。
4. 希望得到 HTML、准确率、失败用例和原因。

第 441 行扩展为：解释现有 shell 脚本；根据 10 篇 Benchmark survey 设计更清晰的 task/workspace/fixture/rubric 规范；但此时仍是“调研与设计”，不是“在一个线程中交付跨平台可发布产品”。

#### 推断

当时合理的第一个冻结 outcome 应是：

> 证明 Win11 AgentDesk 能被一个最小 evaluation harness 调用，并让 1 个有 fixture 的 task 产出可审计 trace、明确 verdict 和 HTML 报告；同时形成下一阶段 PRD。

这个 outcome 在会话前段已经足够成立，后续工作本应进入新的开发任务。

### 1.3 实际阶段与 timeline

| 阶段 | JSONL 节点 | 事实 |
|---|---:|---|
| 平台/框架判断 | 9–911 | 决定 AgentDesk 留在 Win11，Promptfoo 做 MVP；识别 Linux 包架构不匹配、OpenResponses 端口差异、原脚本只证明 token/transport。 |
| Benchmark 规范设计 | 441–911 | 讨论 fixture、每题 workspace、hidden checks、rubric、Judge、结果分母和隔离边界；产出分析草案。 |
| 建项目并接通真实接口 | 1269 起 | 用户要求创建工作目录、安装 Promptfoo、接通 OpenResponses、导入前置文件并生成第一批日志。 |
| Runner / trace / scoring 产品化 | 多轮 compaction 后 | 实现逐题 workspace、日志解析、normalized trace、hard checks、Binary/Graded Judge、报告和 CLI。 |
| 双语报告和 task authoring | 45121–51077 | 新增中英 HTML、Binary/Graded 双模式、`required_capabilities`、fixture hash 命令、单题/全量运行说明。 |
| 安装与发布 | 51077 起 | 工作扩大到 Win11/macOS portable ZIP、P00/P01 probe、installer、进度提示、AgentDesk readiness、产品文档。 |
| 文档减法与二机验证 | 57032–58709 | 清理/重组文档；另一台 Win11 安装成功并通过 P00/P01；补 AGENTS 索引和四题 HTML 阅读指南。 |
| 末尾状态 | 58806–58868 | 声明同一 ZIP 可作为 macOS Preview，但无 Mac 实机验收。 |

### 1.4 Scope drift

#### 事实

范围按以下顺序持续扩大：

1. “在哪个平台、选什么框架” → Benchmark 研究与 PRD。
2. 研究/PRD → 创建完整 `agentdesk-eval` 项目并联调真实 AgentDesk。
3. 单题 probe → 46 题 catalog、fixture 导入、日志 lifecycle、trace parser。
4. runner → Binary/Graded scoring、Judge prompt、hard-check DSL、capability 声明。
5. evaluation core → 双语 HTML、产品诊断、task authoring CLI。
6. 开发工具 → Win11/macOS portable installer、release packaging、P00/P01 安装验收。
7. 发布 → README、AGENTS、QuickStart、User Guide、产品培训和 report 解读。

这些后续需求多数由用户逐轮明确提出；不能简单归类为“agent 擅自加需求”。问题是每次新增独立 outcome 后，没有结束当前 task、创建版本化 backlog 或新 PR，而是把所有工作继续塞进同一个会话和同一个未版本化目录。

#### 推断

scope drift 的机制不是单次误解，而是“任何合理的新需求都被当成当前 Goal 的下一 milestone”。缺少的机器边界是：当新增了新的 runtime、平台、用户角色或验收面时，强制生成新 issue/PR，并禁止当前任务吸收。

### 1.5 Overdesign、垃圾代码与结构后果

#### 已确认事实

1. **没有 Git 历史。** 当前父目录的只读结果是：

   ```text
   ## No commits yet on master
   ?? .pnpm-store/
   ?? agentdesk-eval/
   ?? tmp/
   ```

   `agentdesk-eval/` 整个目录未跟踪，父仓库零 commit。数天的实现、重构、测试、发布和文档没有可审阅 diff、稳定基线、回滚点或 commit-bound acceptance。这是本会话最严重的工程问题。

2. native resume 的只读统计显示：

   - `src/`：22 个文件，约 14,022 行；
   - `scripts/`：13 个文件，约 3,563 行；
   - `tests/`：29 个文件，约 16,188 行；
   - `benchmark/`：369 个文件，约 15,406 行；
   - 最大文件包括 `tests/terminal-evidence-validator.test.mjs` 2,448 行、`tests/report-finalization.test.mjs` 1,919 行、`src/scoring.mjs` 1,895 行。

   行数本身不是缺陷；缺陷是这些规模全部存在于无 commit、无 PR 的工作区，无法证明每个阶段何时加入、是否仍被使用、是否有 reviewer 接受。

3. 一次外部 Win11 安装日志显示 `npm audit` 有 4 个漏洞（3 moderate、1 high）。会话没有给出 release 前清零或风险接受记录。

4. 测试曾出现 `319/320`，唯一红项是 Promptfoo 子进程 60 秒超时。agent 后续有针对性复现和更长窗口运行，但没有一份 commit-bound、CI-owned 的最终 acceptance 证据。

5. macOS 只有脚本、native binding 选择和 mock/静态验证；没有一台真实 macOS 的 `doctor`、P00/P01 和 HTML 检查。会话最终只敢称 `macOS Preview`，这个边界是正确的。

#### 推断

- `hard checks`、Judge、reporter、trace parser、installer、release catalog、双语 UI 同时自建，很可能形成了“一个项目内的多个产品”。是否存在可安全删除的具体文件，不能只凭行数判断，必须先建立依赖图和覆盖率；因此本文不把某个文件直接定性为无用。
- 2,448 行的 validator test 和 1,895 行的 scoring module 是可维护性热点，应拆模块，但只有在行为 characterization tests 完成后才能做，不能直接重写。

### 1.6 Gate 缺口

- **版本门禁：** 零 commit，无法把测试、制品和报告绑定到 source revision。
- **PR/review：** 没有 PR、merge commit 或 required checks 证据；独立 subagent review 不是 Git review gate。
- **CI：** rollout 主要是本机 `npm test`；没有在干净 checkout 验证 Windows PowerShell 5.1/7、Node 版本矩阵、ZIP 安装和报告生成。
- **release provenance：** ZIP 的 SHA256 有记录，但源码目录无 commit，因此 hash 不能回答“由哪一版源码生成”。
- **安全/依赖：** release 安装仍报告 high vulnerability；没有 allowlist 或接受记录。
- **跨平台：** macOS 未实测；不能作为正式支持面。
- **Benchmark 质量：** 只完整跑 4 题；46 题中大量 task 的 fixture、rubric 或环境尚未 ready。

### 1.7 当时应采用的任务拆分

1. **D0 设计决策**：Win11/WSL、Promptfoo/Inspect 对比；交付 ADR，不写产品代码。
2. **D1 单题 transport probe**：只证明 OpenResponses、token、timeout 和日志 trace ID。
3. **D2 单题 evaluation slice**：一个 fixture、一个 workspace、一个 Binary verdict、一个 HTML。
4. **D3 Trace lifecycle**：日志切片、清理、混流隔离、normalized trace；单独 PR。
5. **D4 Scoring contract**：Binary 与 Graded schema、Judge evidence、失败分类；不做 UI。
6. **D5 四题 sub-benchmark**：固定 4 题、首次串行全跑、无 resume、commit-bound report。
7. **D6 Product CLI**：单题/整 suite、fixture hash、task validation。
8. **D7 HTML 与双语**：report UX，绑定稳定 JSON schema。
9. **D8 Win11 portable release**：只支持一台干净 Win11 的安装、P00/P01、卸载/升级。
10. **D9 macOS feasibility**：在真实 Mac 验收前只产出兼容性调查，不进入正式 release。
11. **D10 文档/authoring**：README、AGENTS 索引、QuickStart、User Guide；只对已发布命令写文档。
12. **D11 Git/CI/release gate**：应在 D2 前完成，而不是最后补；任何后续功能必须有 commit、PR、clean checkout CI 和 artifact provenance。

---

## 2. WSL `019fc840-0dca-7db0-8f34-5b128433642f`

### 2.1 证据位置与规模

- Rollout：`/home/alex_mercer/.codex/sessions/2026/08/03/rollout-2026-08-03T08-31-08-019fc840-0dca-7db0-8f34-5b128433642f.jsonl`
- 清理前备份：同目录 `.jsonl.bak-image-strip-20260803T163621Z`
- 当前 rollout：约 2.3 MB、1,110 行；2 次 compaction、3 个 `session_meta`。
- 原任务 cwd 始终是生命组学答辩 PPT 项目，原始目标与 Base URL/fleet 无关。

### 2.2 Resume 语义错配

#### 事实

原始 JSONL 第 9 行明确要求恢复 `019fc1d2...` 的五页 PPT 会话、继续制作并做 QA。第 429、436 行是用户对 PPT 的具体视觉和内容反馈。第 1105 行的固定探针返回 `THREAD_IMAGE_CONTEXT_REPAIR_OK`。

本轮对同一 ID 执行只读 resume 后，agent 却输出“原始 Base URL 迁移”“WSL 第一、Win11 第二、BWG/L40S/OVH”等另一个会话的审计，并主动读取 `agent-tools` 的 rollout 与代码。这与原始 JSONL 不符。

#### 推断

- fixed-marker probe 只证明模型能返回一行，不证明长历史中的任务身份、cwd 和最近有效目标被正确恢复。
- 当前 resume 会把新的 cwd/AGENTS/environment 追加进旧线程；当历史经过图片剥离、compaction 和跨 cwd 恢复后，模型可能选择了错误的“最近相关任务”。
- 因此这次 resume 的 Base URL 结论全部排除，不用于评价 PPT 开发，只作为恢复机制失败证据。

### 2.3 原始目标与实际阶段

#### 事实

原始目标是：从旧会话恢复五页 PPT 的最近修改意见和经验；复制新模板、迁移已有内容、继续制作、逐页串行加载图片并完成 QA。

实际 timeline：

1. **恢复与初版交付（9–422）**
   - 恢复旧任务与中断点；
   - 复制新模板并保存迁移底稿；
   - 重做第 3 页布局；
   - 修第 2 页标题裁切、第 3/4 页孤字、第 5 页因果链；
   - 产出 V9-05、PDF、迁移底稿、构建脚本和 QA 记录。
2. **用户否定初版粗糙部分（429、436）**
   - 政策截图裁切、标题形状、习近平原文可读性、日期和页首句需改；
   - 第 2 页删回用户已删除的低信息模块；
   - 第 3 页不能是难懂案例堆砌；
   - 第 5 页列五家中心、三项挑战各配示意图；术语不得自造。
3. **V9-06 权威基线与 V9-07（443–1094）**
   - 识别用户保存后的 V9-05 为权威 base，复制为 V9-06；
   - GPT Image 2 无可用 key，改为保存 prompts 和 PPT 原生矢量占位图；
   - 从 V9-06 定点更新到 V9-07；
   - 多轮渲染/复核抓到标题裁切、短尾行、示意图越界和语义错误；
   - 最后可见状态仍是“当前工作版/最新渲染/QA 记录”，不是独立最终 acceptance。

### 2.4 Scope drift 与维护性后果

#### 事实

- 第一阶段已经宣告“最终交付”，用户随即指出多处粗糙缺陷，说明第一次 acceptance 过早。
- 新一轮同时处理政策事实核查、国内外案例叙事、模板定点修改、GPT Image 2 prompts、矢量示意图、跨渲染器标题裁切和包级 QA。
- 当前仓库只读状态有大量未跟踪 drafts、figures、reference 素材和版本脚本，包括 V4、V5、V6、V7、V9、V11 系列脚本/文档；该状态包含其他会话工作，不能全归因于本 session，但证明产物没有被版本化收束。

#### 推断

- PPT 任务的 overdesign 不是“做 QA 太多”，而是把内容研究、事实核查、图片生成、模板迁移、版式修复、渲染兼容和最终验收放在同一任务中反复循环。
- 可重现构建脚本对初版有价值，但用户手工修改后，继续全量重建会破坏人工工作。因此后来改成 V9-06 包内定点修改是正确收敛；这个生产边界应该在任务开始前冻结。
- 多个版本脚本和中间报告若没有一个 manifest 标记 authority、derived artifact 和可删除 scratch，会增加下一位维护者误用旧脚本覆盖人类基线的风险。

### 2.5 机器 gate 缺口

- `validate.py --original`、ZIP/OOXML、占位符、字号和 notes 检查能证明结构，但不能证明视觉正确。
- 标题裁切和一字符尾行多次由肉眼/独立 agent 才发现；现有机器检查没有把文本 bbox、幻灯片边界、短尾行和最小字号变成 fail-closed gate。
- 同一文件在 LibreOffice 与 reviewer 渲染判断不同；没有固定渲染器矩阵或像素差分基线。
- “最终交付”没有要求一个独立 reviewer 对最终覆盖后的同一 hash 再验收所有五页；复核过程中仍不断修文件，旧结论容易失效。
- imagegen 不可用时，任务继续吸收了 prompts 与占位图；更合理的是将三张图作为独立 blocked asset task，不阻塞版式之外的工作，也不把占位图称为最终图。

### 2.6 当时应采用的任务拆分

1. **P0 恢复审计**：只恢复旧会话文字决策和文件 authority，不编辑 PPT。
2. **P1 内容/术语冻结**：五页逐页 claim、来源、禁止表述、备注；用户确认后 freeze。
3. **P2 模板迁移**：只做模板副本和内容迁移，结构/包级验收，不改叙事。
4. **P3 第 1 页**：政策证据裁切与可读性，单页验收。
5. **P4 第 2 页**：美国/欧盟布局，单页验收。
6. **P5 第 3 页**：数据如何支撑科学智能，单页验收。
7. **P6 第 4 页**：只讲现象，单页验收。
8. **P7 第 5 页**：五家中心、三项原文挑战、示意图位置，单页验收。
9. **P8 Image 2 assets**：三张无字图独立生成、来源和 prompts 归档；没有模型/key 时明确 blocked。
10. **P9 最终 assembly**：只从用户权威 base 定点合并已接受页面。
11. **P10 acceptance**：冻结 hash 后再运行结构 gate、五页视觉检查和第二渲染器检查；任何修复都使旧 acceptance 失效并重跑受影响页。

---

## 3. WSL `019fae69-7bc9-72a2-8acd-2c730be96540`

### 3.1 证据位置与规模

- Rollout：`/home/alex_mercer/.codex/sessions/2026/07/29/rollout-2026-07-29T08-06-16-019fae69-7bc9-72a2-8acd-2c730be96540.jsonl`
- 规模：54,057 行，约 132 MB；71 次 compaction、131 个 `session_meta`、162 条用户消息、1,239 条 assistant 消息。
- 时间：2026-07-29 至 2026-08-04。

### 3.2 原始目标

#### 事实

第 9 行最初只要求说明并验证 Win11 单机 Helper：

1. 怎么启动；
2. 是否后台常驻；
3. 本地 Dashboard 是什么；
4. 如何和服务器代充系统联动；
5. 解释架构、运行逻辑和业务逻辑。

第 161–412 行加入了一个具体 UI bug 和最小 release 要求：空闲状态操作人切换不成功；需要修复，并提供 ZIP + BAT/SH 的手动 release。

#### 推断

合理的首个冻结 outcome 应是：

> 在一台 Win11 上修复空闲状态操作人切换，并证明服务器发出一个指定操作人的任务后，本机 Helper 能领取、拉起 AdsPower，并留下清晰日志；附一个可重复安装的内部 ZIP。

### 3.3 实际阶段与 scope drift

#### 事实

会话随后吸收了至少八类独立 outcome：

1. Dashboard 操作人、API key 和任务领取状态。
2. Microsoft 登录/onboarding 的邮箱、OTP、about-you、all-set 等 DOM bug。
3. 浏览器/Helper/Server 的阶段恢复、safe hold、Profile 生命周期和支付确认。
4. Debug DOM/trace、多语言识别、页面 fingerprint 和 sanitizer。
5. Extension/Helper/Server 多仓库发布、制品同步和 release SSOT。
6. Win11 Helper 一键安装/更新、Bootstrap/Update ZIP、PowerShell 5.1/7。
7. 新操作人 `zzt` 横跨 Extension、Helper、Dragtokens App、微软/谷歌业务。
8. 新卡台、无 API 结算、指定 `paymentMethodId` canary 和卡台抽象。

这些扩展多数来自用户明确追加，但没有拆成 serial PR/issue；每次真实 E2E 暴露新问题后，会话同时修代码、改发布、换版本、换语言和再测，导致变量无法单独控制。

### 3.4 实际完成阶段

resume 审计与 JSONL 共同支持以下事实：

- 有明确 merge/PR 证据的工作包括多语言/create-password、TokenRouter 人工验收、sub-profile 复用、Win11 Helper 更新、PowerShell 兼容、`zzt` 操作员等。
- 会话末期验证了 Extension 与 Helper 的多个 ZIP，并核对 manifest、Git blob 和 SHA256。
- 另一台/本机的部分真实流程成功，但没有在一个最终版本上把最初问题逐项跑完。
- 越南语 E2E 最终未付款；YesCaptcha 新 Profile 的最终真实 storage 注入未确认；最新 Helper/Extension 未形成一轮完整线上 E2E。
- macOS 更新未实测；API-less 卡台和指定卡 canary 未实现。

### 3.5 Overdesign、不可维护性与结构破坏

#### 已确认事实

1. **版本/制品碎片化。** resume 审计从历史计算 `3.0.92 → 3.0.106` 之间有 51 commits、14 merge commits、60 个文件变化、约 `+3329/-239`，与用户“这一批问题合成一次小版本”冲突。
2. **Release SSOT 漂移。** 用户明确 Extension 应从 Dragtokens App 发布，但 `haoshangkami/releases/extension` 仍保留多版制品；历史 README 的 current release 曾落后于目录实际版本；release ownership PR 未在当时闭合。
3. **Debug contract 分散。** Extension 保留的结构字段会被 Helper 二次 sanitizer 丢弃；之后 review 又发现低熵 fingerprint 和敏感信息风险。两个运行时各自清洗同一 evidence schema，容易字段/安全策略漂移。
4. **状态机重复。** Extension、Helper、Server、Client 都表达 onboarding/支付/恢复状态；历史反复出现浏览器已进入下一页但 Extension 仍报旧阶段、TokenRouter 已提交但 Helper/Server 仍 safe hold、Profile 已关闭但锁未释放。
5. **卡台抽象不成立。** 历史文件证据显示 `card_platforms.ts` 对 `vmcardio` 做 literal 限定并直接 import client，`payment_methods.ts` 和 `manualPaidConfirmation.ts` 也直接依赖 VM Cardio 行为；新增无 API 卡台不能直接复用。
6. **当前 checkout 仍脏。** 只读状态包括 `.codex/README.md`、`CLAUDE.md`、`status.md` 修改，`adspower-helper` 子模块状态，以及多份 untracked release ZIP。当前状态可能含后续会话工作，不能全部归因于本 session，但说明制品/仓库清理没有形成稳定边界。

#### 已确认的运行时结构破坏/风险

- 多次测试混用了不同 Extension/Helper 版本，某次实测仍是旧插件，不能证明新修复。
- Profile、任务锁、Server stage 和 UI stage 曾不一致；这是业务状态所有权分散的实际后果，不只是代码风格问题。

#### 未确认

- 没有足够证据把某个具体源码文件判定为“完全无用、可安全删除”。
- 多仓库 PR 后当前 production 是否仍保持相同版本组合，未在本轮只读审计中重新做线上验证。

### 3.6 Gate 缺口

- 没有“原始问题 × 最终版本 × 真实环境”的冻结 acceptance matrix。
- ZIP/manifest/SHA256 成功被多次当成 release ready，但它们不证明安装、重启、任务领取、DOM 自动化、支付和清理 E2E。
- Mock DOM 不能证明真实 React rerender、focus/trusted input 和多语言页面。
- 没有固定多语言 fixture corpus 和页面状态 corpus。
- 没有 Extension/Helper/Server 最低兼容版本矩阵；版本快速推进使 E2E 证据失效。
- 后续快速 patch 没有逐个展示独立 review；没有一次围绕最初问题的最终独立 acceptance。
- 部署缺少统一 gate：required CI、server catalog readback、Feishu/应用中心制品、员工机器旧版→新版更新、public smoke 和 rollback drill。
- 新卡台没有 `paymentMethodId` 原子锁定和 fail-closed canary；随机选卡不能作为指定卡验收。

### 3.7 当时应采用的任务拆分

1. **H1 Dashboard operator bug**：只修空闲切换和 API key readback；Win11 单机验收。
2. **H2 Server→Helper dispatch**：一个操作人、一条任务、领取/heartbeat/AdsPower 拉起；不做 onboarding。
3. **H3 Debug evidence contract**：Extension→Helper→JSONL 固定 schema、单层敏感信息策略、parity tests。
4. **H4 Login/onboarding pages**：邮箱、OTP、about-you、all-set、create-password；固定页面 corpus。
5. **H5 State ownership/recovery**：定义 Browser、Extension、Helper、Server 各自 authority 和幂等 transition；用故障注入测试。
6. **H6 Payment/cleanup**：只做 Checkout、支付核验、取消续费、清理；不引入新卡台。
7. **H7 Multilingual**：语言无关 DOM contract + fixture corpus；语种新增只加 fixture，不改状态机。
8. **H8 Release SSOT**：Extension 与 Helper 分开 source/release；一次批次一个版本、compatibility manifest、clean-build artifact。
9. **H9 Win11 install/update**：Bootstrap、Update、PowerShell 5.1/7、旧版到新版、`/ready`；macOS 明确 excluded。
10. **H10 Operator expansion**：`zzt` 作为跨仓库 schema change，独立 PR 和契约测试。
11. **H11 Card platform interface**：先定义 adapter、verified/unverified/manual_pending 账务语义；不接真实支付。
12. **H12 Specified-card canary**：显式 `paymentMethodId`、原子锁定、不可用即失败、绝不静默换卡；独立 production canary。

每个任务必须绑定一个版本/commit、一个变量集、一组机器可执行 AC 和一次独立 acceptance；不能用后续任务的 ZIP 或人工跑通反向证明前一个任务完成。

---

## 4. 本分报告的证据边界

- 对三条会话都实际发起过 resume；但只有 `019fae69...` 的 resume final 与原始任务一致。
- `019fc840...` 的 resume final 明确错配，因此本文以原始 JSONL 为 authority。
- Win11 native resume 被主动中止，没有 final；本文以 JSONL 和 native PowerShell 的只读仓库输出为 authority。
- 当前 Git 状态用于证明“现在是否存在版本边界”，不用于断言所有 dirty 文件都由目标会话产生。
- 本轮没有运行 installer、修改配置、继续旧开发、部署、提交或清理任何目标仓库。
