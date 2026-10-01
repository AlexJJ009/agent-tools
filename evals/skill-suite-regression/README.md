# 合并后 skills 完整回归

复用上一轮最终的 25 题、四模型、两组、两次重复，共 400 个试次。题目、校准样例、评分规则均不改变；challenge 统一使用最终 H01 修订入口（其余题继承最终 v3），避免回退到旧主项口径。结果只输出逐题结构数据，不将旧分类器中针对某次样本的发现套到新产物。

先把 eval 分支合入已在远端 main 合并的提交，提交全部评测源码修复，保持工作树干净。所有动作使用同一个新目录，不复制旧 runs、grades 或 manifest：

```bash
python3 evals/skill-suite-regression/evaluate.py plan --main-commit MERGED_SHA --output /home/alex_mercer/projects/_artifacts/agent-tools/codex-skill-eval-design/regression-20261001-wording
python3 evals/skill-suite-regression/evaluate.py calibrate --main-commit MERGED_SHA --output /home/alex_mercer/projects/_artifacts/agent-tools/codex-skill-eval-design/regression-20261001-wording --workers 6
python3 evals/skill-suite-regression/evaluate.py run --main-commit MERGED_SHA --output /home/alex_mercer/projects/_artifacts/agent-tools/codex-skill-eval-design/regression-20261001-wording --workers 6
python3 evals/skill-suite-regression/evaluate.py score --main-commit MERGED_SHA --output /home/alex_mercer/projects/_artifacts/agent-tools/codex-skill-eval-design/regression-20261001-wording --workers 6
python3 evals/skill-suite-regression/evaluate.py report --main-commit MERGED_SHA --output /home/alex_mercer/projects/_artifacts/agent-tools/codex-skill-eval-design/regression-20261001-wording --workers 6
```

`merged-main-skills.json` 直接对指定 Git commit 的全部 skill 文件字节取 hash。启动前核对当前源码；每次安装后、模型调用前再次检查完整包及共同参考资源，证据保存在 raw 的 `skill_setup.merged_main_copy_audit`。发现多余、遗漏或旧文件立即阻止调用。读取根目录基于当前脚本路径，避免已安装用户级 skills 或旧工件内脚本的绝对路径指向旧代码。

`regression-manifest.json` 记录 main SHA、eval SHA、25 题 hash、继承源码和二进制 hash。只缓存完全相同的 manifest 内容；每任务检查 stat，批前批后完整校验文件字节和清单，漂移将写 `INVALIDATED.json` 并停止。新结果保存在 `matrix/` 和 `field/`，旧目录保持不变。

成功结果（即使质量不合格）及预算超时不重抽。网络或服务容量中断可保留 attempt 后重试；未分类失败要求先审查。`--infra-retries` 默认 2 表示首轮之后最多再恢复两轮，仍有失败时返回非零，可核查网络后继续同目录。评分成功的同 identity 结果缓存；评分器失败可重试 `score`，不重跑 subjects。底层 matrix 评分入口会因保留的 subject timeout 返回非零；此调度器将它与 Judge 失败分开记录，报告仍要求每个成功试次都有有效分数。

输出 `structural-results.json`、各 suite 报告和 field/report.json。报告保留执行失败、题目/模型/组别分母、正文读取诊断；不同能力不合成总分。新旧对比须区分共同辅助 skills 也发生改变的情况，不能把整个版本的变化都归因于单个目标 skill。
