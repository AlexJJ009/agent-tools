# Sources A, B and C for synthesis practice

All three source cards below are synthetic evaluation materials, not published studies. The numeric observations are stipulated fixture facts, not experiments performed by this migration task. They may be discussed within the exercise but must not be presented as real research evidence.

## Source A: More candidates under a larger budget

Question: Does a changed sampling configuration improve task accuracy?

Setup: The same base model and test set are used. Baseline generates one candidate with a 2000-token output cap per question. The changed configuration generates four candidates with the same per-answer cap. Both use scorer S to select an answer. Each configuration has one run.

Reported fixture observation: Accuracy is 40% for baseline and 44% for the changed configuration. No matched-total-budget run, uncertainty estimate, or diversity intervention is supplied.

Boundary: The comparison jointly changes candidate count and maximum output budget. It does not isolate diversity as a cause.

## Source B: Fixed budget with a changed generator

Question: Does a different candidate-generation procedure help under fixed sample and token limits?

Setup: Both conditions use four candidates, a 2000-token per-answer output cap, the same questions and scorer S. The changed generator increases a reported diversity indicator. Its candidate-quality indicator also changes. There is one run per condition.

Reported fixture observation: Accuracy is 42% versus 43%. The supplied material does not intervene on diversity independently of candidate quality and provides no repeat-run uncertainty.

Boundary: This controls the stated sample/output limits, but still cannot assign the difference specifically to diversity.

## Source C: Answer normalization changes scorer decisions

Question: Does representation normalization change answer-equivalence judgments?

Setup: A fixed set of 50 answer pairs is scored first by literal string equality and then by a rule that normalizes integer leading zeros. Examples include "007" and "7". Five pairs change from unequal to equal. The rule does not implement general LaTeX equivalence.

Boundary: This is a scorer study. It compares no training methods and reports no learning improvement. It shows why comparison conditions must include scoring rules.

## Task material boundary

The packet supports comparing question, conditions, evidence and limits. It does not establish that a new research question is globally novel. Candidate next experiments may be proposed as proposals with explicit missing evidence.
