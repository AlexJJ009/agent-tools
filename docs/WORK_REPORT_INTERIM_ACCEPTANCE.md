# 中途工作汇报后续行：修复与验收

## 问题与行为

用户在长任务中要求“任务还要继续，但现在临时汇报进展”，旧 Skill 允许 Agent 交付报告后发送 final，即使原任务仍有工作。报告中写“任务继续”或后台作业存活，不能证明 Main 已恢复开发。

修复区分三个入口：任务完成后的 final 报告；中途抽检的 progress 报告；没有续行要求的独立即时报告。中途报告在 commentary 交付，随后实际执行原任务下一步；任务完成、用户取消或需要用户输入时才结束。

## 最小机制

- Intent Judge 根据当前用户原文判断 `resume_after_report`，旧 intent 未提供时为 false。截图、例句和开发需求不登记为当前汇报义务。
- 运行时单独保存 interim progress 义务。原任务已有不同活动约定时，另建临时汇报目录，读取原 working-state，并保留原任务引用；不覆盖或取消旧结束/周期约定。
- 没有新鲜有效收据时沿用有限补报。收据有效、尚未观察到非报告工具活动时，Stop 阻止一次并要求恢复原任务。已观察到后续工具活动则避免重复提醒。这个启发式只能观察活动，不能认证其业务价值。
- 中途义务消费后关闭，不因后续问答或旧报告变化重开；不宣称原业务任务完成。用户 Interrupt/cancel 优先。

没有增加业务调度系统、自动训练流程或永久续行门禁。报告 Judge 仍只审快照质量；验收另查原任务的具体后续动作。

## 验证

| 检查 | 结果与边界 |
|---|---|
| 旧版反例 | 旧 runtime 在新增的 standalone interim 注册测试上失败，证明测试能检出旧行为 |
| Runtime | 35 项通过；包含跨目录优先级、取消、一次续行、活动旧约定保护、过期收据、报告改动失效、业务证据变化、即时链接提示 |
| 报告工具 | 50 项通过 |
| 调度器 | 9 项通过 |
| 专用安装器 | 26 项通过（Skill、hooks、schedule） |
| Skill 结构 | quick_validate 通过 |
| 独立代码审查 | 最终源码及即时链接提示均复核，无剩余 blocker |

首轮真实任务恢复并完成了 3 项测试，但正式 report 批次早于 register cutoff，正确触发新鲜度补报；保留失败记录，没有将它说成通过。第二轮登记顺序正确、确实继续测试且正常结束，但报告链接直到最终回复才出现；顺序检查检出此问题。修复后要求 finalize 成功的下一条进度消息立即给出链接，PostToolUse 同时给出一次实际链接提示。第三轮已通过，结果如下。


## 第三轮真实任务验收

独立任务：`01a076d4-c076-7ba2-b247-7791b80f3660`。使用冻结的最终 Skill 源码，在隔离工作区继续已有 `sum_even` 小任务，没有部署候选到用户环境来冒充隔离验收。

| 观察 | 结果 |
|---|---|
| 报告和实际工作顺序 | 完成事件索引 61 finalize → 62 commentary 中的报告链接 → 66 实际 unittest 成功 |
| 原任务续行 | 报告后新增测试，3 项实际运行通过，再写 acceptance.json |
| 真实 Judge | intent / report 两次独立委派均有记录，保存 JSON 与真实返回逐项一致 |
| 结束行为 | 一个正常 Stop，没有多余补报；interim 已消费，gate=observed |
| 候选一致性 | 验收 snapshot 的 21 个文件与最终 Skill 源码一致 |

这是小任务流程验收，不证明多日稳定性，也不以任意工具调用代替业务结果。一次性 Stop 提醒仅在原生 hooks 实际加载且受信任时生效；无 hook 的宿主只有 Skill 文字流程约束。

证据：[第三轮结果](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-interim/acceptance-v3/result.json)、[完整事件](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-interim/acceptance-v3/session.jsonl)、[原生 hook 事件](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-interim/acceptance-v3/hooks.jsonl)、[独立审查摘要](/home/alex_mercer/projects/_artifacts/agent-tools/work-report-interim/independent-review.md)。第一、二轮分别保存在同级 acceptance / acceptance-v2；这些本地原始产物不随 clone 保存。
