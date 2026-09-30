# Agent Tools skills 隔离试跑

本轮使用项目内的 BuildEval 运行 19 道合成题，检查启用当前 skills 后的具体行为。
用户已授权直接运行、修复评测设施问题后继续；评分采用程序检查和模型 Judge，不要求用户标记。
源代码基线是 `168906a4e4471a814a15a3a851cebcc6093c4005`。题目文件不保存执行成绩；实际结果以运行产物为准。

## C05 具体测什么

用户反馈的是“找不到需要清理的东西”，之前把它扩大成“查找并修复关键问题”不准确，已修正。
C05 现在提供一个功能已完成的小仓库，请 Agent 自主检查并清理，没有在请求里列出待删文件。
仓库中有无人调用的重复函数、明确已被新实现替代的试验脚本及输出；同一 scratch 目录也有活跃测试读取的数据。
另有未决问题笔记和禁止修改的登录模块。通过条件是完成有依据的清理、保留活跃及未决材料，并验证行为保持。

这让“自主发现清理项”变成可观察结果：是否删除已无用途的内容、是否误删仍有用途的内容、是否保持行为、是否给出可继续工作的交接。
它仍然只是固定小仓库测试，不能代表复杂真实仓库中的清理能力。

## 题目与 skills 的关系

完整输入及评分条件见 `REVIEW.md`，机器可读定义见 `cases.json`。每题的 `target_skills` 指明加载哪些技能，
`skill_association` 说明与技能的关系和归因限制，`execution` 写明状态准备及需要注入的项目规则。

| 题目 | 对应能力或技能 | 本轮能观察到什么 |
| --- | --- | --- |
| C01–C04 | task-routing、教学重建、学习材料 | 保持当前意图、避免误触发、完成多阶段请求 |
| C05、C11、C18 | cleaner | 自主发现清理项、清理与交接、按项目约定维护必要 ADR |
| C06、C07 | agent-workflow runtime 合约 | 从真实任务状态恢复、区分验证通过与用户验收；不是独立 skill 的效果 |
| C08–C10 | teaching-reconstruction | 解释完整性、代码机制、事实与未验证结论的边界 |
| C12、C14、C17 | learning-artifact-compiler | 修改原材料、离线完整交付、避免越权归档 |
| C13–C16、C19 | retrieval-practice 等 | 题目难度和呈现、答案时机、提示记录、练习触发 |

程序阅读、指令遵循和基本文件操作也属于模型本来的能力。单次启用 skills 的运行可以发现当前配置的失败，
不能证明某项成功由 skill 带来。测增量需要另跑同模型、同题、同工具预算的无目标 skill 对照。
本轮把目标技能列入可用目录，由 Agent 选择读取；单独记录实际读取证据，不把文件存在当作已加载。目录是针对题目准备的，不能由此推断日常完整技能列表下的自动发现可靠性。
这些也不是 Agentic RL 训练实验，不能推出奖励有效、训练改善或真实用户学习进步。

## 怎样隔离和运行

实验 worktree 隔离开发改动，但单独的 worktree 不能限制同一用户读取其他目录。
执行端需要为每题准备全新 Git 仓库、HOME 和 runtime 数据根，并通过工具运行边界只暴露当前题所需材料、技能及依赖。
不能让被测 Agent 读到 `cases.json`、checks、评审答案、其他题输出或宿主用户的真实任务库。

普通题的文件由 `fixtures.files` 原样生成。C06/C07 要在隔离数据根通过真实 task runtime 创建状态，
不能仅放一个 JSON 就宣称测试了 runtime；如果该设施不能建立，应修复设施或明确列为基础设施失败。
C18 的项目 ADR 约定必须实际注入。多轮题的 `turns` 包含合成历史，运行产物只算最后请求后的实际执行。
被测代码如需修改，应留在每题目录；评测脚本修复留在实验分支，不顺手修改被测 skills 来追分。

C11 要区分初始文件、运行中新生成文件和最终保留文件。只有首尾快照时只能判断最终状态，不能声称从未生成过过程材料。
实际 runner 使用 Linux bubblewrap 文件系统白名单和 Codex workspace-write 沙箱。真实探针确认宿主 HOME、源码题库不可读，工具直接出网得到 EPERM；CLI 本身保留订阅连接。认证副本只在临时 profile 内使用并于结束后删除，受信 CLI 环境内可读。

C11 通过外部 inotify 记录 workspace/runtime data 的文件事件，并保存首尾快照。新目录观察有竞态，不能把未观察到某个短暂文件写成绝对没有生成。其他题仅保存首尾快照与 CLI 轨迹。隐藏行为检查在最终 workspace 的副本中执行，不修改原始产出。

全局 hooks、真实项目历史、外部服务和个人记忆不注入；目标 skill 的依赖也可能被原生 discovery 发现，实际安装清单与指令哈希保存在每次结果里。这里只测这一明确配置。

## 怎样直接评分

程序检查实际文件变化、受保护内容、行为测试及状态，不能用 Agent 自述“完成”代替。
模型 Judge 判断解释是否准确、是否守住任务边界、练习是否在当前回复中可见可答，以及是否遵循共同写作规范。
写作评分关心结论和证据是否清楚、风格与当前请求是否匹配、何时应触发讲解或练习；不强制固定篇幅或标题。
这些语义评分没有经过真人偏好校准，应保留证据与不确定性，但不要求用户补标签。
旧版 `user_preference` 字段保持空值只是兼容旧格式，不影响评分。

分别呈现四类流程及逐题检查结果，不用一个总分掩盖清理、教学和任务恢复的差异。
环境故障、输出截断、评分器失败与被测行为失败分开；设施修复后的重跑保留原失败记录。
候选来源包括仓库合成规则题、历史场景改编及本聊天反馈；没有复现 PHAI 或 read paper 的真实故障。
知识先修 DAG 暂无对应题；真实大仓库清理、完整运行时恢复故障、长期学习收益也不在本轮覆盖内。

## 本机复跑

需要 Linux/WSL 的 `bwrap`、现有 Codex ChatGPT 登录、系统 Python 和 Node。C11 的 pytest 及依赖由现有本机 uv 缓存离线复制，缺失时报环境错误，不自动改宿主安装。当前实现是本机 pilot runner，尚不是跨平台安装器。

在本实验 worktree 中执行，运行目录必须是源码 checkout 之外的新绝对路径：

```bash
python3 evals/skill-suite-pilot/run_eval.py --cases all --variant skills --reps 1 --workers 2 --model gpt-5.5 --timeout 420 --output /absolute/pilot/runs
python3 evals/skill-suite-pilot/run_eval.py --cases C05,C08,C17,C19 --variant control --reps 1 --workers 2 --model gpt-5.5 --timeout 420 --output /absolute/pilot/runs
python3 evals/skill-suite-pilot/score_runs.py --runs /absolute/pilot/runs --output /absolute/pilot/scoring --workers 2
python3 evals/skill-suite-pilot/export_results.py --runs /absolute/pilot/runs --scored /absolute/pilot/scoring --output /absolute/pilot/reports
```

control 保留相同写作规范、工具与题目，移除技能包。四道对照只用于检查题目有无初步区分度，不估计整套 skills 的平均收益。运行前先用评分器的正确/错误/空回答样例校验，程序检查用 `python3 -m unittest discover -s evals/skill-suite-pilot -p 'test_*.py'` 验证。

导出器默认期望 19 道 skills 题和上述 4 道 control 各一次。未完成或评分版本过期会明确列出并返回非零；不同 rep/对照集合需要调整导出参数或调用函数。旧 attempt 保留，但每个题目/配置/rep 只采用最后一次有效试跑；环境修复后的重跑不作为额外独立样本。

C05 试跑曾出现等价数据迁移被过严评分拒绝，评分器已改为检查实际消费者和破坏性负控，不锁定路径或测试代码 AST。原始产出不变，旧评分失效并重新评分。被测 skills 本轮没有改动。
