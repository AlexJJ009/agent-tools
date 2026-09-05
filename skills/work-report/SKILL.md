---
name: work-report
description: 生成长任务或用户指定阶段的本地 Markdown 工作汇报，记录关键决定、验证、阻塞与范围漂移，并经过脚本检查和独立 SubAgent Judge。用于“汇报进展”“完成后汇报”“工作汇报”“work-report”；普通短答、只问一个状态事实时不启动完整汇报。不要求 Linear、幻灯片或额外开发流程。
---

# Work Report

把工作过程讲清楚，让用户判断目标、进展、取舍、风险和下一步。Markdown 是默认载体，至少一张有实际内容的表格或图示；不自动发布、commit、启动定时任务或创建业务 PRD。

## 固定材料与工具

先读 [共同 rubric](references/rubric.yaml)，生成时用 [报告模板](assets/report.md)。Judge 再读 [专用规则](references/judge.md)。两者不各维护一套标准，不因评审而追加业务验收要求。

脚本位于本 SKILL.md 同目录的 `scripts/report_tool.py`，调用：

```text
uv run --script <skill-dir>/scripts/report_tool.py --help
```

依赖由脚本的 PEP 723 元数据固定，uv 缓存在用户目录，不修改被汇报项目的 Python 环境。安装时应预热工具；uv 不可用时报告工具未就绪，不声称机器检查通过。

## 1. 开始约定并记录过程

用户约定后续汇报时，在任务开始就记录用户原始要求、后续修订、关切、报告时机和过程状态。优先引用已有原文文件；仅在用户要求只存在对话时，把必要原文保存到项目产物目录的 `request.txt`，不能只写自己的目标改述。创建 request.txt 前先用 Git 确认目录没有已跟踪文件；初始化完成后脚本会设置和核验排除规则。现成原文可直接传入，不额外复制全文聊天。

工具初始化示例（路径用本任务的真实绝对路径）：

```text
uv run --script <skill-dir>/scripts/report_tool.py init \
  --workspace <执行项目路径> --title <简短英文主题> \
  --request <用户原文文件> --kind progress
```

如果初始化因权限、sandbox 或 Git 排除规则失败，停止该次初始化并报告具体原因；不要擅自改用 /tmp、公共目录或另一工作区来绕过约定。只有用户明确指定新位置时才使用 --output-root。

输出给出 task/report 路径及标识。默认在项目 `docs/work-reports/`，task/report ID 带 UTC 时间与随机后缀。用户指定位置用 `--output-root`；已有任务用 `--task-dir`，已有状态文件用 `--state`。`--window-start` / `--window-end` 接受带时区的 ISO 时间，收尾用 `--kind final`。同一任务复用 task，不建多个互相冲突的状态文件。

`working-state.md` 简短维护：当前进度；带时间的重要决定与理由；失败尝试、验证与证据；阻塞和下一步；后台任务的产物位置及查询方式。在这些事件发生时更新，不逐条抄工具调用，不到最后伪造事中记录，不自动写全局 memory。没有发生的事项说明无；没有证据的说明未验证。

初始化在 `context.json` 冻结本次原文与工作状态，供 Judge 独立读取。若 init 是任务开始时运行，此后状态有更新，正式汇报时用相同 task-dir 再 init 一个批次，取得最新快照；早期未交付的占位批次不能冒充完成报告。正在运行的后台作业不因汇报被终止。

## 2. 生成 Markdown

读取本次 context、最新可归属的代码/测试/日志证据，再写 `report.md`。保留工具生成的 frontmatter；按共同 rubric 的六个 H2 内容区填写，删除占位符。没有重大决定或待决策项就如实说明，不填充空话。

最少一张真实状态／验证表即可。脚本可靠支持 Markdown 表格及实际图片附件；仅有 Mermaid 时当前版本不能验证其语法，需补一张表格。不要为通过形式检查安装网页渲染系统。图旁说明结论，图片放本批次 `assets/`。引用本地证据时使用可打开的路径；外部 URL 不等于已验证。大日志只保留必要观察与原位置，不把敏感内容或无关聊天复制进报告。

对照用户原要求与修订，披露超出范围的实现、成本或过度设计。区分必要步骤与自行扩展，别把用户已有未提交改动归入本任务。漂移严重时说明影响、建议停止哪部分及需用户判断什么，不自行删代码或回滚。

## 3. 机器检查 → 独立 Judge → 交付检查

```text
uv run --script <skill-dir>/scripts/report_tool.py check \
  --report <report.md> --task <工具给出的 task-id> --workspace <执行项目路径>
```

读取返回的退出码、issues 和 warnings。`0` 只证明适用的机器条件通过；`1` 表示不满足条件，`2` 表示工具未完成。修正实际问题后再 check。不能把“字段齐全”说成“内容正确”。

机器检查通过后，使用宿主实际的 SubAgent 委派工具，在独立上下文发起只读 Judge。传入：用户原始输入快照 context.json、report.md、checks.json、共同 rubric、judge.md、必要证据路径。不要传自己的预期 verdict；不要让 Judge 修改文件或业务代码。遵循当前用户的 reviewer 模型约定；没有指定时用当前宿主可用模型，不创建额外模型服务。

等待真实返回，将其 JSON 原样保存为本批次 `review.json`；格式错则要求修正格式，不能把不通过改成通过。最多两轮报告修订，每次改完报告重新 check 和 Judge。子代理不可用、超时或仍不通过时，提供明确标记的草稿／风险快照及原因，不伪造独立评审，不无限重试。

```text
uv run --script <skill-dir>/scripts/report_tool.py finalize \
  --report <report.md> --task <task-id> --workspace <执行项目路径>
```

只在 finalize 返回 0 时声明“报告检查通过，Judge 结果为 pass”。脚本总会说明自己不能认证 Judge 来源；只有实际宿主调用记录才支持“已发生独立委派”，不能用 JSON 中自填的 reviewer_id 作证明。报告、附件、规则或被引用证据改变后，旧结果失效。

## 4. 交付与存储边界

返回 `report.md` 完整本地路径、最重要的结论／待决策事项及未核验范围。用户可用 VS Code 或 Obsidian 阅读；不要求 HTML 或演示文稿。报告检查通过不等于业务任务完成，诚实披露漂移的报告也可以通过。

产物默认通过 Git 本地 info/exclude 排除，脚本核验实际忽略和未跟踪状态。不要自动 git add、commit、强制 untrack 或改项目 .gitignore。用户要求团队共享规则或提交指定报告时再按要求处理；共享报告可导出到受跟踪文档目录，其他过程产物继续忽略。未跟踪文件不随 clone 保存，移除工作区前按需要导出并告知位置。

这是受检查的报告入口，不是自动运行的宿主 hook，不能保证所有回复无法绕过检查。第一版没有定时器、Linear 发布、全局记录服务或自动长期记忆；不要把这些当成 Judge 的加分项。
