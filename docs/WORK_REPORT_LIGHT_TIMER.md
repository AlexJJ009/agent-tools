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
