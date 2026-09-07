# 轻量定时投递

只做一件事：普通 Python 进程等到时间，调用 `codex queue` 向指定原对话发送一次汇报提示。等待期间不调用模型；发送成功不等于报告已完成，也不等于当前客户端支持即时 steer。

当前入口使用 Unix flock，已面向 Linux/WSL 实现；原生 Windows 需要其他进程/锁适配，未在本轮验证。

## 使用

确认本机 `codex queue --help`、真实当前对话 UUID 和工作目录。用户给出固定时刻时保留时区，不能猜时区；给出间隔时使用指定间隔。不默认给所有任务创建定时器。

先在当前 profile 做一次经用户授权的自投递探针。既记录 queue 返回，也观察消息实际何时进入原对话；如果只证明入队，明确报告这一限制。不要用 `codex exec resume` 并发接管活跃对话，也不要为模拟即时投递而中断当前轮。

状态目录使用项目已忽略的 `docs/work-reports/<任务>/timer/` 或用户指定的产物目录；先核对未跟踪/未暂存及 Git 排除，不为定时器另建业务计划或报告批次。脚本入口在 Skill 的 `scripts/report_timer.py`。

```text
python3 <skill>/scripts/report_timer.py run --workspace <项目绝对路径> \
  --state-dir <定时器绝对目录> --thread <真实UUID> --after 60

python3 <skill>/scripts/report_timer.py run --workspace <项目绝对路径> \
  --state-dir <定时器绝对目录> --thread <真实UUID> --every 1800

python3 <skill>/scripts/report_timer.py run --workspace <项目绝对路径> \
  --state-dir <定时器绝对目录> --thread <真实UUID> --at 2026-09-08T09:00:00+08:00
```

三种时机互斥。需要定制监督范围时传 `--message-file <提示词文件>`，不在脚本中硬编码其他任务的 UUID 或路径。长任务用 tmux 或已有进程管理器承载这条前台命令，保存标识并核对存活；不是启动命令返回就声称后台运行。

```text
python3 <skill>/scripts/report_timer.py status --state-dir <定时器目录>
python3 <skill>/scripts/report_timer.py stop --state-dir <定时器目录>
```

status 显示最后记录，不单独证明进程存活；用 tmux 或对应 PID 另行核对。取消后重新安排使用新的状态目录，避免复用旧 stop 标记。

退出/取消只停止这个定时器，不能终止业务进程。已入队消息不会因停止定时器而撤回。

## 汇报提示

默认提示要求执行当前这次中途汇报、立即在 commentary 给出报告链接，然后继续原任务；保留原目标、授权范围与恢复点，不新建定时任务。定时消息只引导这次操作，不给任务整体追加“以后只能监督”的限制。报告质量仍使用已有 check/Judge/finalize 流程。

新建的原对话定时投递默认由此入口承载；已有 cron 或其他定时器不自动迁移或叠加。不要再注册旧 runtime 的周期或安装 cron。若 setup 消息触发了 pending，真实 intent Judge 可判该设置动作不需要本 runtime 义务，再按原文正常解除候选；这不代替 timer 的启动校验。实际投递到达时再按“中途汇报后继续”处理。

## 保留的最小机制

- 一个 flock 防止同一状态目录启动两个定时器。
- 一个 stop 标记用于取消，一份 state 和 events 记录时间及投递结果。
- 没有等待报告完成的 pending/租约；队列失败或投递结果不确定时不自动补投同一条，避免重复消息。
- 周期逾期不集中补发。周期可能在前一条尚未被模型处理时再次投递；用户可停止定时器或加大间隔，此版本不声称有消息处理去重。

本机休眠或进程退出期间不保证发送；恢复及消息何时被处理取决于宿主。承诺的是到期发起投递，不是报告完成时限或绝对不打断。交付时给出定时器目录、线程 UUID、进程/承载标识、下一触发时间、queue 结果和实际观察到的消息到达阶段。
