# 结束与定时汇报运行时（v2）

本页用于未来汇报约定、中途抽检后续行，或已登记任务的到期/结束检查。独立立即汇报（无继续任务要求）与报告后的普通问答不需要注册。

## 注册约定

1. 保存用户原始提示词；若来自 UserPromptSubmit，用 JSON 读取 pending 的 `prompt` 并按 UTF-8 原样写出，不转录或规范化换行。runtime 和报告工具都按原始字节计算摘要；CRLF 与 LF 不相同。
2. 先实际委派 intent Judge，再根据判定选择登记方式。普通问答／非当前约定不需要初始化报告目录。
3. `none`、`needs_clarification`、`deferred` 可直接调用，不传 `--task-dir`：

```text
python3 report_runtime.py register --workspace <repo> \
  --request <request.txt> --decision <intent.json> --session-id <真实UUID>
```

这条路径校验原文、Judge 格式、引文和匹配的 pending，保存处理记录后解除候选提醒；不创建报告、收据或已完成状态。`deferred` 保留未来里程碑约定，并明确尚未配置自动触发；Main 在原工作状态中保留要求，到业务里程碑实际完成时生成 final 报告。`needs_clarification` 只对真正缺失的信息澄清一次，普通问题照常回答，不要求用户阅读或批准报告。

4. 只有 `confirmed` 才用 `report_tool.py init --record-only` 建立上下文，然后把真实 Judge JSON 传给 register，增加 `--task-dir <task-dir>`。同一约定复用目录；已有不同活动约定时，临时汇报另建目录，用 `--state` 引用原 working-state，不取消原义务。正式报告在 register 成功之后再 init。

默认报告目录是项目 `docs/work-reports/`，工具维护本地 Git 排除。实验日志／模型产物的外置目录不自动成为报告目录；只有用户明确指定报告位置时才传 `--output-root`。没有初始化报告的需要时，不为清除候选而建立目录或要求用户批准 Git 忽略规则。

登记失败不代表 Judge 没执行，也不代表报告已交付。已校验 Judge 后的登记错误保留在 pending 诊断记录中，Stop 至多给一次具体原因和恢复提示，不重复输出“Judge 尚未执行”。不要通过猴子补丁、伪造 context、删状态文件或转换原文换行来让登记通过。未能登记的自动保障必须明确标为未就绪；可推进的原任务继续执行。

session-id 必须使用 hook 上下文或 pending JSON 中的真实 session UUID，不能写 `current-session` 等占位。运行时会拒绝占位或与待审原文不匹配的会话绑定。

当前结束语义是注册后 Main 的下一次正常 Stop（本轮最终回复前）。Stop 不表示项目、训练或所有后台作业完成。明确的跨轮业务里程碑用 deferred 记录，不缩成每轮回复前汇报；也不把后续普通问答变成新义务。

正式批次必须在 register 成功之后重新 init：前面的 `init --record-only` 只为登记提供上下文。即使先前已生成 report.md 占位，也不能复用其早于 registered_at 的快照；需同一 task-dir 新建 `--kind progress` 批次再写报告。脚本的新鲜度检查不因这是中途抽检而放宽。

## 中途抽检与续行

约定 Judge 输出 `resume_after_report=true` 时，登记独立的 `interim` 义务，使用一次 `progress` 报告；无结束/周期要求时 `on_end=false`、`interval_seconds=null`。旧版 intent 未提供这个字段时按 false 处理。中途报告不得关闭其他任务的结束或周期约定。

Main 在报告前保存原任务目标、当前执行点和具体下一步。PostToolUse 首次核验中途交付收据后，会提示实际报告链接与立即交付动作；同一义务只提醒一次，不能把链接拖到原任务的最终回复。报告通过 check/Judge/finalize 后，在 commentary 交付链接，随后继续原任务，直到实际完成、需要用户输入或用户取消。只有后台进程仍在运行不算 Main 已续行。

Stop 门禁核验新鲜的 progress 收据；没有收据时沿用最多两次补报。收据有效后，如果尚未观察到报告之外的后续工具活动，则阻止一次 Stop，要求恢复原任务，不重新生成报告。这是一次性的续行提醒，不是能够证明业务进展或保证长程运行的调度器。工具活动检测只是减少重复提醒，不能识别任意工具调用的业务价值；独立验收必须检查具体原任务动作。

中途义务消费后不因后续问答或旧报告变化而重开。用户 Interrupt/cancel 仍然优先；真实阻塞应明确报告，不为了满足提醒制造无关动作。未加载/信任 hooks 的客户端只具备 Skill 流程约束，不能声称有 Stop 兜底。

## 结束前检查

安装器 `scripts/install_work_report_hooks.py` 在当前用户的 `.codex/hooks.json` 合并五个事件处理器，保留其他 hook，不修改模型、认证、CC Switch 或 `hooks.state`。运行前先由 Codex 原生 `/hooks` 审阅并信任定义；文件存在/安装check通过不代表信任已激活。

- UserPromptSubmit：以“汇报/报告+时机”做保守候选捕获，交由真实约定 Judge 判断。匹配器不是完整自然语言理解，隐喻式表达或未加载/未信任的 hook 不能声称必捕获。
- SessionStart/PostToolUse：恢复或提示到期状态，供 Main 在工具边界记录/补报。
- Stop：未处理的约定候选或未满足的报告义务，会产生 Main 同对话的续行要求。存在新鲜、匹配、重新核验通过的 `delivery.json` 才满足义务。每个义务最多两次续行，超限明确记录失败并显示警告，不无限阻塞。
- Interrupt：尊重用户停止，取消当前会话的汇报义务，不自动恢复被停止的业务工作。

Main 收到补报要求后，使用同一 task-dir 新建相应 `final` 或 `progress` 批次，冻结最新工作状态，生成完整报告，经过报告 Judge，再 finalize。`delivery.json` 的生成时间、任务、原文摘要、报告摘要都必须匹配；旧报告、单独 `review.json` 或空模板不算交付。

## 定时与补偿

优先用当前 harness 已安装且可调用的原对话调度能力。只有真实创建成功并读回任务标识，才称“已安排”。不可用时用 agent-tools 的间隔 cron 适配器：

```text
python3 <agent-tools>/scripts/install_work_report_schedule.py --task-dir <task-dir>
python3 <agent-tools>/scripts/install_work_report_schedule.py --task-dir <task-dir> --check
```

先注册经过 Judge 确认的周期，再安装定时项。cron 每分钟运行轻量检查，实际周期来自 `reporting.json`。不默认给所有任务注册，不运行完整 agent-tools 安装器。原生 `codex queue` 只保证入队；本机实测入队成功不保证立即执行，因此不把它当作唯一唤醒保障。

cron 的报告执行者是有时限的独立 Codex 进程：保留现有账号登录，读取原文、最新 working-state 和证据，只能写本任务报告目录；不并发 resume Main，不修改业务代码。它需使用真实独立报告 Judge。生成期间有任务内互斥租约，避免同一窗口重复派发；没有最新状态时如实说明，不虚构 Main 的技术理由。该方式会在磁盘产出报告和日志，不保证立即在原对话窗口弹出通知。

超时、模型/工具不可用、Judge未通过、缺少有效收据都视为失败；有限重试后写明确标为“未评审风险快照”的 fallback，保留原因与状态位置，不宣称正式报告通过。任务完成/用户取消时停止周期登记。检查：

```text
python3 report_runtime.py status --task-dir <task-dir>
python3 report_runtime.py tick --task-dir <task-dir>
python3 report_runtime.py cancel --task-dir <task-dir>
python3 <agent-tools>/scripts/install_work_report_schedule.py --task-dir <task-dir> --remove
```

`tick` 只判断到期，不是生成器。真正的 cron 执行入口是 `report_scheduler.py tick`。同一时间段只选择一种调度后端，不能同时安装原生schedule和cron来重复生成。

## 能力与验收边界

本地定时需要对应主机和cron存活；桌面原生定时需要相应App/项目可用。phai 上要独立运行就必须在phai安装并实测，不能用本机结果替代。当前为 Linux/WSL Codex 适配，Claude 仅共用报告生成技能，不声称其hooks已安装。

原文/状态的完整性与语义判断仍需要模型；脚本保证的是约定登记、到期/结束检查、交付摘要绑定、重复控制和失败可见。汇报是独立叙述，用户在之后对内容提出的问题由 Main 在对话回答，不为满足门禁自动改写报告。
