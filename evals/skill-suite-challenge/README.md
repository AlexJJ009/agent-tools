# Skills 原子能力挑战

这组新题回应首轮题目偏浅的问题：固定 10 道更难的合成题，每个目标 skill 两道。
每题 skills/control 使用相同模型请求、输入、工具与共同写作规范，只在 skills 组提供目标 skill。
两组均获得必要的只读参考资源，不把其他 skill 的完整指令或目标 skill 的元数据放进 control。
题目在本轮模型输出前固定，不根据模型输赢调整期望答案。

## 每题具体区分什么

| 题目 | 目标 skill | 主能力与困难来源 |
| --- | --- | --- |
| H01 | cleaner | 判断材料真实用途：配置动态加载的数据看似临时；唯一证据和旧 final 仍需保留，新 draft 不能替代；真正过时 probe 应清除 |
| H02 | cleaner | 抽取实际重复，保留相似函数的语义差异；Unicode casefold 与 lower 不是同一行为 |
| H03 | teaching-reconstruction | 追踪共享对象副作用；赋值没执行不代表 cache 没变化，必须解释闭包与可变列表 |
| H04 | teaching-reconstruction | 在 README、旧版日志与当前源码冲突时，按版本及异常类型界定结论 |
| H05 | retrieval-practice | 针对浅拷贝误解出题，同时区分嵌套对象共享和顶层键重新绑定，不能复述定义 |
| H06 | retrieval-practice | 针对“finally 总吞异常”生成有区分度的双函数判断，控制 close 自身是否抛错的歧义 |
| H07 | task-routing | 最新只读请求覆盖旧修复任务和来源模板，同时仍完成实际定位 |
| H08 | task-routing | 从多轮修订恢复CSV导入完整契约：保留id前导零、追加region、覆盖输出，再解释和同步schema/usage；旧prototype不能覆盖现行要求 |
| H09 | learning-artifact-compiler | 在原文定点补上求值前提和反例，保护已有正确段落，而非只改结论或重写全文 |
| H10 | learning-artifact-compiler | 把观测、尝试次数、重试次数和程序保证分开，修订材料的论证范围 |

`primary_check_id` 指向每题的主检查，单独统计它的配对结果；其他检查保护行为、来源或任务边界。
所有题仍要求真实完成相应请求：清理不能只提建议，修复不能只说成功，练习不能先给答案。
主检查是一个能力判断，可能有多个证据条件；它不是多项互不相关任务的混合总分。

## 输入、答案和评分边界

`fixtures.files` 是被测端文件，`prompt/turns` 是真实执行时的输入；多轮历史是合成上下文，不计为本次模型产出。
`checks` 和 `grader_side` 只在评测端使用，不能注入被测环境。后者保存一种可接受的 oracle 文件操作或明确的 null，
以及已知正确、错误回答和必要观察。null 表示这是解释/出题/只读任务，没有固定文件补丁，不表示没有可判定标准。
正确答案允许其他实现和措辞；oracle 不是要求逐字匹配的模板。

程序判分关注文件、行为和保护义务；语义 Judge 判断因果解释、题目区分度和任务选择。
写作分与主能力分分开，不用“看起来流畅”替代语义正确或必要前提。
已知正确/错误例用于校验评分器，不能用于引导被测 Agent；用户无需人工标记。

这仍是每题两组各两次的小样本，能发现反例与局部差异，不足以证明稳定增益、真实大仓库清理能力或学习收益。
如果设施或评分器出错，保留原记录，修复后重新执行或评分；不得为了让目标 skill 获胜而更改输入和判分。
原 pilot 文件保持独立；本目录只保存本组挑战定义，运行产物另存。

## 隔离运行与迭代

每轮先提交题目、评分器与运行器；固定源文件及被复制资源的哈希，再运行：

```bash
python3 evals/skill-suite-challenge/run_challenge.py --output /absolute/external/run-dir --reps 2 --workers 3 --model gpt-5.5 --effort medium --timeout 420
python3 evals/skill-suite-challenge/score_challenge.py --runs /absolute/external/run-dir --output /absolute/external/score-dir
python3 evals/skill-suite-challenge/report_challenge.py --runs /absolute/external/run-dir --scored /absolute/external/score-dir --output /absolute/report-dir --reps 2
```

每题两组各两次，共 40 个被测试次；同题内按 skills/control、control/skills 顺序交替。
每个试次都有独立临时 HOME、工作目录和 runtime 数据；bubblewrap 不挂载真实用户目录、项目或评分器。
被测工具不能访问网络，只有受信 CLI 保留订阅连接；认证临时副本运行后删除。

本轮寻找可以复现、可以解释的缺口，不把更低通过率当成成功。若两组仍都通过，该题不提供 skill 增量证据；
若出现缺口，检查源码、实际读取、执行轨迹和最终产物，区分题目/评分设施错误与被测行为错误。
后续验证题单独定稿、提交和运行；不修改已运行题目的期望答案来制造 skill 优势。
评分器先用正确、错误、空回答校准；这属于合成样例校验，不等于真人偏好验证。
