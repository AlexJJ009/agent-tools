# 轻量定时投递：实现与本对话测试

## 行为

`report_timer.py` 等到用户指定时间后，调用 `codex queue --thread <UUID> --message <提示词>`。提供 `--after`、带时区的 `--at`、`--every` 三种互斥方式，以及 status/stop。等待期间不调用模型；到点只负责发起投递，不等待报告完成。

保留单实例 flock、停止标记、小型 state/events。没有报告回执、租约恢复、额外 cron 或监督状态机。默认提示要求立即交付本次中途报告链接，再继续原任务，不修改原授权、不另建定时器；原任务已经完成时如实说明，不虚构新工作。

队列调用失败或结果不确定时不重试同一条；周期可继续发送下一次消息。当前不消除客户端队列里尚未处理的旧消息，取消定时器也不撤回已发送消息。使用说明见 [timer.md](../skills/work-report/references/timer.md)。

## 实测（2026-09-07 UTC）

用户授权在本对话 `01a06f99-146b-75f3-9544-4a51c138ef4f` 直接测试，没有向其他业务对话投递。

| 检查 | 观察 |
|---|---|
| 手动自投递 | 12:25:29 成功入队，ID `01a07bd4-a82e-7b72-b438-354f29644a19` |
| 定时自投递 | 12:36:49 启动 after=2 秒，12:36:51 成功入队，ID `01a07bdf-1174-7231-be29-a8dfc698b583` |
| 运行中工具 | 同时运行的 8 秒测试工具于 12:36:57 正常完成，退出码 0；之后 Main 继续开发 |
| 消息到达模型 | 截至 12:38:00 两条消息仍在本机 queue 表中，当前活动轮尚未收到；不能称为即时 steer |
| 真实取消 | 启动 60 秒后发送的一次性定时器，等待中调用 stop；退出码 0，没有发生 queue 调用 |
| 测试 | timer 12 项、专用安装器 27 项通过；旧 scheduler 9 项通过；Skill 结构校验通过 |
| 独立审查 | 最终脚本复核无剩余 blocker |

本机 CLI 的真实返回格式是 `Queued message <id> for thread <id>.`，实现按真实格式解析并核对目标；成功退出但无法确认 ID 会记录 uncertain。

当前结果证明了到点发送、工具正常运行与取消。没有证明本机客户端会在当前轮中即时 steer，也没有在本次传输探针中生成正式报告；探针明确要求只确认到达，不触发额外报告。测试没有并发 resume，也没有人为中断主对话来伪装即时送达。

原始证据位于 `/home/alex_mercer/projects/_artifacts/agent-tools/work-report-light-timer/`：manual-probe.json、timed-probe.json、queue-readback-after-timer.json、cancel-result.json。两条探针已发送，后续是否到达以本对话实际新消息为准；一次性测试定时器均已退出，没有留下长期业务周期。


## 本机安装与边界

修复源码 `4be867506e37b68f65192e900dab98fd808559f8` 已推送到 `codex/work-report-light-timer`。专用安装器已更新本机 Skill，23 文件一致，5 个既有 hook 定义检查通过。安装前后配置、凭证、CC Switch DB、hooks.json 哈希一致，既有三个 Codex 相关进程身份保持；安装后的 report_timer.py --help 可运行。

没有设置长期业务定时任务，也没有更新 PHAI 或修改其监督程序。最后的队列读回见 [final-queue-readback.json](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-light-timer/final-queue-readback.json)，安装证据见 [install-result.json](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-light-timer/install-result.json)。当前客户端即时 steer 尚未通过验收；如随后在本对话收到探针，应记录它是活动轮内还是轮次结束后到达，不能倒推为已证明即时投递。


## 后续实际到达：探针 A

手动探针 A 于 **2026-09-07 13:05:22 UTC** 作为本对话的新输入到达，对应新 turn `01a07bf9-2c96-71d3-b3bf-5906f05f4265`。这是上一轮最终回复之后，距离 12:25:29 入队约 39 分 53 秒；Main 已在 commentary 确认标识并继续验收记录工作。

这次证明了该消息会回到原对话并在轮次结束后被处理，不能据此称为活动轮中的即时 steer。探针明确不要求正式报告，所以本次仍是消息传输与续行记录的验收。未新增定时器、未改动业务任务。证据：[probe-a-arrival.json](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-light-timer/probe-a-arrival.json)。


## 后续实际到达：探针 B

定时探针 B 于 **2026-09-07 13:08:06 UTC** 到达原对话，对应 turn `01a07bfb-aaaf-7ad2-b4ed-20b99d4cb2c1`，发生在探针 A 所在轮次的最终回复之后。距离 12:36:51 入队约 31 分 15 秒；Main 已在 commentary 确认标识。两条测试探针已从队列消费，开发已完成，本次只记录结果，没有创建新定时器或报告。

两次到达均证实了当前本机客户端的跨轮队列处理；本测试没有观察到活动轮即时 steer。完整报告生成仍不是这两条传输探针的测试内容。证据：[probe-b-arrival.json](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-light-timer/probe-b-arrival.json)。


## 原任务未结束时到达：探针 C

本次使用一个约 3 分钟的受控后台批任务：同一 worker（PID `177766`）每 10 秒完成一批，共 18 批，计算 `SHA256("work-report-long-probe:" + str(i))`，`i=0..17`。这是模拟长任务的续接验收，不是真实业务实验。验收任务还包含 Main 在探针到达后核验全部结果，不能用 worker 退出代替验收完成。

| 时刻（2026-09-07 UTC） | 实际证据 |
|---|---|
| 13:14:19 | 原 worker 启动 |
| 13:14:22 | 一次性定时器成功入队，ID `01a07c01-6852-74d1-a6d8-e1ccf6a8ae34` |
| 13:15:05 | 前一轮结束前检查：4/18 批，worker 仍运行，验收未完成 |
| 13:15:19 | 探针作为原对话新输入到达 |
| 13:15:42 | 保存 arrival.json：PID 与启动 ticks 匹配，进程状态 S，8/18 批、running |
| 13:17:19 | 同一 worker 写出 complete、18/18 批 |
| 13:18:38 | Main 逐项重算全部 18 个 SHA256，完全匹配；内存中替换一个错误摘要的负例被核验拒绝 |

**通过：后台原任务尚未结束时收到投递，随后继续完成该任务的结果核验。** 没有启动替代 worker、新定时器或正式报告，没有操作业务任务。到达时间与现场采样时间分别记录，8/18 是现场采样时的批次进度。

边界：探针仍在前一轮回复结束后被处理，因此没有证明活动模型轮次内的即时 steer；一次受控测试也不保证所有任务都不会受提示词影响。可将该机制用于到点投递、跨轮续接的汇报提醒，不承诺到点立即生成报告。本次明确跳过正式报告，尚不能称为完整 work-report 生成与续行的端到端验收。

证据目录：`/home/alex_mercer/projects/_artifacts/agent-tools/work-report-long-probe/`，包含 `task.json`、`before-yield.json`、`arrival.json`、`progress.json` 和 `result.json`。仅补充本地验收记录，Skill 源码与安装内容未改动。


## 保持当前轮的探针 D：未通过即时到达验收

本次约定 Main 在 180 秒观察窗口内不发送最终回复，并以 15 秒间隔记录队列状态。首次定时器因状态目录不存在而退出，未发送消息；创建目录后再次启动一次性投递，原观察截止时间保持不变。因此实际入队后的窗口约 69 秒，并非完整 180 秒。

| 时间（UTC） | 观察 |
|---|---|
| 2026-09-07 13:33:50 | 开始观察，截止时间为 13:36:50 |
| 2026-09-07 13:35:41 | 成功入队，ID `01a07c14-ed01-7380-b202-9b957faf5676` |
| 2026-09-07 13:36:50 | 最后采样仍在队列；观察进程正常退出，未收到探针 |
| 2026-09-08 01:31:14 | UserPromptSubmit 钩子记录探针输入，turn `01a07ea4-02a4-77f0-88f6-6da85d1bdee4` |
| 2026-09-08 01:31:33 | Main 保存 arrival.json，随后完成验收记录 |

**结论：消息最终到达，但当前轮观察窗口内到达的验收未通过；即时 steer 仍未证明。** 对话记录中 Main 在到达前没有发送最终回复，但入队到钩子输入相隔近 12 小时，不能凭缺少 final 推断模型一直运行，也不能把本次归为即时活动轮插入。长时间间隔的原因尚未核查。

没有延长或重启观察测试、没有新建定时器或正式报告。真实 intent Judge 返回 none，已通过 register 清除候选标记。现场状态、逐次队列采样、到达记录及结论保存在 `/home/alex_mercer/projects/_artifacts/agent-tools/work-report-active-probe-D/` 的 `task.json`、`observations.jsonl`、`arrival.json`、`result.json`。
