# Evidence packet for a synthetic manuscript exercise

This packet defines fictional but fixed observations for evaluator-controlled writing exercises. No experiments in this file were executed by the PRD-writing task. Generated drafts must remain labeled as fixture drafts and may not be submitted as real results.

## Project and method

The project tests whether reading final consumed configuration values can detect selected experiment-setup mistakes. A checker compares a supplied agreement with observed values at the consumer. It does not evaluate overall learning quality.

## Supplied observations

Three local, CPU-only cases each contain one deliberately injected mismatch:

1. The agreement requires K=4 candidates per generator; the consumer observes K=1.
2. The agreement requires an 8192-token response cap; the configuration instead applies 8192 to prompt plus response.
3. The agreement requires integer-answer normalization; the scorer rejects "007" when the reference is "7".

In the stipulated fixture results, the checker detects all three mismatches. A comparator that checks only whether the program exits successfully flags none of the three, because all three programs exit successfully.

## Not measured

No GPU training, downstream model accuracy, production deployment, researcher productivity, or long-term reliability was measured. No statistical generalization is supplied. No claim that the approach is the first of its kind has been researched. The material includes no real bibliography.

## Requested writing boundary

A draft can describe the bounded problem, mechanism, observed fixture outcomes and missing validation. A proposal can suggest a budgeted future evaluation. It cannot turn a proposed experiment into a completed result or invent literature references.
