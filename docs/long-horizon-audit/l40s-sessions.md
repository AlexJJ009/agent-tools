# L40S Slurm 长程会话审计

审计对象：

- `019fae66-d1a2-7f23-a806-9ed3742464e4`：启动并执行 `slurm-platform-v1` Goal
- `019fc29a-4824-70a3-a177-356edf1c3e82`：恢复、审查并继续同一 Goal

审计日期：2026-08-05（Asia/Tokyo）

## 结论

这两条会话没有证明“Codex 胡乱破坏了现有 Slurm 系统”，但清楚证明了另一种工程失败：**治理过程、审查工件和安全状态机的增长速度，远高于可用产品能力的交付速度**。

截至审计时，仓库从冻结 base 到 HEAD 已有 211 个 commit、281 个变更文件、83,740 行新增、62 次 `REVIEW_REQUESTED`、103 个 finding ID 和 136 份 review 文件。Goal validator 仍报告 `PASS / READY / ACTIVE / M3`，但没有成功 Slurm bootstrap、成功 Slurm query、Goal GPU job、M3 completion、真实 primary archive/fallback 验收或 final acceptance。换句话说，系统已经为“如何证明安全”写出了一个大系统，但原始的“三节点 Slurm 平台”仍未交付。

这不是单一 prompt 写得不好。现有机器约束能保证 append-only ledger、review 顺序、敏感信息边界和 live fail-closed，却不能限制：

- 一个 Goal 是否过大；
- 单个 milestone 是否应继续增长；
- finding 是否被过宽的 AC 自动吸收为 `IN_SCOPE`；
- review/fix 循环的总成本；
- 代码量、模块复杂度和本地治理工件是否已经超过维护预算；
- 外部状态不变时是否还应反复构建 candidate、跑同一 live audit 并提交新 ledger commit。

因此，`goal-plan` 在这次运行中不是“完全没有机器约束”，而是**约束优化目标错位**：它强力优化了可追溯性和 fail-closed，却没有把“小批次交付、复杂度上限、真实用户价值、团队 PR/CI 验收”设为同等强度的硬门禁。

## 本次调研的任务拆解

本审计按以下顺序执行，未继续原 Slurm 开发：

1. **Host 身份与路由核验**
   - `L40S-3`、`l40s-ts`、`l40s-3-via-l40s2` 和 `L40S-2` 均在 SSH banner 阶段超时。
   - 检查现有 SSH 配置后，使用会话实际绑定的旧 alias `l40s-3-public` 成功到达同一主机。
   - 实测身份：`host=ecm-b6f0-0001`、`user=root`、`home=/root`。
2. **会话定位与 resume 尝试**
   - 定位两条原始 rollout JSONL。
   - 分别执行 `codex resume <id> '<只读审计提示>'`，明确禁止修改代码、配置、Goal 状态和继续原任务。
   - TUI 可恢复会话并开始只读核验，但远程 PTY 输出是大体量 ANSI 屏幕刷新，无法稳定采集；分别以 180 秒和 45 秒 timeout 终止。
3. **直接解析会话证据**
   - 复制两份 JSONL 到临时目录，只读统计时间、消息、tool call、context compaction 和用户授权变化。
   - 提取原始 launch attachment、resume prompt、关键 handoff、review failure 和 busy-gate 记录。
4. **仓库与 Goal 交叉核验**
   - 读取 `AGENTS.md`、`status.md`、Plan v10、runtime ledger、findings ledger、review artifacts 和 Git history。
   - 运行 `/root/.local/bin/goal-plan-runtime validate-plan` 与 `validate-runtime`，核验 Plan SHA、HEAD 和 working tree。
   - 量化 commit、diff、目录、最大文件、review/finding 数量，并核查 open findings 和缺失 live evidence。
5. **事实与推断分离**
   - “发生了什么”只采用 JSONL、Git、validator、ledger 和 review artifact。
   - “是否 overdesign、为什么难维护”列为工程判断，不把代码规模直接等同于破坏或垃圾代码。

模型路由说明：任务请求 GPT-5.5 / medium；当前子代理无法切换到该不可用路由，实际使用父任务继承的同级可用模型。远端历史 review 也多次明确记录“GPT-5.5 unavailable”，改用 GPT-5.6-sol medium。

## 会话一：`019fae66-d1a2-7f23-a806-9ed3742464e4`

### 原始目标与授权

原始 attachment 不是一个小任务，而是一次性授权自动执行 M1 到 M6：

- 建成私有三节点、24×L40S 的 Slurm batch platform；
- 三台机器只运行独立 single-node jobs，不做跨机 24-GPU distributed training；
- 正式 job 绑定 Git/submodule commit、container digest、dataset/model manifests；
- 实现 rsync staging、本地 cache、checkpoint local-first、真实 primary archive、worker-a 单写 fallback 和 split-brain-safe reconciliation；
- 只有 stop-class action、contradiction、AC change 或无法修复的 validator failure 才停。

证据：

- `/root/.codex/attachments/a46acd41-74b3-47b0-87e0-6682d6db6b5b/pasted-text-1.txt`
- `/data-1/code/l40s-slurm-cluster/docs/goals/slurm-platform-v1/plan.md`
- rollout：`/root/.codex/sessions/2026/07/29/rollout-2026-07-29T08-03-21-019fae66-d1a2-7f23-a806-9ed3742464e4.jsonl`

### 会话规模

在加入本次只读审计消息后，JSONL 统计为：

- 时间跨度：2026-07-29 15:03 UTC 至 2026-08-04 15:22 UTC；
- 49,692 条 JSONL 记录；
- 96,353,280 bytes；
- 33 条 user message；
- 902 条 assistant message；
- 15,048 条 tool call；
- 74 次 context compaction；
- 至少 278 条 subagent started/interacted/context-compacted 相关记录。

这是上下文失控的直接证据。74 次 compaction 后，agent 依赖 handoff、ledger 和自身生成的 review 文档维持连续性；这些工件减少了完全失忆，却也使“继续 Goal”越来越像维护 Goal framework 本身。

### 关键时间线

| 时间 | 事实 | 工程含义 |
|---|---|---|
| 2026-07-29 | 按 Plan v9 启动 M1；用户授权自动推进 M1–M6 | 一开始就把产品、infra、live rollout、storage failover 和最终验收装入一个 Goal |
| 2026-07-29 | M1 初始 47 tests 全绿，但 R-10 一次发现 7 个 blocking defects；随后进入 F-11…F-21 等多轮修复 | independent review 有真实价值，但 M1 contract 面快速膨胀 |
| 2026-07-29 至 07-30 | scanner、inventory、target lock、renderer、installer、receipt、process containment 等不断增加 adversarial controls | 安全机制成为主要开发对象 |
| 2026-07-30 | M1、M2 完成，进入 M3；first apply 超过 1800 秒，被外层 timeout 终止，未发布 apply receipt，产生 F-89 | 最关键的 live 操作在超时/receipt 设计上失效，现场状态一度未知 |
| 2026-07-30 至 08-03 | 围绕 F-89/F-90/F-96/F-97 构建 interrupted recovery、remote CAS、selector authority、inode/descriptor/witness 机制 | 从 Slurm bootstrap 进一步漂移到自研部署事务/恢复协议 |
| 2026-08-03 | F-97 通过 R-49；随后 F-98/F-99 围绕 operator docs 与 target-lock shell assignment 产生 R-50 至 R-58 多轮 review | 文档 checker 进入 CommonMark/Bash context 解析，出现典型 assurance-cost runaway |
| 2026-08-03 | M3 被 foreign GPU workload 阻塞后，Plan 允许 PRE-M4/PRE-M5 `OFFLINE_ONLY` work-conservation；相继实现并 review | 形式上受 Plan v10 允许，不是隐式越权；但在核心平台未可用时继续增加后续功能体量 |
| 2026-08-03 | 两组各三次 fresh audit 均发现 `foreign_gpu_workloads=34`，每次均 zero mutation；最后两组分别记录 blocked | 不变外部状态被反复采样、构建和提交，收益很低 |
| 2026-08-04 | 本次只读 prompt 恢复后，原会话承认应停止开发并开始审计 | resume 成功，但 TUI 输出不适合远程机器采集 |

### 当前阶段（事实）

当前权威状态来自 validator，而非 `status.md`：

- Plan validator：`PASS`
- Plan replay status：`READY`
- Plan version：10
- Plan SHA256：`eefc0b518440deae993c90edfa164dd0f4e36c7a7ff42e8b2e43a10c4d9a220f`
- Goal：`ACTIVE`
- current milestone：`M3`
- branch：`codex/slurm-platform-v1-implementation`
- HEAD：`330430e9b06d312b76c8610445372cb4f5253cb2`
- working tree：clean
- pending user decisions：0
- open：F-81、F-86（DEFERRED）、F-89；其中 F-89 是 live recovery/M3 主阻塞链的一部分

已完成的是 M1、M2，以及 PRE-M4/PRE-M5 的离线实现 review；未完成的是 M3、M4、M5、M6 和 final acceptance。

### 失败 gate 与缺失 evidence

已起作用的 gate：

- secret/inventory 边界；
- target-lock/Plan SHA/candidate binding；
- append-only runtime/findings ledger；
- independent review，且多次真实返回 FAIL；
- foreign GPU workload admission，六次均阻止了 live mutation；
- exact candidate、non-root build、reproducible bundle 等 gate。

缺失的最终 evidence：

- 没有成功完成三节点 Slurm bootstrap；
- 没有成功 Slurm query；
- 没有 Goal GPU job；
- 没有 24-GPU scheduling target 的 live acceptance；
- 没有真实 primary archive 成功证据；
- 没有真实 fallback/failback/split-brain drill；
- 没有 M3 completion，更没有 M4–M6 completion；
- 没有 final independent acceptance；
- 仓库没有 remote、PR、merge commit 或外部 CI delivery surface。

这使大量 “PASS” 必须按边界解读：R-60/R-62 等明确是 `OFFLINE_ONLY`，不能证明平台可用。

## 会话二：`019fc29a-4824-70a3-a177-356edf1c3e82`

### 原始请求如何变化

这条会话最初只要求回答：完成了什么、未完成什么、进度、原目标和偏离程度。随后用户要求找到 Goal 文件并生成 resume prompt，再明确输入 `/goal` 继续执行。因此它不是一开始就被授权继续编码，而是在审计后转为第二个执行入口。

关键变化：

1. 2026-08-02：只要求 resume 并评估进度/偏离；
2. 2026-08-03：用户要求找到 Goal 文件和启动 prompt；
3. 2026-08-03：用户提交 `/goal 继续执行现有 Goal slurm-platform-v1`；
4. 后续 Goal internal context 明确要求从 F-97 推进至 M3–M6；
5. 用户又发送“继续”和“我授权，继续”；
6. foreign workload 持续存在后，用户反复询问该如何授权、是否能继续离线开发。

所以这里存在两层问题：

- 用户确实后来给了继续授权，不能说 agent 完全越权；
- 但 workflow 把“帮我评估当前 Goal”很容易转化为“继续一个无上限、无 token budget 的永久 Goal”，缺少新的工程可行性审查和重新拆单 gate。

### 会话规模

- 时间跨度：2026-08-02 13:12 UTC 至 2026-08-04 15:22 UTC；
- 5,698 条 JSONL 记录；
- 11,454,593 bytes；
- 20 条 user message；
- 205 条 assistant message；
- 2,316 条 tool call；
- 7 次 context compaction；
- 至少 30 条 subagent started/interacted/context-compacted 相关记录。

Goal internal context 在 2026-08-03 已显示约 598k tokens，随后显示 4.15M、4.18M、4.42M、4.45M tokens，且 token budget 为 none / remaining unbounded。这是“长程目标没有资源预算”的直接证据。

### 第二会话暴露的额外问题

1. **审计与执行没有隔离**：最初的进度调研会话最终成为新的 `/goal` 执行会话。
2. **blocked resume 语义鼓励重复尝试**：三次 busy audit 后 Goal blocked；用户 resume 后又运行三次同类 audit，最终再次 blocked。
3. **用户无法基于产品结果判断授权**：用户多次问“为什么应该授权”“应该怎么做”，说明 ledger 和安全术语没有转化成清楚的产品决策界面。
4. **offline work-conservation 让体量继续增长**：GPU 被占用时，agent 依 Plan v10 完成 PRE-M4/PRE-M5；形式上合规，但使尚未 live 验证的后续层继续堆叠在不稳定的 M3 基础上。

## 代码与维护性审计

### 可量化事实

以 base `acc56b77f477807305346f87f2054bbccddd92c5` 到当前 HEAD 计算：

- 211 commits；
- 281 files changed；
- 83,740 insertions、21 deletions；
- commit 类型粗分：48 个 `docs(review)`、28 个 `fix`、3 个 `feat`、3 个 `test`、61 个其他 `docs`、68 个其他；
- `docs/` 新增 16,624 行；
- `src/` 新增 26,479 行；
- `scripts/` 新增 7,106 行；
- `tests/` 新增 29,875 行；
- reviews 目录有 136 个文件；
- runtime ledger 有 62 次 `REVIEW_REQUESTED`、51 次 `REVIEW_COMPLETED`、25 次 `RISK_NOTICE_RECORDED`、9 次 `PLAN_AMENDED`；
- findings ledger 有 680 条事件、103 个 finding ID，其中 102 个被分类为 `IN_SCOPE`。

最大 Python 文件包括：

- `scripts/install_production_runtime.py`：4,128 行；
- `src/l40s_slurm_cluster/transport.py`：3,047 行；
- `tests/test_production_runtime_installer.py`：3,035 行；
- `src/l40s_slurm_cluster/bootstrap.py`：2,268 行；
- `src/l40s_slurm_cluster/receipts.py`：2,079 行；
- `src/l40s_slurm_cluster/interrupted_recovery_manifest.py`：1,943 行。

代表性 churn：

- `c82b896`（selector descriptor authority）：仅 installer 和对应 tests 两个文件就有 3,166 insertions / 3,542 deletions；
- `82f4c3f`（PRE-M5 offline storage continuity）：23 个文件、3,828 insertions；
- `9850bec`：为了 target-lock 文档 fence，引入 CommonMark dependency 和 checker/tests；
- `330430e`：只记录 resumed busy gate 的单行 ledger commit。

### 事实：没有发现的破坏行为

本次只读审计没有发现以下证据：

- 格式化磁盘；
- 删除历史 checkpoint/dataset/model/source；
- 停止或清理 foreign GPU workload；
- 修改 firewall/Tailscale ACL；
- 公开暴露 Slurm/storage/SSH；
- 绕过 busy gate 去执行 live recovery；
- 当前 working tree 污染。

六次 busy audit 都记录 `remote_mutations=0`。因此不能把“代码非常复杂”直接写成“已经破坏生产”。

### 工程判断：高可信 overdesign 迹象

以下是推断，但有强证据支持：

1. **assurance-cost runaway**：M3 尚未完成，已有 62 次 review request、103 个 finding、136 个 review artifact。审查机制本身成为主要产出。
2. **单文件维护风险**：4,128 行 installer、3,047 行 transport、2,268 行 bootstrap 和多千行测试文件，已经超过普通 cold reviewer 可可靠掌握的范围。
3. **自研事务协议过深**：从一次 apply timeout 演化出 interrupted recovery、remote-live CAS、selector descriptor authority、inode anchor、witness、receipt schema 等多层协议。部分安全复杂度有必要，但整体已经接近另一个产品。
4. **F-99 是典型过度工程候选**：为保证两段 operator 文档里的 target-lock assignment 不被 Markdown/Bash context 绕过，经历 R-51–R-58 多轮 review，并引入 CommonMark 解析和大量 adversarial fixture。更简单的结构方案应是生成脚本/单一可执行配置，而不是把文档当 shell authority。
5. **finding 分类失去收敛作用**：103 个 finding 中 102 个 `IN_SCOPE`。当 AC 写得足够广，几乎任何新缺陷都能被解释为既有 scope，机器分类就不能阻止 Goal 扩张。
6. **状态源分裂**：`status.md` 最后更新 2026-08-02，仍描述旧 F-96 gate；当前 ledger 已到 F-102/R-62 和六次 busy audit。Plan 文件头静态写 `Plan status: DRAFT`，validator replay 却是 `READY`。机器 validator 没有把 cold-reader 状态一致性作为失败条件。
7. **本地自证闭环**：reviewer 确实独立于 implementer context，且多次给出真实 FAIL；但所有实现、review、ledger 和验收准备仍在同一主机、本地 branch、同一 agent 体系，没有 remote PR/CI/team owner 的外部交付门禁。

### “无用代码/垃圾代码”的审慎判断

仅凭本次证据，不能逐文件断言哪些 production module 永远无用，也不能把全部 83k 行称为垃圾代码。更准确的结论是：

- PRE-M4/PRE-M5 当前只通过 `OFFLINE_ONLY`，在 M3/M4/M5 live replay 前都属于**未兑现价值的库存**；
- review Markdown、重复 busy-gate commits、过期 `status.md` 和围绕文档 shell assignment 的复杂 checker，存在较高的低价值/维护负担；
- selector/recovery 代码确实解决了真实的 fail-closed 问题，但其复杂度和 churn 使正确性难以由团队长期维护；
- 只有后续按独立交付物做代码保留/删除评审，才能确认具体 dead code；当前没有运行 coverage/dependency reachability，因此不应编造文件级结论。

## 机器约束缺口

### 1. 缺少 Goal admission gate

现有 validator 检查 Plan 是否 READY，却不检查 Goal 是否应由一个执行单元承担。启动前应机器检查：

- milestone 数量；
- AC 数量和跨域数量；
- 是否同时包含产品开发、生产部署、数据迁移、灾备演练和最终验收；
- 预估 diff/commit/review/time budget；
- 是否能在一个 PR 内由一个 owner review。

超过阈值必须拒绝 `/goal`，要求先建立 PRD 和 issue DAG。

### 2. 缺少复杂度与变更预算

每个 issue/PR 应有机器预算：

- 最大新增 production LOC；
- 最大 touched modules；
- 最大单文件长度/复杂度；
- 最大 review rounds；
- 最大 finding 数；
- 最大 wall-clock/token budget。

超限不是自动“继续修”，而是 `SCOPE_REPLAN_REQUIRED`，要求人类决定拆分、替换设计或停止。

### 3. 缺少“真实能力先于后续层”的门禁

M3 未完成时，PRE-M4/PRE-M5 可以 conservation，但不应允许形成数千行长期库存。更严格的规则应是：每个 blocked milestone 只允许一个 bounded spike 或 interface stub；前序 live acceptance 未通过，后续功能 PR 不得合并。

### 4. 缺少外部状态 watcher

foreign workload 不变时不应每次 resume 都：构建新 candidate → 跑 48 reads → 写 receipt → 提交 ledger。应由一个只读 watcher 监测明确条件（例如 foreign workload count 归零），状态变化时才唤醒 Goal；unchanged 状态不创建 commit。

### 5. 缺少状态单一真相生成器

`status.md` 和 Plan header 不应人工维护。应从 runtime ledger 生成只读 current-status artifact，并在 CI 检查：

- Plan header/replay status 一致；
- `status.md` 的 HEAD、open findings、latest review、next gate 与 validator 一致；
- 过期即红，不允许冷读者看到多个互相冲突的状态源。

### 6. 缺少团队交付 gate

本地 reviewer PASS 不能代替：

- remote issue；
- branch protection；
- CI；
- PR diff；
- CODEOWNERS/指定人类 owner；
- 至少一名人类批准；
- merge 后部署 gate。

Linear/Jira 可以管理拆单，但真正约束代码的是 GitHub/GitLab branch protection、required checks、CODEOWNERS 和部署环境 approvals。项目管理工具不能替代 repo gate。

### 7. 缺少“替换设计”而非无限增补的触发器

连续两轮 review failure 后，当前 convergence review 仍可能得出“继续在原系统上加 architecture”。新的机器规则应比较：

- 修补当前实现的预计复杂度；
- 删除/替换为成熟组件或更小设计的成本；
- 失败设计留下的代码是否应删除。

当同一模块三次大幅重写或 churn 超限，默认停止增补，进入 ADR + replace/delete review。

## 建议的工程任务拆解

不要再以一个 `/goal` 自动执行 M1–M6。保留 PRD 作为产品级目标，但执行必须拆为可单独关闭的 issue/PR。

### Phase 0：停止扩张与可维护性审计

交付物：一份保留/删除清单，不写新功能。

- 冻结当前 branch；
- 建立 remote backup 和 PR；
- 生成 module dependency graph、coverage、dead-code/reachability、complexity 和 file-size 报告；
- 将 `status.md` 改为 ledger 生成物；
- 对 F-99 docs checker、selector/recovery state machine 做 replace/delete ADR；
- 明确哪些 PRE-M4/PRE-M5 代码保留为 future branch，哪些从 M3 PR 中移出。

验收：人类 owner 批准 ADR 与删除清单；不以 test count 代替批准。

### T1：M3 bootstrap/recovery 最小 PR

只验证 AC-03/AC-04 和 F-89 收口：

- 三节点 bootstrap；
- Slurm health/query；
- 3×8 GPU inventory；
- idempotent second apply；
- bounded rollback/recovery。

明确不包含 job provenance、storage cache、primary/fallback。foreign workload 未退出时只由 watcher 等待，不继续开发其他大模块。

### T2：immutable submission/container PR

只验证 AC-05/AC-06/AC-08/AC-09：

- commit/image/data/model binding；
- container mount/privilege contract；
- 三个独立 single-node jobs；
- job-local Ray 和 cancellation cleanup。

复用 PRE-M4 的代码前必须重新做 diff/复杂度审查，并在已经可用的 Slurm 集群上 live replay。

### T3：cache staging PR

只验证 AC-07：manifest、rsync staging、cache hit/corruption/retry。它不接触 primary failover 状态机。

### T4：live primary archive PR

只验证 AC-10：local-first checkpoint、真实 primary archive、checksum/inventory receipt。不得用 disposable backend 冒充验收。

### T5：fallback/failback PR

只验证 AC-11/AC-12：单写 authority、capacity admission、primary outage、fallback、reconciliation、dual-outage refusal。该 PR 风险最高，必须单独设计 review 和 live maintenance window。

### T6：operator handoff 与 final acceptance

只在 T1–T5 全部 merge 且 live evidence 可复现后开始：

- AC-13 runbook；
- cold-reader drill；
- 全 AC evidence index；
- independent final acceptance。

### 每个 issue/PR 的统一模板

每项必须机器可读地声明：

- user-visible outcome；
- in scope / out of scope；
- base commit；
- 最大 diff 和 complexity budget；
- 必须变红的 negative control；
- required CI checks；
- live environment 和 maintenance window；
- rollback；
- code owner；
- “本 PR 不证明什么”；
- 完成后是否删除 spike/prototype。

## 证据索引与复现命令

### Host / rollout

```bash
ssh -o BatchMode=yes -o RequestTTY=no l40s-3-public \
  'printf "host=%s user=%s home=%s\n" "$(hostname)" "$(id -un)" "$HOME"'

find /root/.codex -type f -name '*019fae66-d1a2-7f23-a806-9ed3742464e4*.jsonl'
find /root/.codex -type f -name '*019fc29a-4824-70a3-a177-356edf1c3e82*.jsonl'
```

### Goal authority

```bash
cd /data-1/code/l40s-slurm-cluster
/root/.local/bin/goal-plan-runtime validate-plan docs/goals/slurm-platform-v1
/root/.local/bin/goal-plan-runtime validate-runtime docs/goals/slurm-platform-v1
sha256sum docs/goals/slurm-platform-v1/plan.md
git status --short --branch
git rev-parse HEAD
```

### 规模

```bash
base=acc56b77f477807305346f87f2054bbccddd92c5
git rev-list --count "$base"..HEAD
git diff --shortstat "$base"..HEAD
git diff --numstat "$base"..HEAD
find src scripts tests -type f -name '*.py' -print0 | xargs -0 wc -l | sort -nr
jq -s 'group_by(.event) | map({event: .[0].event, count: length})' \
  docs/goals/slurm-platform-v1/runtime.jsonl
```

### 关键路径

- Plan：`/data-1/code/l40s-slurm-cluster/docs/goals/slurm-platform-v1/plan.md`
- Runtime：`/data-1/code/l40s-slurm-cluster/docs/goals/slurm-platform-v1/runtime.jsonl`
- Findings：`/data-1/code/l40s-slurm-cluster/docs/goals/slurm-platform-v1/findings.jsonl`
- Status：`/data-1/code/l40s-slurm-cluster/status.md`
- Reviews：`/data-1/code/l40s-slurm-cluster/docs/goals/slurm-platform-v1/reviews/`
- Installer：`/data-1/code/l40s-slurm-cluster/scripts/install_production_runtime.py`
- Transport：`/data-1/code/l40s-slurm-cluster/src/l40s_slurm_cluster/transport.py`
- Bootstrap：`/data-1/code/l40s-slurm-cluster/src/l40s_slurm_cluster/bootstrap.py`
- Receipts：`/data-1/code/l40s-slurm-cluster/src/l40s_slurm_cluster/receipts.py`
- Interrupted recovery：`/data-1/code/l40s-slurm-cluster/src/l40s_slurm_cluster/interrupted_recovery_manifest.py`

## 审计边界

- 本报告没有运行 full test suite、live Slurm query、GPU probe、storage probe 或 deployment；这些会改变审计成本或触及当前 blocked surface。
- 当前 validator 与 Git/ledger 状态已实时核验。
- 代码质量判断来自 diff、文件规模、review/finding history 和已存在 reviewer evidence；没有逐行审完 83k 新增代码。
- 因此，本报告可以确定流程失衡和维护风险，但不能声称每个 production module 都错误，也不能声称生产环境已被破坏。
