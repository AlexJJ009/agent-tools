# Linear Issue Template：需求收集（Discovery / Triage）

## 在 Linear 中的模板设置

- **Template name**：`需求收集｜Discovery / Triage`
- **Template type**：Standard issue template
- **建议默认状态**：Triage
- **适用范围**：尚未确认是否立项、尚未明确修改哪个仓库，或仍需要补充产品判断的想法、问题和机会
- **不适用**：已经有明确 repository、scope 和 acceptance criteria 的代码任务；这类任务应先在目标 GitHub repository 创建 Issue，再同步到 Linear
- **建议默认属性**：Team=`DragAI`；不预设 Project、Assignee、Priority

> 将下方“模板正文”复制到 Linear。方括号中的文字是填写提示；完成 Triage 前必须替换或删除。Discovery Issue 不是开发授权。

---

## 模板正文

### Initial idea

[用一到三句话描述你希望改变什么。允许不完整，但不要直接指定大规模实现方案。]

### Observed problem

- **Current behavior**：[现在真实发生了什么]
- **Affected user / operator / system**：[谁或哪个系统受到影响]
- **Impact**：[造成了什么业务、用户、运维或工程后果]
- **Evidence**：[日志、截图、数据、用户反馈、复现步骤或相关链接；暂时没有时说明需要怎样取得]

### Expected outcome

[描述成功后可以观察到的结果。不要把“重构系统”“建设平台”本身当成结果。]

### Known constraints

- **Time / urgency**：[有明确期限时填写；没有则写 None]
- **Security / privacy / money**：[涉及权限、敏感数据、支付或余额时填写；没有则写 None]
- **Compatibility / operations**：[必须保留的兼容行为、部署条件或人工流程；没有则写 None]
- **Possible systems or repositories**：[只列目前已知候选；不确定时写 Unknown]

### Existing context

- **Related Project / PRD**：[已有则链接；没有则写 None]
- **Related GitHub Issue / incident / discussion**：[已有则链接；没有则写 None]
- **Prior attempts or decisions**：[已有结论时摘要并链接证据；没有则写 None]

### Questions to resolve

- [为了决定是否立项、确定产品行为或拆分工作，还必须回答的问题]

### Triage decision

> 本节由 Product Owner 或 Planning Agent 调研后填写。

- **Decision**：Promote to Project / Convert to GitHub Issue / Keep in Backlog / Reject / Duplicate
- **Reason**：[基于证据说明决定]
- **Resulting Project / PRD / GitHub Issue**：[填写创建或关联的对象；不适用则写 None]
- **Owner**：[下一步负责人]
