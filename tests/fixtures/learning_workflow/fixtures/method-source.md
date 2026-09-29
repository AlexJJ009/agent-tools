# Source M: Budgeted multi-source sampling

This is an original synthetic evaluation source. It is not a published paper and reports no real experiment. The evaluator must preserve this label when presenting it as a paper-shaped reading fixture.

## Problem and motivation

A training pipeline generates candidate answers for each question. Using only one generator can produce very similar answers. A second generator may offer different candidates, but it also changes cost and possibly answer quality. The proposed mechanism separates per-source candidate allocation from answer scoring so the two choices can be inspected independently.

## Method definition

There are two generators, G1 and G2. For each question, each generator produces K=4 candidates: eight candidates in total. K means candidates per generator, not total candidates. Each answer has an output limit of 8192 tokens; this number does not include prompt tokens. Actual token use can be smaller.

The pipeline applies the same supplied scorer to every candidate. It retains one candidate with the highest score; ties are resolved by generator index, then candidate index. The retained candidate becomes the training target. No claim is made here that this target is correct merely because its score is highest.

## What can and cannot be inferred

Compared with a baseline generating four candidates in total, this mechanism changes both candidate sources and candidate count. Such a comparison cannot isolate the effect of source diversity. A budget-matched comparison would need to hold candidate count and relevant compute/output conditions fixed and inspect scorer behavior.

No training run, accuracy measurement, cost measurement, or author discovery diary is supplied. A teaching reconstruction may propose why the mechanism is plausible, but must label its reasoning separately from source statements.

## Stable locators

Use the section headings above as locators for text-only evaluation. For a disposable Zotero-backed test, render these exact bytes to a PDF, seed only the authorized test library, and record the actual parent/attachment keys, generated PDF digest, and page mapping at run time. Do not invent library keys or cite this fixture as real published research.
