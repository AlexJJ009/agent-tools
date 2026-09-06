# 结束与定时汇报运行时（v2）

本页仅在用户约定未来汇报，或处理已注册任务的到期/结束检查时读取。立即汇报与报告后的问答不需要注册。

## 注册约定

1. 保存用户原始提示词到已排除跟踪的产物目录。若由 UserPromptSubmit 捕获，原文在 `<repo>/docs/work-reports/.pending/<session-id>.json` 的 `prompt`，准确复制其文本，不用模型目标改述代替。
2. 用 `report_tool.py init --record-only --workspace <repo> --title <slug> --request <request.txt>` 开始记录，已有任务传 `--task-dir`。结果 `draft.md` 不是正式报告。
3. 使用宿主实际 SubAgent，传入原文路径和 [intent-judge.md](intent-judge.md) 的完整路径，要求先读规则再返回其中定义的 JSON。Judge 的作用是识别用户明确要求，不是为每条日常消息调用模型。将真实返回原样存入 task-dir 的 `intent.json`；若字段或格式错误，让同一 Judge 修正，不自行翻译、补字段或改判定。
4. 调用（脚本均在 skill 的 scripts 目录）：

```text
python3 report_runtime.py register --task-dir <task-dir> --workspace <repo> \
  --request <request.txt> --decision <intent.json> --session-id <原始主对话UUID>
python3 report_runtime.py status --task-dir <task-dir>
```

`confirmed` 才登记结束/周期要求；`none` 清除误触候选，`needs_clarification` 先澄清，不宣称已经安排。周期必须来自原文，不擅自假定三小时。`reporting.json` 是本任务的约定与运行状态，不是另一套业务任务系统。

session-id 必须使用 hook 上下文或 pending JSON 中的真实 session UUID，不能写 `current-session` 等占位。运行时会拒绝占位或与待审原文不匹配的会话绑定。

当前结束语义是注册后 Main 的下一次正常 Stop（本轮最终回复前）。Stop 不表示项目、训练或所有后台作业完成。长任务跨多轮的阶段终点须由用户明确约定；不能让一次“完成后汇报”无限作用于报告之后的问答。

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
