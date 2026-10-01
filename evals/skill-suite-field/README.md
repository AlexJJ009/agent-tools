# 现场维护与自然触发评测

本目录补充六个现场场景，与已有19题分别保留数据，再按问题类别比较。题目与边界见 [CASES.md](CASES.md)，解释规则见 [TAXONOMY.md](TAXONOMY.md)。不修改目标 skill，不测长期学习效果。

从工作树根目录运行，输出必须在源码工作树外：

```sh
python3 evals/skill-suite-field/evaluate.py plan --output /absolute/field-output
python3 evals/skill-suite-field/evaluate.py calibrate --output /absolute/field-output --workers 6
python3 evals/skill-suite-field/evaluate.py run --output /absolute/field-output --workers 6
python3 evals/skill-suite-field/evaluate.py score --output /absolute/field-output --workers 6
python3 evals/skill-suite-field/evaluate.py report --output /absolute/field-output
```

默认四模型为 gpt-6.1-sol、gpt-6-sol、gpt-5.6-sol、gpt-6-luna；每题有/无目标 skill 各两次，共96个位置，medium、420秒。固定评分器为 gpt-6.1-sol、medium、300秒。`--models` 和 `--cases` 可选子集；完整汇总时不加筛选。运行通过本机 Codex CLI 的 ChatGPT 登录，不改真实配置。

`run` 复用已成功试次，不因低分或未观察到读取而重新抽样，超时也保留。确认属于基础设施错误后，可用相同命令加 `--retry-infra` 追加失败位置的 attempt。`score` 可重新执行，已成功的同身份评分复用。`plan` 冻结代码、输入、资源和协议；漂移必须使用新的输出目录，不能覆盖旧清单。不要同时启动相同输出目录的两个入口。

F03–F06 仅提供可发现元数据，没有强制目标调用指令；F03/F04 两组均拥有 retrieval-practice。完整正文在工具输出中出现是诊断，不是通过条件，也不等于内部注意或真实触发的完整记录。判分器看到实际指令上下文，因此不是完全盲评；同一固定标准用于所有组，不隐去已有指令后再把其来源说明当错误。

校准的18个正确/错误/空样例只预设主项期望，不声称约束与写作全维已校准。首次运行中18个主项均匹配；F01正确清理样例的验证状态措辞被判不清楚，不能将此二级扣分说成虚构测试、越权或清理失败。

分类汇总保留每题和每模型的分母，不合成总能力分：

```sh
python3 evals/skill-suite-analysis/classify.py \
  --old /absolute/old-summary.json \
  --field /absolute/field-output/report.json \
  --output /absolute/classified-report
```

`CLASSIFIED_RESULTS.md` 展示25题的主项、约束、写作与读取诊断，`classified.json` 保留逐条证据路径。旧超时造成的质量配对排除会使分类入口返回2；这不等于新试次没有运行完。旧写作盲评上下文问题及方法性扣分仍保留标注，新旧不同题目、不同评分上下文不能当成前后提升。
