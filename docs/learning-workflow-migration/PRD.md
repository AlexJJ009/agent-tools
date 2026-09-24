# 教学与学术写作工作流的渐进迁移 PRD

状态：供评审，尚未实施。版本：0.1。日期：2026-09-24。

本次交付是迁移需求、验收标准和测试输入。它不表示已有 skill 完成迁移，也不授权批量安装、远程实验、论文提交或博客发布。PRD 正文用中文解释；计划维护的 skill 指令、描述、字段和操作规则使用英文，面向用户的实际材料跟随用户语言与文体。

## 1. 要解决的问题与交付目标

用户已有有效的教学重建措辞和开发验收流程。当前需要让这些能力适用于论文阅读、真实论文写作以及开发中的学习，同时避免开发请求误触发教学，并保留已有行为。

目前已观察到三个具体问题：

1. 当前教学路由按子串匹配。直接调用时，“修复 Docker healthcheck”进入学习检查，“修复 citation 字段”进入论文元数据处理，“不要安排练习题，直接修复”仍进入学习检查。原有 5 个触发测试方法全部通过，说明已有测试尚未覆盖这些反例。这是函数级观察，不是原生会话误触发的证明。[探测与原始输出](../work-reports/20260920T030723Z-academic-writing-and-research-learning-e68e93d3/revisions/20260924-portable-teaching-boundary/router-probes.json)
2. 教学成文组件要求教学状态、前置关系和练习；真实 manuscript 起草或修改不能把这些作为前提。学术写作应同时支持 ReadPapers 的练习 playground 和论文项目的实际稿件。
3. 当前教学记录和材料适配包含 Zotero、ZotLit、Obsidian 专属要求；通用代码/架构学习不应依赖这些环境。跨项目学习成果则需要可追溯、可找回，不能为统一存储而复制整套原始资料。

本次后续实施应交付：可复用的教学与学术写作能力、Agent 主导的任务路由、有限且可观察的脚本/Hook 检查、兼容迁移工具与证据、轻量的成果索引。以下 R 编号是需求来源分类，AC 编号是验收项；完整映射在 [checklist.yaml](checklist.yaml)。

| 需求 | 用户要求 | 本 PRD 的具体回应 |
|---|---|---|
| R01 | 分类应理解上下文，脚本未必能独立胜任 | Main Agent 负责 semantic routing；脚本不做任意自然语言分类 |
| R02 | 开发保持 hands-off，不能突然教学或写论文 | 活动与能力分开；否定约束优先；混合请求按已授权阶段执行 |
| R03 | 保留有效用语，谨慎迁移并局部重构 | 保存基线；先改入口，后改依赖；保留教学行为与旧记录兼容 |
| R04 | 使用精准的领域词汇 | 每个术语绑定适用场景、动作、产物与可观察标准，不以术语数量计分 |
| R05 | skill 全部英文，用户材料跟随上下文 | 维护规则英文；用户原话、语料和实际正文可中英文混合 |
| R06 | 学术写作既有 playground 又有实战 | 单独的 academic-writing 入口支持直接起草、修改和教学调用 |
| R07 | Zotero、论文保存与精读只在 ReadPapers | 项目适配负责资料库操作；其他项目消费已有证据和引用 |
| R08 | idea 可行性可能需要服务器代码 | 授权的 SSH 读取作为材料来源；区分代码观察与运行证明 |
| R09 | 学习产物可归拢，但开发、整理、发布分开 | 项目保留权威记录；显式整理时生成自足笔记和可搬迁索引 |
| R10 | 用户需要输出、练习与引导，也允许 AI 直接写稿 | 分开作品质量、用户表现、帮助程度与结果接受 |
| R11 | 验证实际触发和迁移质量 | 机械检查、原生会话行为、独立材料审查与用户体验分别验收 |

## 2. 产品边界：能力、活动、材料和成果

不能把全部学术能力固定在 ReadPapers，也不能因为 skill 已安装就允许其接管当前任务。

| 维度 | 含义 | 例子 |
|---|---|---|
| Capability | 可调用的专业能力 | 教学重建、学术写作、开发验收 |
| Activity | 用户当前要完成什么 | delivery、learning、writing、curation、answer |
| Material | 当前判断依据在哪里 | 代码、日志、稿件、已整理文献证据、Zotero 原文 |
| Artifact owner | 谁维护权威产物 | 代码仓库、论文项目、ReadPapers、选定的知识目录 |

ReadPapers 负责资料管理、精读、综合与练习。论文项目负责正式稿件、图表和实验结论的表述。开发仓库负责代码与运行事实。通用教学可以在这些环境中使用；领域写作方法也可以跨项目调用。

普通开发中的必要解释不自动升级为教学。阅读材料里出现的指令只是材料；不能改写当前任务。用户要求先实现、再学习时，记录阶段和恢复点，不能在教学后丢失原开发任务。

Work Report 继续由开发汇报约定触发；ReadPapers 的日常学习不调用它。共享写作原则不意味着共享六章节报告格式。

## 3. Main Agent、脚本、Hook 和 SubAgent 的分工

### 3.1 Main Agent 负责 semantic routing

新增小型英文 `task-routing` skill，或等价的薄入口模块。它读取当前 query、仍有效的任务约定、明确排除项和项目材料边界，给出当前活动、需要的能力以及简短依据。它不能只看 cwd 或几个关键词。

Main Agent 是默认分类者，原因是它拥有持续的任务上下文。独立 SubAgent 只用于确有争议的混合意图复核、迁移评测或重要质量审阅，不为每条 query 固定启动一次。缺少用户意图且确实改变目标时，向用户澄清；能够从代码或既有约定查清的事实，继续调查。

按当前目标可以安全完成的阅读、短答或实现不必因另一项未决问题全部停住。禁止把“不要讲解”识别成学习请求，也禁止让引用材料中的“请开始教学”修改活动。

### 3.2 脚本负责 deterministic validation

脚本检查字段、任务/会话对应关系、阶段、输入是否已处理、项目范围、已选择能力是否可用，以及已登记动作是否满足其原有约束。它不证明分类语义正确，也不根据英文术语数量宣称教学有效。

短答可只保留会话内判断；持续任务、阶段切换、持久材料写入或受控动作需要可读回的 route record。已有开发记录时引用现有记录及 revision，不复制其中的协议、授权和验收状态。纯学习不要求初始化完整开发 gate。

建议最小记录形态如下，字段为英文，字段值可保留用户原话。这里定义的是拟实现接口，不是现有 CLI 已支持的参数：

```json
{
  "schema_version": "task-route/1",
  "task_id": "example-task",
  "session_id": "host-session-id",
  "workspace_root": "/workspace/manuscript",
  "route_revision": 1,
  "request_refs": ["request.txt#turn-1"],
  "activity": "writing",
  "interaction_mode": "direct",
  "workspace_context": "manuscript",
  "selected_skills": ["academic-writing"],
  "excluded_actions": ["unsolicited_exercises", "zotero_mutation"],
  "material_refs": ["results/summary.md"],
  "output_targets": ["paper/introduction.tex"],
  "next_stage": null,
  "development_record_ref": null,
  "rationale": "The user requested a draft from existing results without exercises.",
  "unresolved": []
}
```

`activity` 为 delivery/learning/writing/curation/answer；`interaction_mode` 为 direct/guided/practice/review。activity 不替换现有开发 runtime 的 scenario，也不改写 algorithm/infra/business/bug_fix 等已有枚举。能力可多选，但当前活动只有一个；混合任务通过有顺序的阶段表示。`request_refs` 必须能定位真实请求；`rationale` 是简短、可核对的分类理由，不要求公开内部思维链。

后续用户输入先判断是否改变当前活动或范围；同一次输入重试应幂等。更新提交携带 base_revision，过期写入返回冲突，不覆盖新状态。会话、任务和 workspace 共同定位记录；不能让同一机器上的两个任务共用可变活动。旧分类不能无条件覆盖新约束。记录丢失或过期时重建必要上下文；只阻止依赖缺失信息的受控动作，保留不依赖它的阅读和答复。路由自身的读取、分类记录写入和安全恢复操作不得被其 pending 状态循环阻塞。

### 3.3 Hook 负责生命周期上的触发和回读

当前可复用模式位于 `agent_workflow/hooks.py`。代码声明 SessionStart、UserPromptSubmit、PreToolUse、PostToolUse、Stop；它需要显式绑定 schema-2 开发记录，未绑定时不工作，也不做语义分类。这是现有实现事实；新学习入口仍需单独实现适配。

| 事件 | 迁移后的用途 | 必须保留的限制 |
|---|---|---|
| SessionStart | 恢复已存在的任务/路由，注入薄入口提示 | 无记录时不强建重型记录 |
| UserPromptSubmit | 标记新输入，提醒 Main 分类或保持当前目标 | Hook 不另起模型作隐式分类，不覆盖用户原话 |
| PreToolUse | 对可识别且已纳入范围的动作校验当前记录 | 不声称能拦截任意 shell、工具或自然语言输出 |
| PostToolUse | 关联实际工具结果，记录观察 | 成功退出不自动等于验收或用户理解 |
| Stop | 有约定的产物/阶段结束时检查是否遗留必要工作 | 无义务时不制造汇报，不形成无限继续循环 |

安装配置不等于宿主已信任或启用 Hook。每个宣称支持的宿主必须留下真实事件和实际调用轨迹；工具名与事件格式要按宿主适配。现有实现只识别部分 Bash 命令，不能照搬后宣称覆盖 exec_command、MCP 或所有文件写入。

Hook 关闭或缺事件时，已登记高风险动作继续由原执行入口校验；普通学习退回 skill 提示与必要的显式检查，并标明自动触发覆盖缺口。聊天内容的语义误触发依赖真实会话评测和用户纠正，不能伪装成脚本可以绝对阻止。

## 4. 可复用能力与项目适配

### 4.1 保留通用教学，单独支持学术写作

保留 teaching-reconstruction 的已有主干：理解读者当前模型、明确前置知识、解释动机、证据定位、重建与迁移、按请求形成材料。保留 guided-direct 的直接讲解，不能强迫每个用户回答背景问卷。

新增 `academic-writing`，以可读的来源/结果/稿件作为输入，支持：

- draft：完整或局部稿件起草、proposal 备选和建议；
- revise：定位到段落或句子的修改及理由；
- argument-review：主张、证据、限制和其他解释的核查；
- teaching recipe：由教学编排调用，分析范文、安排尝试、提供针对性反馈。

前三项不以 learner checks、知识 DAG 或“用户已掌握”为前提。缺数据时可以给条件式 proposal 或论证框架，但不能补造实验结果、引用或创新性证明。教学模式保留用户原稿和帮助程度，用户明确要范文时允许直接给出。

learning-artifact-compiler 继续负责教程、博客稿和学习笔记。形成教学成品的前提不能被误用于所有写作任务；也不能因用户要求“博客发布”就自行调用外部发布工具。

### 4.2 材料访问与知识归属

ReadPapers 才能激活 Zotero 管理、论文入库、正式精读与 ZotLit 更新。论文项目可以消费已有引用、文献证据和稿件材料；需要新增入库或完整精读时生成指向 ReadPapers 的具体待办，不能自动跨任务创建新对话或在开发仓库复制论文库。

授权的 SSH 只读代码可以服务 idea 可行性或教学。记录仓库、revision、路径和实际读取范围；无法访问时明确缺口，不推测远端内容。代码阅读不是 smoke test，更不是正式训练或生产授权。后续执行继续受原开发约定约束。

用户生成的学习笔记不自动作为外部原文导入 Zotero。项目内先保留上下文；用户请求整理时才产生自足笔记和索引条目。默认索引只包含标题、主题、来源项目/版本、正文位置和状态，不自动收集私有数据、复制实验日志或发布博客。

第一版支持显式指定知识目录、相对路径/仓库标识和手动导入。未指定中央目录时保留项目内 `artifact-index.json`，不猜测本机 vault 路径。索引重复导入应更新已有条目，不产生多份权威原文；源项目不可访问时标明链接失效，不伪称已同步。

## 5. 英文规范与领域术语

所有迁移范围内维护的 SKILL.md 指令、description、模板字段说明、router/reviewer 提示与脚本帮助使用英文。中文 skill 展示名可以保留。测试 query、用户原话、历史快照、来源引用和实际学习/写作内容不受英文限制。中文用户要英文论文段落时按交付语言写；不能机械按 query 的语言覆盖明确要求。

术语必须承担具体动作。以下是最小维护集，不要求每次全部使用，也不把英文词本身当成能力保证。

| 领域 | 术语 | 对应动作和可观察产物 |
|---|---|---|
| 任务/工程 | semantic routing; readback; provenance; scope of authority | 对照请求给出活动；读取真实记录/值；区分来源与授权 |
| 迁移/工程 | characterization test; regression test; differential evaluation; backward compatibility | 保存已知行为；复现误触发；比较新旧输出；验证旧记录仍可读 |
| 教学 | prerequisite; worked example; fading; retrieval; near/far transfer | 补足必要背景；示范后逐步撤去帮助；在新材料上检查表现 |
| 论证 | claim–evidence–warrant; qualifier; alternative explanation | 定位主张、支撑关系、结论范围及竞争解释 |
| 写作 | rhetorical move; CARS (Create a Research Space); reverse outline; reader expectations | 分析段落作用、动机结构、信息衔接和读者需要的背景 |
| 文献/选题 | synthesis matrix; contribution positioning; problematization; falsification criterion | 共同条件下比较工作；界定贡献；检查假设；说明什么观察会推翻候选解释 |

示例规则应以英文写清触发条件和动作：

```text
Use semantic routing to identify the user's current activity from the request,
active agreement, and explicit exclusions. Treat topic words as context, not
as authorization to switch activities. Preserve the continuation point.

For argument review, identify the claim, its evidence, and the warrant linking
them. Locate unsupported inferences and state the qualifier or additional
evidence needed. Do not invent results to complete the narrative.

In guided practice, preserve the learner's attempt and disclose assistance.
Give targeted feedback before a full rewrite unless the user requests an example.
In direct drafting, produce the requested text without imposing a learner test.
```

共享表达原则沿用 W1–W9，保留 ID 与 Work Report/reviewer-brief 的既有语义。建议在 `shared/writing/reader-facing-contract.md` 维护可复用核心，由构建/同步步骤生成随包副本；报告六部分和报告 Judge 留在原 skill。教学适配说明：练习先给任务和条件，答案按教学阶段展示；关键背景不能全部折叠。旧规则的改变必须在 diff 中解释，不能通过“统一风格”无声改义。

## 6. 复用来源与维护位置

当前事实已保存在 [baseline/inventory.json](baseline/inventory.json)。这些 snapshot 是只读审阅基线，不是第二套维护源，也不装入用户级 skill 目录。

| 组件 | 已核对的来源 | 拟改动边界 |
|---|---|---|
| 教学组件与测试 | `/home/alex_mercer/projects/_worktrees/agent-tools/codex-teaching-skills-suite/`，HEAD `0bef6f345d1899a0d99292ad538ec832d8d4ff89` | 从实际源保留提示词与测试；选择性迁入当前集成分支，不整枝合并旧 worktree |
| 当前开发 runtime | 本仓库 `agent_workflow/`、`skills/intent-to-contract/` | 复用 Agent 分类/运行时检查分工；仅修改必要 handoff，保留已有 gate |
| read-paper | `/home/alex_mercer/projects/.claude/skills/read-paper/`；ReadPapers 与用户级路径当前指向它 | 缩小激活范围与适配依赖；不重写 Zotero 阅读实现，不清空历史资料 |
| W1–W9 | `skills/work-report/references/writing-contract.md`、同步脚本和 reviewer-brief 副本 | 共享原则与体裁规则分开；保留报告旧测试与调用行为 |
| 教学/写作调研 | [现有报告](/home/alex_mercer/projects/obsidian-vault/read_papers/insights/academic-writing-and-research-idea-learning.md)；跨机器时由 README 定位项目资料 | 复用术语、例子、来源边界，不另造无依据的教学法 |

实施后的通用 skill 维护源拟为本仓库 `skills/`；测试在 `tests/`；共享规则在 `shared/writing/`。当前 main 尚无教学组件，不能假定改 main 同名文件就会更新安装版本。实现前重新读取安装链接和源 HEAD，若与基线不同先分析差异。

已调研外部方法按固定版本选取小片段和结构，不复制完整重型流程。复制时保留许可及归属，新增网络内容需另行核验。

| 来源 | 可复用部分 | 版本与本地证据 |
|---|---|---|
| [K-Dense scientific-writer](https://github.com/K-Dense-AI/claude-scientific-writer/tree/0c7260603be3de4dd5161565ab92e85b31c45eb5) | claim/evidence 对应、定位反馈、未核实状态 | MIT；`../work-reports/20260920T030723Z-academic-writing-and-research-learning-e68e93d3/community/snapshots/kdense-scientific-writing-SKILL.md` |
| [EvoSkills](https://github.com/EvoScientist/EvoSkills/tree/7dde27cda0ae57b863a371175275db8eaa02dcb2) | challenge–insight 关系表示 | Apache-2.0；同目录 `evoskills-research-ideation-SKILL.md`；不要求默认 30–50 篇或多角色竞赛 |
| [claude-scholar](https://github.com/Galaxy-Dawn/claude-scholar/tree/6ed46dac03191c7a734f49ed48b41195012098ff) | research question、证据缺口、反证条件与最小下一步 | MIT；同目录 `claude-scholar-research-ideation-SKILL.md` |

## 7. 渐进迁移与文件约定

### M0：保全基线与隔离候选

保存安装目标、源 revision、核心 prompt、旧记录 fixture 和原生行为样例。基线 prompt 已保存，但历史“用户喜欢的讲解”仅有调研样本，实施者仍需选择有真实用户反馈的代表例，不得冒充已完成人体学习试验。

在隔离 worktree/临时用户 profile 验证候选；不改正在使用的 symlink 或全局 Hook。遵循已有 target guard。所有 installer/helper 写入前先执行 `scripts/codex_target_guard.py`；只对当前指定目标操作，不推送 PHAI 或其他机器。

### M1：入口与边界

Main 语义分类；旧关键词路由不再作为最终决策者。保留必要兼容入口，但不能让旧 fallback 把明确否定的开发请求送进教学。接入最低限度的记录检查、项目范围和原生事件；保留当前开发授权与报告触发规则。

### M2：写作入口与材料适配

加入 academic-writing；共享领域方法，拆开 direct drafting 与 guided practice。把 Zotero/Obsidian 特有依赖收回 ReadPapers 适配。保留旧教学 v1 记录读入，不批量重写历史笔记；新导出格式若变更需版本化并提供显式转换与兼容测试。

### M3：整理、质量对照与候选安装

支持显式 curation 和可搬迁索引。完成原生触发、同题材料对照、独立代码审查和用户小范围体验，再按授权激活单一目标。安装路径搬迁后仍可调用，foreign Hook 配置保留；回退只恢复本次管理范围，不覆盖用户后来新增的设置。其余机器安装为后续单独范围。

### 记录位置

纯学习/写作持续任务默认记录到当前项目：

```text
docs/learning-workflow/records/YYYY-MM-DD/YYYYMMDDTHHMMSSZ-<slug>-<shortid>/
  request.txt
  routing.json
  task.md
  materials.json             # only when durable material references are needed
  learning.json              # only for learner attempts/feedback observations
  artifact-index.json        # only for a requested curation operation
  evidence/                 # only actual verification/review output
```

日期与时间以 UTC 生成；slug/字段使用英文，内容允许中文。每个任务一个 record，后续阶段原地更新，不为每个 turn 建目录。已有开发记录时复用其任务目录，通过一份 routing sidecar 引用 canonical revision，不另建第二套 checklist。

ReadPapers 的学习正文继续进入现有 `notes/`/`insights/`，formal manuscript 继续位于论文项目；上述目录只是工作记录，不是第二份稿件库。项目等价记录可复用，但需在 task.md 明确实际路径。短答不要求持久化这些文件。

## 8. 验收方法与完成条件

完整标准在 [checklist.yaml](checklist.yaml)，可复现请求在 [validation-cases.json](validation-cases.json)。当前所有实现项保持 `not_run`；本次文档一致性检查或独立 PRD 审阅不能把实现项打勾。

写作与精读用例使用 [fixtures/README.md](fixtures/README.md) 指定的固定材料包与 SHA-256 清单。这些是明确标注的合成材料，不是已发表论文或本轮实际实验；其用途是固定比较条件和证据边界。实际 run manifest 记录所用材料 digest、候选版本与宿主。T06 必须读取真实仓库附件，不能把附件指令搬进用户 query；T30 单独演示过期 revision 被拒绝、受控入口阻止未处理输入和分类恢复。

验收分三层：

1. **机械验证**：schema、旧记录兼容、路径范围、幂等、失效与 Hook/入口检查。对将复用的检查至少演示一次有意失败；不能只观察绿灯。
2. **真实调用验证**：隔离 Main Agent 从自然 query 启动，不预先告诉它应加载哪个 skill。保存实际 skill 读取/调用、工具动作、路由记录及前后文件清单；来源正文中的英文术语不能当作加载证据。声明支持的宿主分别验证。分类者模型/版本、次数、延迟和额外调用数一并记录。
3. **材料与学习验证**：独立读者先看实际产物及读者任务，再核对来源与原请求；比较背景充分性、论证、来源边界、语言和用户输出空间。用户反馈单独记录；作品通过不等于学习者掌握。

固定测试集全部运行；按 execution_kind 分别使用原生会话、适配集成或安装测试，不把每个机械案例都变成整套教学任务。`critical_negative` 用例每例至少 3 次独立新会话，出现一次禁止动作即阻止该目标激活。另取至少 6 条未见过的改写/组合请求作为 holdout，并报告选择方式。次数和 holdout 是本 PRD 的验收设计，不是统计可靠性或泛化证明。这是本次迁移的发布验证成本，不是日常每个 query 都要跑的流程。

不规定任意性能分数。报告单次/累计时延与模型调用，默认分类不能新增常驻调度器或固定额外模型请求。简单 bug fix 不应为教学而等待练习、启动文献检索或生成教学文件。性能结论仅覆盖实际测过的宿主和样本。

完成条件：所有 required AC 有当前候选绑定的实际证据；独立代码/安装审查无阻塞项；用户体验项有真实反馈；受影响旧流程通过回归。人工只需 AC-21 的两个代表性材料与其重点问题，不要求逐项手审机械检查。未测宿主、不可用远程材料和未完成体验须保留 pending/blocked，不能用模拟通过替代。

## 9. 范围限制与未证明事项

- 不增加中央任务调度服务、常驻分类模型、admission webhook 或大批 manifest。
- 不改 Coder 的实现方式，不重做开发验收框架；仅改与学习/写作 handoff 有关的必要部分。
- 不建设自动云同步、博客发布系统或跨机器学习画像服务；第一版只有显式整理与索引。
- 不宣称英文术语能稳定解锁隐藏能力；以真实行为、文章质量和用户表现评价。
- 不宣称 Hooks 覆盖任意工具或能强制模型内部遵守分类；披露被测边界。
- 不以论文叙事顺序证明作者真实发现历史，不把检索不到等同于研究空白，不把读代码等同于实验有效。

这份 PRD 的新增模块名、默认记录路径、最小重复次数和共享规则维护位置属于设计建议，已明确写出，便于评审；用户确认 PRD 前不得把它们当作已经安装或已验收的事实。
