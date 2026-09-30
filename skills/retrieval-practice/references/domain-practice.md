# Practice by domain

Choose the exercise from the capability the learner wants to retain. Domain methods share attempt tracking and feedback, not a universal question template or mandatory mixture. Work with inspected evidence and preserve its version or source locator.

| Domain and objective | Useful task | What to assess |
|---|---|---|
| Paper: problem and motivation | Reconstruct the failure of a baseline and the constraint the method addresses | Whether the problem is clear without merely repeating the abstract |
| Paper: contribution and evidence | Compare the new method with a prior approach; identify which ablation distinguishes the explanations | Whether the claimed novelty and strength of inference fit the evidence |
| Code: task decomposition | Break one actual request into responsibilities and locate the interfaces between them | Whether each responsibility has an owner and the interfaces carry enough information |
| Code: module decoupling | Predict which modules change when a backend or requirement changes; identify a dependency that leaks across the boundary | Whether the learner understands coupling and change propagation |
| Code: architecture and state | Assign decision, execution, state, and resource ownership in a concrete case | Whether the roles and invariants are separated correctly |
| Code: control flow | Reconstruct a trace or predict behavior after a timeout, duplicate event, cancellation, or reordered operation | Whether sequencing, branches, recovery, and completion follow the actual implementation |
| Code: engineering trade-offs | Choose between two plausible designs under changed latency, scale, consistency, or maintenance constraints | Whether the choice follows constraints and acknowledges its costs |
| Tool use | Complete a bounded operation or diagnose a provided failed command/configuration | Whether the learner can act and verify the result, with assistance recorded |
| Writing | Choose, repair, or produce a claim with appropriate evidence and qualifications | Whether the response demonstrates recognition, local revision, or independent composition |

For code learning, replace filename-recall quizzes with an executable or inspectable question: “If producer and consumer share this mutable object, what can go wrong?” may matter more than “What is the class called?” A source lookup can test evidence-finding, but it does not establish unaided recall. A correct predicted trace is not a test run.

Examples may use code snippets, a partial call trace, a diagram to repair, a failing test, or a small proposed patch. State whether source access, hints, execution, or an agent are allowed. Creating a code-learning exercise does not authorize modifying production code or launching jobs. If the learner delegates the whole answer back to the agent, record assisted study rather than independent performance.

Vary the case on later review so repetition asks the learner to recall or apply the principle. Reuse the underlying ability and evidence instead of inventing an unrelated quiz each time. A short discrimination task is useful when effort is low; move to reconstruction or application when that is the intended capability. Do not require every session to pass through every format.
