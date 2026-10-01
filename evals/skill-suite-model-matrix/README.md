# 固定题目的四模型复跑

本轮沿用已经提交的四套 19 题，不根据新模型的表现改题。每题都有 skills/control 两组，每组重复两次；四个模型各 76 个试次，总计 304 个。

被测模型仅允许 `gpt-6.1-sol`、`gpt-6-sol`、`gpt-5.6-sol` 和 `gpt-6-luna`，统一 medium、每次 420 秒。固定 Judge 使用 `gpt-6.1-sol`，沿用既有 medium、300 秒预算和当前评分修订。不会自动换模型；CLI 不返回实际服务模型身份时，只记录请求值并保留未核验状态。

## 执行与恢复

先完成本目录代码、指标和汇总脚本并提交，再冻结运行：

```sh
python3 evals/skill-suite-model-matrix/evaluate.py plan --output /absolute/matrix-root
python3 evals/skill-suite-model-matrix/evaluate.py run --output /absolute/matrix-root --workers 6
python3 evals/skill-suite-model-matrix/evaluate.py score --output /absolute/matrix-root --workers 6
python3 evals/skill-suite-model-matrix/evaluate.py report --output /absolute/matrix-root --workers 6
```

同一入口可重复执行。执行错误产生新 attempt；已有成功试次按原 runner 的模型、预算、题目和资源哈希复用，能力低分或未读技能不会触发重新抽样。评分使用有效 identity 缓存。全局冻结清单拒绝继承源码、题目、skill 资源及 CLI 二进制的漂移；需要改变这些条件时使用新的输出目录。

可用 `--models gpt-6-luna`、`--suites mechanisms`、run 阶段的 `--cases L01,L02` 选取子集。选取子集不改变总实验清单；未运行的题仍是缺失结果。每个模型、套件使用独立目录：

```text
matrix-root/
  matrix-manifest.json
  gpt-6.1-sol/
    challenge/{runs,scored,report,logs}/
    mechanisms/{runs,scored,report,logs}/
    source-discovery/{runs,scored,report,logs}/
    artifact-followup/{runs,scored,report,logs}/
```

调度按题目轮换模型起始顺序。每个 model/suite/case 内串行执行 skills/control、control/skills；最多同时运行六个 subject job，每个 job 一次只启动一个模型进程。同一输出目录的重复 run 入口有互斥锁。score 单独调度，最多六个 Judge 进程；若与 run 同时运行，会额外占用订阅额度。

L03 的两组独立任务 ID 必然不同，因此比较归一后的初始任务语义签名，不比较随机 ID。实际任务身份在各试次内部保持情况仍由原 runtime grader 检查。

## 评分与解释

challenge 使用 `reviewed_challenge_v3.py`，mechanisms 使用 `reviewed_mechanisms.py`，来源定位与材料修订跟进使用各自已冻结的 scorer。模型目录不混放；Judge 模型进入评分 identity。

既有报告仍提供“确认读取正文”的有效配对子集，未读取时可能返回 exit code 2。此信号不意味着 subject 没有执行完毕。矩阵汇总应同时呈现全部结构有效分配配对，以及其中观察到目标正文读取的子集，具体分母见 [METRICS.md](METRICS.md)。不得为了形成读取证据而重跑、选取更好的结果。

运行日志、原始轨迹、费用使用量、错误和产出文件均保存在外部输出目录。没有实际美元成本数据时不推算账单。外层文件隔离与临时认证副本清理由既有 runner 执行；此入口不修改真实 Codex 配置。
