# 最终汇总与完成率审计

`finalize.py` 不运行模型、不改原始产出、不覆盖原报告。它在独立 view 目录引用原 manifest、校准和选定报告：challenge 使用各模型的 `report-h01-review`，另外三套使用原 `report`。质量表继续由冻结的 `summarize.export` 生成。

运行方式（先等全部评分与分报告生成）：

```sh
python3 evals/skill-suite-model-matrix-review/finalize.py \
  --source /absolute/path/model-matrix-20260930-v2 \
  --view /absolute/path/final-view \
  --output /absolute/path/final-report
```

输出包括 `RESULTS.md`、保留原质量 `complete` 含义的 `summary.json`，以及 `completion-audit.json`。路径保留原始绝对位置；模型顺序固定为 gpt-6.1-sol、gpt-6-sol、gpt-5.6-sol、gpt-6-luna。

执行分母固定为 304 个实验位置。每个位置取数字最大 attempt，旧失败只保留数量与原因，不增加分母。完成、超时、其他错误和缺失分别统计；每模型每题另有两组完成、仅 skills 完成、仅 control 完成、两组未完成四格。超时不是质量 false，质量分母仍是原报告的有效配对数。因此质量比较是条件于完成且配对有效的子集，存在选择偏差，不能替代全部分配任务上的完成率。

`evaluation_run_complete` 表示每个位置都已尝试，最新尝试只剩完整输出或超时，且每个完整输出都通过原始数据、题目、当前评分器及固定 judge 的身份核验；错误、缺失、协议不符或缺评分都会阻止它为真。它不表示所有任务完成，更不表示 skill 有效。`delivery_ready` 另要求临时 auth 文件残留为零、H01 修订校准为 4/4。文件残留审计只统计认证文件，不读取内容。原质量汇总和各分报告的 `complete=false` 不会被改为真。

H01 修订在独立评分目录中核查所有实际清理处置，包括仍在评审的唯一 draft；不改变被测输入或原输出。4/4 预设好坏校准与期望一致只是评分器局部校准，不能保证真实输出无误判。最新与历史 attempt 的模型、预算、manifest 协议检查结果都保留，已修复的历史基础设施错误不当作新的实验位置。
