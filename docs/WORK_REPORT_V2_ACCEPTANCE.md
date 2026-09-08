# work-report v2：结束、定时与补偿机制验收

v2 保持独立完整的 Markdown 工作汇报。用户看完后的追问由 Main 在对话另答，不把报告改成问答清单。v1 的立即生成入口继续可用。

## 使用与安装

任务开始时可以说“本轮完成后给我工作汇报”，或明确“每三小时汇报一次”。Main 通过真实约定 Judge 区分明确约定、普通追问和需要澄清的周期，再写项目内 reporting.json。

```bash
python3 scripts/install_work_report.py
python3 scripts/install_work_report.py --check
python3 scripts/install_work_report_hooks.py
python3 scripts/install_work_report_hooks.py --check
```

Hook 安装器只合并 work-report 处理器，保留其他定义；不写模型、认证或 CC Switch。Codex 原生 `/hooks` 的信任与激活是独立步骤，安装器 `--check` 只检查定义，不声称验证信任状态。本轮在本机通过原生 Review hooks / Trust all and continue 完成信任，并读回五项 Installed=1、Active=1；没有手写 trusted_hash。

周期经 Judge 确认并注册之后，才执行：

```bash
python3 scripts/install_work_report_schedule.py --task-dir <任务目录>
python3 scripts/install_work_report_schedule.py --task-dir <任务目录> --check
```

默认不创建任何业务定时项。cron 每分钟轻量核查，真正周期来自用户约定。详细 CLI、取消方式和状态语义见 [runtime.md](../skills/work-report/references/runtime.md)。

## 实现边界

| 层次 | v2 行为 | 不作出的承诺 |
|---|---|---|
| 记录阶段 | `init --record-only` 产生 draft.md 与状态快照 | 占位文件不算正式报告 |
| 约定识别 | 实际 SubAgent intent Judge；原文 hash/引文/UUID 绑定 | 保守词法候选不覆盖所有语言表达；自填reviewer_id不是身份认证 |
| 结束检查 | Stop 前核验匹配的 delivery.json；欠报最多两次续行 | Stop 是本轮结束，不是业务项目、后台训练或整个App关闭 |
| 报告质量 | 独立报告 Judge 核对过程、机制、风险、不利证据 | 完整报告不等于完整业务验收；报告后的QA不强制写进报告 |
| 收据 | finalize成功写收据，verify-only只读复核，摘要变化使旧收据失效 | 文件存在、exit0或入队成功不等于已经产出有效报告 |
| 周期生成 | cron启动限时独立Codex快照报告进程，只写任务报告目录 | 不并发resume Main；不保证在原窗口立即弹出通知 |
| 失败/取消 | 有限重试、未评审风险快照、独占租约、进程组清理、取消后移除本任务cron项 | 不无限重试；不把fallback伪装成正式pass |
| 后续问答 | 结束义务在满足的Stop后关闭，普通追问不会重开 | 后续明确的新约定需重新登记 |

周期报告生成跨过多个周期时合并欠报，下一到期时间从完成时向后计算，不集中补发历史窗口。

## 验证结果

| 验证 | 结果 | 证据范围 |
|---|---|---|
| report_tool | 50项通过 | 包含record-only、收据稳定、只读重验、旧结果失效 |
| runtime | 20项通过 | 约定/UUID、结束续行、后续QA关闭、租约竞争、取消、失效收据及周期完成状态 |
| scheduler | 9项通过 | 真正交付与exit0区别、失败快照、超时/取消进程组清理、互斥等 |
| 仓库测试 | 54项通过 | 包含skill安装器、hooks安装器9项和schedule安装器9项；不要与上项重复计数 |
| 独立代码审查 | 已修复明确缺陷并复核 | 包括旧收据摘要错配、Stop/cron竞争、cron字段/命令校验、进程组清理 |
| Native Stop 最小反例 | ALPHA→Stop block→BETA | 证明本机CLI实际支持续行，非仅打印JSON |
| 完整结束补报 | 实际Main先尝试结束→Stop补报→报告Judge→finalize→关闭义务 | 两个Judge的保存JSON都与宿主真实返回一致 |
| 真实cron生成 | 到期后产生真实报告、独立Judge和有效收据 | 不是手动tick或模拟模型；测试定时项已移除 |
| 周期状态修正版 | 真实cron生成的收据在修正版runtime回放通过 | 连续status保留satisfied，下一tick idle；这是回放，不冒充第二次完整模型运行 |
| 本机安装 | 21个skill文件一致，五个hook原生界面Active=1 | 当前Linux/WSL用户；不是所有客户端/远端已认证 |

开发验收阶段未部署 PHAI；后续安装结果见下节。仍未验证 Claude hooks、固定钟点的日历 cron、跨机器通知或多日稳定性，不把本机端到端结果扩大到 PHAI。

## 失败尝试与修正

第一轮完整原生结束测试失败：Main错误使用占位session-id，并重组了格式错误的intent输出；hook响应还夹带非协议诊断字段。后续强制UUID/真实pending绑定、要求同一Judge修正格式、清理native输出，第二轮完整链路通过。

`codex queue` 实测返回入队成功但未使测试任务执行消息，因此未将它作为唯一唤醒机制。cron首次配置又被真实crontab拒绝：把整个PATH嵌入命令超过长度限制；改为任务内metadata保存环境、cron仅调用绝对入口。

首轮cron确实生成合格报告，但监测脚本误等periodic=complete（实际应为satisfied），且状态刷新暴露重复置pending缺陷。已修复并增加回归；保留该监测timeout记录，用独立的生成证据和修正版生命周期回放分别证明两层结果，未将timeout静默改成pass。

## 本机证据

- [完整结束补报结果](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/native-end-v2/result.json)
- [完整结束补报原始事件](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/native-end-v2/session.jsonl)
- [cron实际生成证据](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/cron-acceptance/generation-evidence.json)
- [修正版周期状态回放](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/cron-acceptance/lifecycle-replay.json)
- [本机hook原生激活记录](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/hooks-activation.json)
- [独立代码审查](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/independent-review.md)

以上为本机产物链接，不随clone保存。源码可跟踪；工作报告、约定、收据和执行日志仍在项目内排除Git跟踪的位置。

## 2026-09-06 本地与 PHAI 重新安装

安装源码版本为 `ebac93c8d2532781cc601ee6192cabcdb4cd9022`。使用独立 Skill / hook 安装器，没有运行完整机器安装器。

| 项目 | 本地 | PHAI |
|---|---|---|
| Skill 文件 | 21 个文件与发布源码一致 | 21 个文件与同一发布归档一致 |
| Hook 定义 | 5 项检查通过；此前原生界面 Active=1 | 5 项检查通过；原生信任/激活尚未验收通过 |
| 既有进程 | 未执行重启或终止操作 | 安装前 3 个 Codex 相关进程的 PID、启动标识读回一致 |
| 配置保护 | 仅专用安装器 | 安装阶段 config/auth/CC Switch 哈希未变；最后一次临时 CLI 启动后 config 摘要变化，auth/CC Switch 修改时间仍早于本轮 |
| 定时环境 | 此前真实 cron 验收通过；测试定时项已删除 | 没有 crontab 命令，未安装系统 cron 服务，也未创建业务定时项 |

PHAI 安装在实际用户 HOME 对应的 `.agents/skills/work-report`，没有误写 `/root`。本轮只创建独立临时 CLI 检查原生 hook 界面，未向既有 Codex 进程发送信号。终端初始化和更新提示曾阻塞检查；临时关闭启动更新检查后进入信任界面，但未取得五项 Active=1 的可靠读回，不能声称远端结束补报已启用。没有手写信任状态，也没有升级 Codex。

尚需在 PHAI 原生 `/hooks` 界面完成信任及 Active 读回；远端周期功能还需可用的 cron 或宿主调度器，并按具体任务约定登记。已有进程是否重新加载新版 Skill/hooks 未验证，不能从磁盘安装结果推断。

安装与进程保护证据：[本地验收产物目录](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/phai-install)。这些机器证据不随 clone 保存。

最后一次临时 CLI 的 `protected_configuration_unchanged=false`，不能把它写成保护检查通过。只读追查发现 `config.toml` 的修改时间位于本轮，当前含 `tui.model_availability_nux.gpt-6-astra=1`；这与原生界面的新模型提示一致，但因探针没有保存逐项前置摘要/内容，无法严格证明唯一变化就是该提示状态。auth 与 CC Switch 文件修改时间均早于本轮。未猜测回滚配置，未再启动验收客户端；原有三个进程仍通过身份读回。

## 2026-09-06 PHAI cron 安装与 hook 激活复核

此节是用户授权安装 cron、并在原生界面信任 hook 之后的最新验收，更新前节的待办状态。

- 原生新客户端 `/hooks` 已读回 PostToolUse、SessionStart、UserPromptSubmit、Stop、Interrupt 五项均为 Installed=1、Active=1；核查没有修改信任记录、没有使用跳过信任参数。
- Ubuntu cron 3.0pl1-184ubuntu2 已安装。APT 同时安装/更新了其系统依赖，没有升级 Codex。该容器 PID 1 是 Supervisor，包安装阶段没有自动启动 cron；在现有 Supervisor 配置中新增 `agent-tools-cron`，仅 update 这个组，`/usr/sbin/cron -f` 已为 RUNNING，设置 autostart/autorestart。没有重启 Supervisor 或其他服务。
- 使用真实用户 crontab 登记临时每分钟测试项；daemon 于 `2026-09-06T11:56:01Z` 写入标记。测试项已删除，原 crontab 内容保持一致，没有创建业务汇报周期。
- 本轮开始时四个既有 Codex 相关进程均保持相同 PID 和启动标识；只关闭本轮新建的临时核查客户端。`auth.json`、CC Switch 数据库前后 SHA-256 一致。
- 临时原生客户端仍会改写 config 的 TUI 状态；当前 `tui.model_availability_nux.gpt-6-astra=3`。config 全文摘要变化，不声称其字节完全不变，也未猜测回滚用户配置。

当前可以按具体任务约定注册远端周期。此次证明了 cron 实际执行与原生 hook 激活，没有再次在 PHAI 跑完整的模型生成报告/Judge 链路，也未通过容器重建测试证明配置跨平台重建保留。此前本机的完整链路验收仍单独列示。

证据：[最终结果](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/phai-cron/result.json)、[原生 hook 读回](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-v2/phai-cron/hooks-readonly-ui.log)。
