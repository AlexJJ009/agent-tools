# 迁移验收结果

候选实现已完成。独立审阅者将 **20 项判为各自证据范围内通过，AC-21 等待真实用户反馈**。目前没有替换正在使用的 skill，也没有合并 PR。这不是“所有首次生成都正确”，也不是已经证明用户学会了写作。

实现版本：`602b528b2ade668dd736ee01ffccf2dd7b93b3ad`。之后的提交只更新交付文档和工作记录。原 [PRD](PRD.md)、[checklist](checklist.yaml) 与固定用例保持冻结；此页总结实际结果，不把计划中的 `not_run` 改写为机器验收通过。

## 核查了什么

- **代码与兼容性**：152 项相关测试通过；曾故意移除 pending-input 检查并观察测试失败。项目级 skill 发现、等价 `task.md` 记录复用也保留了修复前失败与修复后通过的证据。独立代码、安装、提示词增量和维护性审阅已完成。
- **实际调用**：30 个固定用例和 6 个额外请求已执行。10 类关键禁止行为各有三次适用范围内的会话证据。宿主为 Linux/WSL Codex CLI 0.155.1，实际模型为 `gpt-5.6-sol` medium；请求的 GPT-5.5 不可用。并非所有旧用例都在最终全部文件字节上重新执行：报告逐项说明所用版本及未改变组件的适用范围。
- **安装与回退**：临时用户目录中的真实安装、源目录搬迁后的教学与写稿调用、精确回退均留有记录。现有日常 skill 的已登记链接仍保持原样。
- **材料审阅**：独立读者先看产物，再核对请求和来源。教学示范、直接写稿和练习反馈分开检查；模拟学习者的回答不作为用户能力证据。

## 没有抹去的失败

最后三次笔记整理都正确使用了导出入口与索引，也把写入留在指定工作目录。但三份初稿都把“只修正 `None` 的 JSON 编码”扩大成了“改变所有非空输入的序列化方式”。这是实质性的内容问题。

审阅者指出后，原会话分别修订了笔记，以同一来源身份重新导出，并再次检查正文、索引和摘要值。**结果是三次初稿失败、三次经反馈修订后通过**；不能表述为三次无辅助成功。原文件和失败记录保留在[初稿审阅](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/native/reviews/final-t17-triple-original-adjudication.md)与[修订审阅](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/native/reviews/final-t17-triple-correction-review.md)中。

此前的项目能力未发现、重复任务记录、缺少能力时未说明、阶段恢复不完整，以及超出指定目录的临时文件写入，也保留在[完整会话结果](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/native/native-review-results.md)。修正后的证据不修改原始轨迹。

## Zotero：日常保留一套

本机使用原有 Win11 Zotero 与日常 library；WSL 只通过明确配置读取 Windows API 和 PDF。安装器不安装 Zotero。

截图中额外出现的窗口来自本次合成材料验收的临时 Windows profile。它使用已有的 Windows 可执行程序，数据目录与 API 端口独立；现已关闭并删除 profile 和测试库。先前任务创建的 WSL Zotero 也已移除。核查的原有进程身份、论文条目、附件对象与 PDF 摘要值保持不变。这里核对的是指定对象，不能扩大为完整资料库或全文件系统审计。详见[清理记录](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/windows-zotero-fixture/cleanup-report.json)。

## 逐项结论

以下结论来自[独立验收映射](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/reviews/ac-evidence-audit.md)，每项的来源、摘要值、实际版本和限制见[机器可读记录](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/reviews/ac-evidence-audit.json)。它们是语义与证据审阅结论，不是通过填写状态获得的机械 gate 结果。

| 项目 | 核查内容 | 结论 |
|---|---|---|
| AC-01 | Preserve the existing teaching baseline | 范围内通过 |
| AC-02 | Agent-led semantic routing | 范围内通过 |
| AC-03 | No unwanted teaching or library side effects | 范围内通过 |
| AC-04 | Mixed tasks, updates, and continuation | 范围内通过 |
| AC-05 | Real Hook lifecycle and explicit coverage | 范围内通过 |
| AC-06 | Hook absence and stale-state behavior | 范围内通过 |
| AC-07 | English maintained instructions and contextual output language | 范围内通过 |
| AC-08 | Domain terms cause concrete professional actions | 范围内通过 |
| AC-09 | Direct manuscript drafting and revision | 范围内通过 |
| AC-10 | Guided practice preserves learner authorship | 范围内通过 |
| AC-11 | ReadPapers-only library and close-reading adapter | 范围内通过 |
| AC-12 | Remote evidence and execution authority stay separate | 范围内通过 |
| AC-13 | Minimal records and one canonical development state | 范围内通过 |
| AC-14 | Explicit curation with portable provenance | 范围内通过 |
| AC-15 | Legacy records and managed-region integrity | 范围内通过 |
| AC-16 | Shared writing principles without workflow leakage | 范围内通过 |
| AC-17 | Independent cold reading and source verification | 范围内通过 |
| AC-18 | Isolated installation, relocation, and scoped rollback | 范围内通过 |
| AC-19 | Focused cleanup, attribution, and independent code review | 范围内通过 |
| AC-20 | Native coverage, holdout requests, and overhead report | 范围内通过 |
| AC-21 | Bounded user pilot and explicit acceptance | 等待用户反馈 |

## 成本与适用边界

本轮完整调查和迭代共记录 138 个运行、166 个 turn、1,901 次模型响应、1,735 次去重后的原生工具调用；累计进程时间 23,352.433 秒（约 6.49 小时）。进程存在并发，这不是实际墙钟用时。统计包含历史失败、无效初始环境、重复验证和修订，并非每条日常请求的开销。

原生响应统计包含 37,494,195 输入 token，其中 33,575,296 是缓存输入子集；693,284 输出 token，其中 170,912 是推理输出子集。它们来自实际响应记录，并不代表计费金额，也不覆盖本任务所有主 Agent 的工作。单次调用、计数口径与部分失败见[运行统计](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/native/native-tool-accounting.json)。没有做足以分离路由额外耗时的配对性能实验，因此不宣称已经证明日常开销很低。

Hook 的实测范围是被登记的入口与所观察到的事件；不能拦截任意 shell/MCP 或保证模型理解正确。本轮也不是 native Windows Codex 宿主资格测试。

一次隔离试验期间，日常 Codex 配置文件的摘要值发生变化，写入者未查明。没有证据将它归因于候选代码，也不能声称全部全局配置始终未变；没有擅自还原该文件。[漂移记录](/home/alex_mercer/projects/_artifacts/agent-tools/codex-learning-workflow-migration/native/protected-config-drift.json)保留了核查边界。它与已单独核实的临时安装回退、指定 Zotero 对象未变化是不同结论。

## 尚需的用户反馈

只需看[两组材料与具体问题](reviews/human-review.md)：学习示范及反馈是否给足背景、帮助是否过多、是否留下输出空间；英文稿件是否能作为继续修改的起点。泛泛认可、此前的开发授权和模拟练习都不替代这些具体反馈。

按 [PRD 第 7 节 M3 与第 8 节](PRD.md)，技术核查与这一小范围用户体验完成后再激活单一目标。这里等待的是体验证据，不是重新请求同一项开发或安装授权。
