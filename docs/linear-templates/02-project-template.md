# Linear Project Template：项目交付容器

## 在 Linear 中的模板设置

- **Template name**：`项目交付｜Project Delivery`
- **适用范围**：一次有明确结束条件、需要多个 Issue 协同完成的产品或工程结果
- **不适用**：永久存在的产品域、单个小 Bug、仅用于把同类仓库放在一起的分类容器
- **建议默认状态**：Backlog
- **建议创建内容**：一个 PRD Document；按真实交付阶段创建 Milestones，不预生成空 Issue

> Project description 只保存摘要和导航，不复制完整 PRD。将下方“模板正文”复制到 Linear Project description。

---

## 模板正文

### Project outcome

{用一句话描述这个 Project 结束时交付的完整结果。}

### Why now

{用两到四句话说明当前问题、影响和立项原因。详细证据放在 PRD。}

### Product requirement

- **PRD Document**：{关联使用“产品需求文档｜PRD”模板创建的 Linear Document}
- **PRD status**：Draft / In review / Approved
- **Product owner**：{对目标、范围和取舍负责的人}

### Scope map

- **Affected products/services**：{受影响的产品或服务}
- **Repositories**：{可能涉及的 GitHub repositories；最终以各 Issue 的单仓库边界为准}
- **External systems**：{第三方 API、部署环境或运维依赖；没有则写 None}

### Delivery strategy

- **Agent mode**：一个 Project Agent 读取完整 PRD 和 DAG，按拓扑顺序连续完成一个或多个 Delivery Batch
- **Issue source**：代码任务先在目标 GitHub repository 创建 Issue，由 GitHub → Linear 自动同步；非代码工作可以直接创建 Linear Issue
- **Planning metadata**：同步后的 Linear Issue 再关联本 Project，并在 Linear 设置 priority、native dependencies、milestone 和 Delivery Batch
- **Batch rule**：同一仓库、同一发布边界且紧密相关的多个 Ready Issues 可以合并为一个 branch/PR
- **CI rule**：每个 Issue 完成时跑定向检查；每个 Delivery Batch 提交 review 前跑一次完整 CI
- **Cross-repo rule**：每个仓库保留独立 PR；最终在固定 candidate SHAs 上运行跨仓库验收

### Milestones

{在 Linear 中创建真实 Milestones，并在此保留简短导航。不要为了填模板而创建空阶段。}

1. **PRD approved**：产品目标、非目标和验收已确认
2. **Delivery batches ready**：Issues、依赖和批次已经人工检查
3. **Implementation complete**：计划内批次完成并通过各仓库 CI/review
4. **Release accepted**：需要的集成验证、发布和运行证据已经确认

### Project completion criteria

- [ ] PRD 中的产品级 acceptance criteria 已满足
- [ ] Project 内没有仍属于本次范围的未完成 Issue
- [ ] 代码任务的 GitHub Issue 与 Linear 映射没有重复项或失联项
- [ ] 所有计划内 PR 已合并，或明确记录了取消原因
- [ ] 需要的迁移、发布、回滚和运维说明已经完成
- [ ] 新发现但不属于本 Project 的工作已转成独立 Issue

### Links

- **Technical design / ADR**：{repo 内版本化文档链接；没有则写 None}
- **Project view / issue DAG**：{Linear view 或关系图链接}
- **Release / deployment evidence**：{完成后填写；尚未发布时删除本行或保持空白}
