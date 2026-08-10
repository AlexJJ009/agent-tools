# 搬瓦工（BWG）Codex 长会话审计

## 结论

两个 session 不是两个独立开发项目，而是同一项 **Abuse Guard WebSocket correlation remediation** 的“长程执行会话 + 终止审计会话”：

- `019facc3-dc77-7f12-bada-b14e9e29b9ae` 从 2026-07-29 开始执行 Plan v3，持续到 2026-08-04。产品候选已经提交并推送到 feature branch，但没有创建 PR，也没有合并到 `dragtokens/main`。
- `019fcd21-ae76-77e1-ba37-811584b88411` 是用户在 2026-08-04 发起的只读审计。它确认原 Goal 已进入治理/验证递归循环，并向长会话发送停止指令。它本身没有继续产品开发。

当前无需回退 `dragtokens/main`：远端只读核验显示 NewAPI 和 TokenRouter 的 `dragtokens/main` 仍分别是 Goal 启动基线。当前 feature branch 应冻结为参考材料，不能整体当作已验收、可部署或可合并的交付。

问题不是“业务代码完全换题”，而是 **过程和验收设施失控**：约 2,100 行产品仓库增量之外，coordination repository 从冻结 HEAD 又增长 302 commits、276 files、`+74,423/-2`；M5 发生 74 次 review request、113 次 finding opened，最终 AC-09 real-binary acceptance 仍未完成，PR 仍为零。

## 调研任务拆解与执行边界

本分支按以下顺序执行，没有恢复原 Goal：

1. 解析 SSH alias，并以禁止 password/keyboard-interactive、禁止 TTY 的 BatchMode 核验远端 hostname、user 和 Codex 版本。
2. 定位两个 rollout JSONL，记录初始大小、mtime、事件类型和原始 session metadata。
3. 分别运行一次带 300/480 秒超时的 `codex exec resume --ephemeral`，prompt 明确要求只根据历史回顾、不运行工具、不修改文件、不继续目标。
4. 对大 JSONL 采用事件类型计数、用户指令抽取、token 计数和 pre-resume cutoff，而非把 238 MB 全文复制到本地上下文。
5. 读取原始 `/goal` attachment、Plan v3、acceptance、runtime/findings ledger 及对应 repo 的 `AGENTS.md`。
6. 对 coordination、NewAPI、TokenRouter 三个仓库执行只读 git 状态、HEAD、diff stat、远端 branch 和 PR 查询。
7. 将事实、会话自述和审计推断分开，形成本文档。

未执行：测试、构建、Docker、代码修改、配置修改、commit、push、PR、merge、清理或生产访问。

## Source boundary 与可复现性

### 主机边界

- SSH alias：`bwg-root`
- `ssh -G` 当前解析：`root@89.208.241.86:22`，`ProxyJump aliyun-newapi`
- 远端核验：hostname `bgw`，user `root`
- Codex：`codex-cli 0.146.0`
- resume 实际模型：`gpt-5.6-sol`，reasoning `medium`
- 用户要求 GPT-5.5 medium；当前 spawn/model surface 不提供 GPT-5.5，因此使用当前同级模型并明确记录替代。

### Rollout 边界

| Session | 原始路径 | pre-resume cutoff | pre-resume 大小；resume 后行数/大小 | 审计用途 |
|---|---|---:|---:|---|
| `019fcd21-ae76-77e1-ba37-811584b88411` | `/root/.codex/sessions/2026/08/04/rollout-2026-08-04T14-16-04-019fcd21-ae76-77e1-ba37-811584b88411.jsonl` | 2026-08-04 14:24:04 UTC `task_complete` | 711,148 bytes；resume 后 210 行 / 791,904 bytes | 终止审计会话 |
| `019facc3-dc77-7f12-bada-b14e9e29b9ae` | `/root/.codex/sessions/2026/07/29/rollout-2026-07-29T07-25-44-019facc3-dc77-7f12-bada-b14e9e29b9ae.jsonl` | 2026-08-04 14:23:20 UTC `task_complete` | 238,383,524 bytes；resume 后 129,774 行 / 238,503,112 bytes | Plan v3 长程执行会话 |

重要限制：尽管使用了 `--ephemeral`，Codex 0.146.0 仍把本次 resume 的 prompt/answer 追加到了原 session rollout；新增 `task_complete` 分别在 15:17:44 和 15:20:17 UTC。所以上表以 pre-resume cutoff 区分原始历史和本次审计追加内容。resume 没有修改代码或配置，但它不是“JSONL 字节级无痕”的只读操作。

### 证据强度

- **当前独立核验**：SSH 身份、文件位置、git status/HEAD/diff stat、远端 branch SHA、`gh pr list`、ledger event count、文件行数。
- **会话/ledger 记录，未重跑**：M0-M4 gate PASS、部分 reviewer PASS、各次 M6 failure 的详细原因。
- **推断**：scope drift、overdesign、维护成本和工作流缺陷。本文给出推断所依赖的事实，不把它们伪装成测试结论。

## Session `019facc3-dc77-7f12-bada-b14e9e29b9ae`

### 原始目标

原始 `/goal` attachment 明确要求执行已经审查为 READY 的 Plan v3，从 M0 连续推进到 M7，只在 paired merge 或真正 stop-class action 停止。业务契约包括：

- NewAPI 生成 connection correlation ID `B`；accepted WS logical turn 使用 `B-ws-(T-1)`。
- retry/failover 复用同一 turn ID，control frame 不递增；不能逐 turn 并发修改共享 connection context。
- generic 与 Responses WS dialer 均要清除外部 `X-Request-ID` 并写入可信内部 ID；缺少内部 ID 时 pre-dial fail。
- TokenRouter 三种 WS transport 在 moderation、fingerprint、warning 和 post-turn policy 中使用同一 turn ID。
- local moderation block 与 upstream cyber warning 保持不同语义。
- cross-repo acceptance 证明 `NewAPI log ID = TokenRouter fingerprint ID = Guard join ID`。
- M5 独立 review、M6 exact-image real-binary local acceptance、M7 paired PR/required checks/人工 merge HOLD。

Plan 明确排除 OVH/生产访问与变更、现有服务/数据库/Redis/Compose 变更、force-push、direct main push 和绕过 branch protection。

### Timeline

| 时间 | 阶段 | 可确认状态 |
|---|---|---|
| 2026-07-29 07:25 UTC | Goal 启动 | 从 frozen coordination `0f6d469...`、NewAPI `f884f9e...`、TokenRouter `d5e3f11...` 启动。早期发生 TokenRouter linked-worktree identity 隔离事故；外部会话随后报告清理并改用 worktree-local config/hooks。 |
| 2026-07-29 | M0-M4 | ledger/session 声称 test-only red、最小实现、focused/full gates 和 cross-repo contract 已完成；本审计未重跑这些 gate。产品候选稳定为 NewAPI `2fa00c21...` 和 TokenRouter `cc3b545d...`。 |
| 2026-07-30 起 | M5/M6 循环 | 每次 M6 暴露新的 harness/admission/evidence-binding 缺陷后，返回 M5、补 checker/test、再次 review。业务候选 SHA 长期不变，coordination HEAD 持续增长。 |
| 2026-08-01 | 用户清理磁盘后继续 | 磁盘 admission blocker 解除；会话继续 M5/M6，而不是收缩目标。 |
| 2026-08-04 | Attempt 15 / R09 | R08 PASS 后，M6 因 `RCA candidates differ from admission` 失败；随后增加 T13/H13、冻结更多前序历史，发起 R09。R09 未完成。 |
| 2026-08-04 14:22 UTC | 停止 | 审计 session 向本 session 发送停止指令；Goal 标记为 blocked，未继续测试、修改、push、PR 或清理。 |

### 产物和仓库状态

#### NewAPI

- Worktree：`/root/work/new-api/abuse-guard-remediation-v1`
- HEAD / remote feature branch：`2fa00c21c98b28b11288cc86e8409dd9c8be2eb9`
- 相对 `dragtokens/main`：12 commits；15 files；`+853/-27`
- 当前 `origin/dragtokens/main`：`f884f9e47b03d9e4bb7d682b9c2898323ef21868`
- `gh pr list --state all --head fix/abuse-guard-remediation-v1`：`[]`
- 当前 worktree clean。

主要 production paths：

- `relay/channel/api_request.go`
- `relay/responses_websocket.go`
- `model/log.go`
- `service/text_quota.go`
- `service/violation_fee.go`

#### TokenRouter

- Worktree：`/root/work/tokenrouter/abuse-guard-remediation-v1`
- HEAD / remote feature branch：`cc3b545db20941ba546a45269c6af1177a656741`
- 相对 `dragtokens/main`：8 commits；18 files；`+1,277/-31`
- 当前 `origin/dragtokens/main`：`d5e3f11e43a719f3fd3aef9f22a06bc8105a67df`
- `gh pr list --state all --head fix/abuse-guard-remediation-v1`：`[]`
- 当前 worktree clean。

主要 production paths：

- `backend/internal/guarddaemon/guard.go`
- `backend/internal/handler/content_moderation_helper.go`
- `backend/internal/handler/openai_gateway_handler.go`
- `backend/internal/service/content_moderation.go`
- `backend/internal/service/openai_ws_http_bridge.go`
- `backend/internal/service/openai_ws_v2_passthrough_adapter.go`

#### Coordination repository

- Worktree：`/root/work/abuse-guard-remediation-v1`
- 冻结 HEAD：`0f6d46906fced99f3dd1f14c1a195a07a0d72d02`
- 停止点 HEAD：`9be161866bc8b4251a1fef153743bca42eeb0691`
- 增量：302 commits；276 files；`+74,423/-2`
- 当前 worktree clean；无 remote。
- Goal reviews 目录：181 files。
- ledger：runtime 307 行；findings 810 行。
- event count：74 `REVIEW_REQUESTED`、72 `MILESTONE_REVIEWED`、113 `FINDING_OPENED`、141 `FINDING_FIX_APPLIED`、133 `FINDING_CLOSED`。
- 代表性 verifier：
  - `verify/local-acceptance.sh`：4,658 行
  - `verify/local-acceptance-admission.py`：6,964 行
  - `verify/test-local-acceptance-rca-admission.py`：6,890 行
  - `verify/test-local-acceptance.sh`：4,010 行

### 目标漂移节点

#### 事实

1. 产品候选 SHA 在早期稳定后，后续大量 commit 只发生在 coordination repository。
2. 多轮 reviewer PASS 后，下一次 M6 又暴露新的 harness false-green 或 binding defect。
3. checker 后来同时验证 execution root、snapshot path、candidate tuple、receipt schema、exact argv/hash、ledger sequence、prior review prompt/report hash、Git ancestry 和历史 continuity。
4. H13 单轮就对 admission checker增加约 508 行、删除 24 行；T13 对测试增加 558 行、删除 338 行，并冻结 R08 exact commit/tree/hash/ledger suffix 等物理历史。
5. AC-09 仍为 `NOT_RUN`；没有 canonical success receipt、live matrix、PR、CI required checks、merge 或 final acceptance。

#### 推断

- 漂移不是“改做另一个产品”，而是从业务交付漂移成了 **构建一个自证、再证明自证历史不可篡改的治理产品**。
- “任何 acceptance harness 缺陷都属于当前 Goal”取消了 scope 上限。每发现一个 checker 缺陷，就引入新的 test、checker、review、hash 和 ledger binding，形成递归维护循环。
- frozen exact-history 常量与具体 commit/sequence 深度耦合，难以迁移、局部修改或复用。它们能证明某段物理历史符合 checker，却不能替代 real-binary 业务行为证据。
- 约 2,100 行产品增量对应 74,000 余行 coordination 增量，说明保障成本与业务改动失衡；不能据此断言每一行都无用，但无法从交付结果证明其边际价值。

### 失败或缺失的 gate

- **AC-09 / M6**：real-binary local acceptance 未成功运行；TokenRouter startup exit code 2 未关闭；live matrix、canonical success receipt 和 root-cause attribution 均缺失。
- **M5 final review**：R09 未完成；没有正式 report、reviewed/closed ledger tail 或 verdict commit。
- **M7 / AC-10**：两个仓库均无 PR、required checks、repo-compliant review、paired merge approval、merge 或 merge 后验收。
- **既有 PASS 的边界**：本审计没有重跑 M0-M4 tests/full gates；R08 PASS 后 M6 立即失败，证明 reviewer PASS 只覆盖当轮 artifact，不能推导 AC-09 或 merge-ready。
- **Gate 与 git workflow 耦合**：outer shell suite 曾因 coordination worktree 尚未 commit/clean 而失败；这扩大了与产品行为无关的失败面。

### 维护性影响

- `dragtokens/main` 未被破坏，因此没有 main rollback 风险。
- feature branches 包含可能有价值的业务提交，但当前只能作为待审材料；不能整体 cherry-pick 或 merge。
- coordination harness 的主要风险是维护成本、错误归因和无限 review，不是已经证明破坏产品 runtime。
- 早期 plain `goal-plan-runtime setup-identity` 曾触及 linked worktree common config/hooks，说明 Goal runtime 的机械 setup 命令存在跨 worktree blast radius；虽会话报告已清理，本审计没有重演事故来独立证明当时每一步。

## Session `019fcd21-ae76-77e1-ba37-811584b88411`

### 目标与实际行为

用户要求理性判断长会话是否严重偏离、是否已创建/合并 PR、是否应该回退，以及若不可信则停止它。该 session：

1. 调查长 session 和三仓状态。
2. 判断 main 未变、无需回退。
3. 判断当前 Goal 已进入验证/治理循环，不能继续当作可靠交付。
4. 向长 session 发出停止指令，要求不再等待 reviewer、测试、修改、commit、push、PR、merge 或清理。
5. 长 Goal 随后进入 blocked/idle。

该 session 自身只有约 2.4M pre-resume total token count，作用是审计和止损，不是第二个 overdesigned implementation。其主要结论经本次独立 git/remote 查询得到确认：两个 main 未变化、feature branches 存在、PR 为零。

### 边界与不足

- 它报告 coordination 增量约 311 commits、286 files、`+75,643/-2`；本次以原始 launch frozen HEAD `0f6d469...` 为基准独立计算为 302 commits、276 files、`+74,423/-2`。差异来自基准选择；综合报告应采用本次明确可复现的 frozen-HEAD 口径。
- 它曾报告 coordination 有 untracked scratch；本次当前状态核验为 clean。不能据此推断 scratch 被谁、何时清理，也不能把旧状态当作当前事实。
- 它没有逐行 review 两个产品候选，也没有重跑 gate；“不可信、不可整体合并”是证据不足下的风险处置，不等于已证明每个业务 commit 错误。

## 机器约束缺口

这些缺口直接来自本案例，不是抽象口号：

1. **没有 scope-growth budget**：Plan 没有限制 coordination-only commits、verifier LOC、review rounds 或 finding churn；业务 SHA 不变时，harness 仍可无限增长。
2. **没有 decomposition admission**：单个 `/goal` 同时容纳两仓业务实现、跨仓 contract、Docker build、real-binary stack、RCA、review protocol、PR/merge lifecycle。启动前没有机器拒绝“多个独立风险域的单一 Goal”。
3. **没有 progress-to-outcome watchdog**：业务候选 SHA 长期不变、AC-09 长期未运行，但 review/ledger/token 持续增长，没有自动 STOP/ESCALATE。
4. **没有 retry/round cap**：M5/M6 可以无限往返；“loop-until-dry”没有最大轮次、最大新增范围或必须拆分条件。
5. **review independence 只在 prompt/agent 层**：同一 Codex 系统内 subagent 的 PASS 不等于 GitHub required review、人类 review 或外部验收。
6. **验证器可自行扩权**：发现 harness defect 后，默认把修 verifier 归入原 Goal；没有结构化变更请求证明它仍是最小必要范围。
7. **gate 证明对象混乱**：大量 gate 证明 Git/ledger/history 形状，而 AC-09 要证明真实 binaries 的业务行为。缺少 machine-readable `gate -> acceptance criterion -> exact artifact` 一对一覆盖检查。
8. **等待机制浪费 context**：长 session 曾约每分钟重新处理大上下文等待 reviewer；没有用低成本外部 job wait/notification 代替模型轮询。
9. **worktree blast-radius guard 不够早**：plain identity setup 能触及 common git config/hooks；应该在命令实现层拒绝 linked worktree common mutation，而不是事故后追加 prompt 规则。
10. **resume 的“ephemeral”语义不满足审计无痕**：Codex 0.146.0 的 resume 仍追加原 rollout。未来原始证据应先复制到只读快照或记录 byte cutoff/hash，再 resume。

## 如果重新开始，应该如何拆分

这里给出搬瓦工（BWG）案例的项目级 disposition，不替代最终跨案例 PRD。

1. **只读 disposition**：锁定三个 HEAD、列出每个产品 commit 和 coordination commit；逐项标记保留、重写、丢弃、仅证据。禁止修改。
2. **行为契约与 red tests**：把 Request ID ownership、turn index、retry/control frame、transport parity、warning/block 语义写成短规格；每条只对应一个旧 main 上真实 red 的 deterministic test。
3. **NewAPI handshake trust boundary PR**：只处理 header override、可信 ID 和 missing-ID pre-dial fail。
4. **NewAPI logical-turn/log PR**：只处理 turn ID、retry/control frame 和日志传播。
5. **TokenRouter transport PRs**：`ctx_pool`、`http_bridge`、`passthrough` 可分别审查，至少不要把三种 transport、Docker 和 governance 放进同一个交付单元。
6. **TokenRouter warning/block PR**：纯语义和数据兼容测试，不依赖跨仓 stack。
7. **最小 cross-repo contract**：固定前述 exact SHAs，只验证 log/fingerprint/join equality；一个小 Compose、一个 runner、一份机器结果、teardown check。
8. **bounded startup RCA**：只定位 TokenRouter exit 2；RCA 不得顺便修改通用 review/ledger protocol。
9. **real-binary acceptance**：作为独立交付 gate，使用 exact images 和 disposable resources；失败时返回具体业务任务，不在原任务内扩建通用证明语言。
10. **标准 PR lifecycle**：每个 repo 按自己的 template、CI、required review 走；只有明确依赖的 paired release 才在最终 merge 点同步。

每个任务必须具备：单一 owner repo、明确非目标、可在数小时内重跑的 acceptance、最大 review rounds、最大 scope delta，以及超过阈值时自动停止并创建新任务，而不是继续扩展当前 Goal。

## 可复用结论

- 目标驱动不是“一个 Goal 容纳所有达到目标所需的工作”。跨 repo、跨 runtime、跨治理域的目标需要先转成有依赖关系的可合并任务。
- verifier 是产品代码。它一旦超过一次性 glue 的规模，就必须有独立 owner、版本、测试和维护预算；不能隐身在业务 Goal 内无限扩张。
- `PASS` 必须标明证明对象。synthetic history mutation PASS 不能替代 real-binary acceptance，subagent review PASS 不能替代 repo review。
- 当业务 candidate SHA 连续多个 review cycle 不变，而 coordination LOC、finding 和 token 持续增长时，应由机器自动判定“交付无进展”，停止并拆分。
- 本案例最安全处置是：main 不回退、feature branch 冻结、coordination harness 不继承为新架构、从 clean main 创建小 PR，只选择性复用能够映射到明确行为契约且有最小测试保护的提交。

## 原始命令与关键证据位置

只读主机核验：

```bash
ssh -G bwg-root | awk '/^(hostname|user|port|proxyjump|identityfile) /{print}'
ssh -o BatchMode=yes -o PasswordAuthentication=no \
  -o KbdInteractiveAuthentication=no -o RequestTTY=no bwg-root \
  'hostname; id -un; codex --version'
```

受限 resume（两个 ID 分别运行，外层使用 `timeout 300` / `timeout 480`）：

```bash
printf '%s' "$AUDIT_PROMPT" | ssh -o BatchMode=yes -o RequestTTY=no bwg-root \
  'timeout 300 codex exec resume --ephemeral --skip-git-repo-check <SESSION_ID> -'
```

远端 branch / PR 证据：

```bash
git ls-remote https://github.com/AlexJJ009/new-api.git \
  refs/heads/fix/abuse-guard-remediation-v1 refs/heads/dragtokens/main
git ls-remote https://github.com/AlexJJ009/tokenrouter.git \
  refs/heads/fix/abuse-guard-remediation-v1 refs/heads/dragtokens/main
gh pr list --repo AlexJJ009/new-api --state all \
  --head fix/abuse-guard-remediation-v1 --json number,state,url,headRefOid,baseRefName
gh pr list --repo AlexJJ009/tokenrouter --state all \
  --head fix/abuse-guard-remediation-v1 --json number,state,url,headRefOid,baseRefName
```

关键 evidence：

- 原始执行请求：`/root/.codex/attachments/910bd6ed-11a9-4da3-b481-6fe6869c3950/pasted-text-1.txt`
- Plan：`/root/work/abuse-guard-remediation-v1/docs/goals/2026-07-29-abuse-guard-ws-remediation-v1/plan.md`
- Acceptance：同目录 `acceptance.md`
- Runtime ledger：同目录 `runtime.jsonl`
- Findings ledger：同目录 `findings.jsonl`
- R09 prompt：同目录 `reviews/m5-startup-rca-r09-prompt.md`
- NewAPI candidate：`/root/work/new-api/abuse-guard-remediation-v1` @ `2fa00c21...`
- TokenRouter candidate：`/root/work/tokenrouter/abuse-guard-remediation-v1` @ `cc3b545d...`
- Coordination stop point：`/root/work/abuse-guard-remediation-v1` @ `9be16186...`
