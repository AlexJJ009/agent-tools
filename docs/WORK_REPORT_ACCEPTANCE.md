# work-report v1 开发、安装与验收

本机范围：当前 Linux/WSL 用户 `alex_mercer`。Codex CLI 0.153.4。开发和快速验收已完成；数小时纵向任务效果、独立 Claude 运行时、hook、定时器和外部发布分别属于未完成或未纳入的验证范围。

## 使用与安装

- Codex：`$work-report`。任务开始时可以约定“中途记录关键决定、验证和阻塞，完成时写本地 Markdown 汇报”。
- Claude Code：安装了 `/work-report` 对应的 skill 入口，但本轮没有另做 Claude 运行时调用验收。
- 默认产物：项目 `docs/work-reports/<task-id>/<report-id>/report.md`。`context.json` 冻结输入，`checks.json` 和 `review.json` 保存机器／Judge 结果。产物通过 Git 本地 exclude 排除，不自动提交。
- 来源：[SKILL.md](../skills/work-report/SKILL.md)、[共同 rubric](../skills/work-report/references/rubric.yaml)、[Judge 规则](../skills/work-report/references/judge.md)、[检查器](../skills/work-report/scripts/report_tool.py)。

在仓库根运行：

```bash
python3 scripts/install_work_report.py
python3 scripts/install_work_report.py --check
```

安装器先运行当前平台的 Codex target guard。Codex 文件安装到 `~/.agents/skills/work-report`，Claude 链接到同一份内容。使用 uv 的隔离脚本依赖，不修改业务项目依赖、模型、认证、hook 或定时配置。安装器保留非受管目录；更新后的工具校验失败会恢复原安装。

## 已验证的结果

| 层次 | 结果 | 边界 |
|---|---|---|
| 技能基础校验 | 通过 | frontmatter 与入口有效，不单独证明行为 |
| 报告工具 CLI 测试 | 47 项通过 | 含文件／结构／图表／引用／Git／冻结输入／过期结果与 malformed 输入正反例 |
| 安装器隔离测试 | 8 项通过 | 含拒绝错目标、保护已有文件、来源漂移、安装后失败回退 |
| 当前仓库测试 | 35 项通过 | 包含上述 8 项，不重复累计 |
| 独立代码审查 | 修复后通过 | 对明确缺陷复查，非形式性自报 |
| 安装读回 | 15 个源文件一致，Claude link 正确 | 当前用户，没有部署到其他主机 |
| 真实匿名 Judge 校准 | 5 例符合预期 | 合格／诚实漂移通过；隐藏漂移／空报告／夸大证据需修订；不是统计可靠率 |
| 新 Codex 会话发现与调用 | 通过 | 真实记录观察到已安装 SKILL.md 的读取 |
| 新会话完整链路 | 通过 | 项目内生成 → check → 实际 SubAgent → 保存返回 → finalize |
| 评审来源核对 | 通过 | 保存 JSON 与真实宿主返回逐字段一致；不是仅看 reviewer_id |
| 受限权限失败路径复测 | 通过 | 新会话初始化返回 2 后明确停止；未切换目录、未生成报告、未伪称通过 |
| Git 产物策略 | 通过 | `git check-ignore` 生效，`git ls-files` 无产物 |
| Markdown 显示 | 通过 | 标准 Markdown 渲染后用本地 Chromium 检查中文标题和表格；未逐一测试所有编辑器插件 |

复现自动测试：

```bash
uv run --with markdown-it-py==4.0.0 --with PyYAML==6.0.2 \
  python -m unittest discover -s skills/work-report/tests
python3 -m unittest discover -s tests -p test_install_work_report.py
```

## 失败尝试与修正

首个新会话验收使用 `workspace-write` sandbox，写入 `.git/info/exclude` 被拒绝。agent 曾自行改用 `/tmp`；该次验收被中断，未计为通过。SKILL.md 补上“不擅自改变输出位置”的规则。

随后在与主会话一致的权限模式下，重新运行一个新会话，成功在项目内完成了全过程。受限 sandbox 仍可能要求宿主明确允许写 Git 排除文件；不能因此宣称所有权限组合都已支持或自动绕过。独立 Judge 的实际调用有宿主记录；脚本本身仍明确输出无法认证 Judge 身份。

补充复测：修正后的 skill 在另一个 `workspace-write` 新会话中再次遇到排除文件只读，按预期停止并说明原因，没有擅自更换输出目录。这里通过的是失败处理验收，不能解读成受限环境已成功生成报告。

## 证据与本次开发报告

- [本次实际开发汇报](work-reports/20260905T062046Z-work-report-delivery-88e2cf13/20260905T062046Z-final-016cdb/report.md)：由当前 main 生成、独立 Judge 评审，check 和 finalize 均通过。该目录按用户约定不跟踪。
- [受限权限复测记录](/home/alex_mercer/projects/_artifacts/agent-tools/codex-work-report-skill/restricted-check/result.json)
- [机器验证摘要](/home/alex_mercer/projects/_artifacts/agent-tools/codex-work-report-skill/verification.json)
- [真实 Judge 校准摘要](/home/alex_mercer/projects/_artifacts/agent-tools/codex-work-report-skill/calibration-results.json)
- [新会话原始事件](/home/alex_mercer/projects/_artifacts/agent-tools/codex-work-report-skill/acceptance/session.jsonl)
- [新会话最终答复](/home/alex_mercer/projects/_artifacts/agent-tools/codex-work-report-skill/acceptance/session-final.txt)
- [渲染检查截图](/home/alex_mercer/projects/_artifacts/agent-tools/codex-work-report-skill/render-check/preview.png)

上述是本机路径，不是可跨设备访问的公开链接。源码可以按项目习惯跟踪；报告与过程证据不会自动进入 commit。
