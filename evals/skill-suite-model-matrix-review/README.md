# H01 清理处置评分澄清

这是测量修订，不改变题目难度、用户提示、fixture、目标 skill 或任何被测输出。原题已经要求仅清理确实废弃的材料；fixture 标明 v2 draft 仍有未决评审。旧 Judge 两次都识别草稿没有弃用依据，却一次在主项扣分、另一次仅在交接项扣分，评分范围不一致。

本修订要求 H01.1 覆盖所有实际处置。未完成或未交付不意味着废弃；无弃用依据、也没有等价替代保留地删除仍在评审的 draft，主项应为 false。接受内容与状态可恢复、相关引用同步更新的等价迁移，不要求原路径，不要求增加文档。其余检查仍沿用原规则；H03/H08/H09 沿用 reviewed_challenge_v3 的既有修订。

统一范围为四个被测模型、两组、各两次，共 16 条 H01 输出，不能只重评暴露问题的样本。使用固定 Judge gpt-6.1-sol；这不是人工偏好标注或被测模型重跑。先用独立 good / bad / 等价迁移样例校准，再由主线程启动重评。

## 入口

每个模型的 challenge 目录独立处理，避免模型混入同一评分目录：

```bash
python3 evals/skill-suite-model-matrix-review/reviewed_h01.py score \
  --runs "$MODEL_CHALLENGE/runs" --output "$MODEL_CHALLENGE/scored" \
  --cases H01 --model gpt-6.1-sol --workers 2
python3 evals/skill-suite-model-matrix-review/reviewed_h01.py report \
  --runs "$MODEL_CHALLENGE/runs" --scored "$MODEL_CHALLENGE/scored" \
  --output "$MODEL_CHALLENGE/report-h01-review" --reps 2
```

评分文件名包含 identity，因此同一 scored 目录会保留旧分并新增 H01 修订分；也可使用独立目录，但报告目录须能读取其余题的原评分。不要覆盖旧报告。score 和 report 使用同一 H01 identity，旧 H01 分不会作为新分静默复用；其余九题 identity 完全不变。summary.json 与 measurement-corrections.json 记录修订范围。

```bash
python3 -m unittest discover -s evals/skill-suite-model-matrix-review -p 'test_*.py' -v
```

离线测试验证 identity 范围、未修改输入、继承的 rubric、迁移允许条款和报告绑定；它们不代替独立 Judge 校准，不声称已经测得模型评分准确率。
