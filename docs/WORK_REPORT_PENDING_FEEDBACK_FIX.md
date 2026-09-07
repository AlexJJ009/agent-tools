# 重复 pending hook 提醒：排查与修复

## 现场证据

只读检查 PHAI 的 [Start conversation](codex://threads/01a079cd-a374-7ee3-84bc-f9eea2c1608d)，不执行截图中的实验指令，也不改动远端任务或配置。

| 观察 | 含义 |
|---|---|
| 五个事件各一个处理器 | 不是重复安装 hook |
| 03:12:50 和 03:13:27 UTC 出现相同 Stop hook feedback | 同一未解除候选触发了两次续行检查，不是用户再次发出报告要求 |
| 初始化失败 `git_ignore_missing` / `external_git_root` | 将实验输出目录套用为报告输出目录，实际落入另一个 Git 根 |
| register 失败 `task_dir_git_mismatch` | 使用外部产物目录作为 runtime task-dir；原本尚未登记成功 |
| 后续 `needs_clarification` 仍失败 `request_context_mismatch` | 非确认判定也被强制要求完整报告 context；runtime 的 read_text 又规范化了 CRLF |
| 临时将 request 读取改为 read_bytes().decode 后成功 | 证明换行字节不一致是具体缺陷，不是用户没有批准报告 |

原始日志时间为 2026-09-07 UTC。核查时目标 pending 已由该任务清除；历史 UI 气泡不会因源码修复消失。原文的“完整矩阵结束后汇报”是业务里程碑，不能换成“每条回复结束前汇报”。

## 修复边界

- runtime 按原始 UTF-8 字节读取原文，保留 CRLF，与报告工具及 Judge 摘要一致。
- 先验证真实 Judge 的格式、摘要、引文及对应 pending。`none` / `needs_clarification` / `deferred` 不再依赖 task-dir 或报告初始化即可解除候选。
- 明确的未来里程碑使用 deferred：保留原要求，不绑定当前 Stop，不声称已调度或已交付。Main 仍需在原工作状态中保留要求，并在业务完成时生成报告；本修复没有通用的实验完成检测器。
- 处理记录按 session + request hash 保存，后续普通问答不覆盖原来的未来要求。
- 已校验 Judge 后的登记失败保留具体诊断；相同错误不再重复假称 Judge 未执行。真正的 confirmed 报告仍须通过目录、context、新鲜度与交付检查。
- 不要求用户审批报告或默认 Git 排除；不使用猴子补丁、伪造 context 或改写原文来绕过检查。

## 本机验证

| 检查 | 结果 |
|---|---|
| CRLF 旧版反例 | 在 c189b08 runtime 上复现同样的 request_context_mismatch；不是只检查新代码返回成功 |
| Runtime / scheduler / report tool | 44 + 9 + 50 = 103 项通过 |
| Skill / hooks / schedule 安装器 | 26 项通过 |
| 真实独立 intent Judge | 对带 CRLF 的明确未来里程碑判为 deferred；原始 JSON 未被改写 |
| 本机 hook 入口回放 | 不传 task-dir 即可记录上述判定；连续四次 Stop 返回空 JSON，不创建正式报告或 runtime obligation |
| 独立审查 | 新提示在旧判定写入和清理之间到达的反例通过，新 pending 保留；无剩余 blocker |

pending 捕获、错误记录、Stop 更新和按摘要清理使用同一 session 锁。未来约定记录以 session + request hash 命名，后续 ordinary none 不覆盖它；同一登记错误 retry 不重复诊断。无候选的普通 Stop 和 nonconfirmed register 不创建噪声目录。

这次是在本机直接调用真实 hook/runtime 入口回放，并使用真实 intent Judge；没有重跑 PHAI 实验，也没有把本机测试称为远端端到端验收。明确业务完成里程碑被保留，但没有自动调度或业务完成检测器。

证据：[本机回放结果](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-pending-feedback/local-result.json)、[旧版 CRLF 反例](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-pending-feedback/crlf-baseline-failure.txt)。原始本机产物不随 clone 保存。
