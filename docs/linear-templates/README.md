# DragAI Linear Team Templates

这组模板对应 Linear `Team settings > Templates` 中的三个入口。它们采用按对象划分的单一真相：

| Linear template type | Template name | 保存什么 | 不保存什么 |
|---|---|---|---|
| Issue | `需求收集｜Discovery / Triage` | 尚未立项或尚未明确 repo 的需求入口 | 已可执行的代码任务 |
| Project | `项目交付｜Project Delivery` | 项目摘要、PRD 导航、交付策略、里程碑和完成条件 | 完整 PRD、详细技术设计 |
| Document | `产品需求文档｜PRD` | 产品问题、目标、范围、产品要求、验收和任务拆解 | 代码方案、API/schema 细节、迁移脚本和 runbook |

对应文件：

1. [`01-issue-template.md`](01-issue-template.md)
2. [`02-project-template.md`](02-project-template.md)
3. [`03-prd-document-template.md`](03-prd-document-template.md)

## 手动导入顺序

### 1. Issue template

1. 在 `Issue templates` 点击 `New template`。
2. 选择 Standard issue template。
3. 名称填写 `需求收集｜Discovery / Triage`。
4. 默认状态选择 `Triage`；不要预设 Project、Assignee 或 Priority。
5. 从 `01-issue-template.md` 复制“模板正文”以下内容。

### 2. Project template

1. 在 `Project templates` 点击 `New template`。
2. 名称填写 `项目交付｜Project Delivery`。
3. 默认状态选择 `Backlog`。
4. 从 `02-project-template.md` 复制“模板正文”以下内容到 Project description。
5. 不预生成空 Issues；Milestones 只在确有对应交付阶段时创建。

### 3. Document template

1. 在 `Document templates` 点击 `New template`。
2. 名称填写 `产品需求文档｜PRD`。
3. 从 `03-prd-document-template.md` 复制“模板正文”以下内容。
4. 使用时把 Document 关联到对应 Project，标题使用 `PRD｜{Project name}`。

## 使用规则

- 模糊需求可以从 Discovery Issue 开始；已经明确是多 Issue 的结果时，可以直接创建 Project 和 PRD，不必先建 Discovery Issue。
- 代码 Issue 在目标 GitHub repository 创建，由 GitHub → Linear 自动同步；不要人工创建两份。
- Linear 保存 Project、PRD、priority、milestone、dependency 和 batch；GitHub 保存代码 Issue、PR、review 和 CI evidence。
- UI 模板只提高一致性，不构成强制门禁。Agent 创建内容时仍需由 workflow 生成相同字段，PR gate 再检查被引用 work item 是否完整、已 Ready 且没有未解决的产品决策。
