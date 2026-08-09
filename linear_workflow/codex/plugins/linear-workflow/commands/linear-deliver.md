---
description: Execute one explicitly dispatched Ready Delivery Batch and stop at its merge approval boundary.
argument-hint: [Ready Linear Batch ID]
---

Use `$linear-deliver` for the supplied Ready Batch ID. Read the shared contract and live Linear/repository facts, execute only the Batch members in DAG order, bind CI and independent review to one candidate, and stop before merge unless a human explicitly approves it.
