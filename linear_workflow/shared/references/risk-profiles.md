# Risk profiles

| Profile | Planning admission | Delivery and review |
| --- | --- | --- |
| Fast | One clear Issue; Project PRD optional | targeted tests, one PR, existing required CI, lightweight review |
| Standard | Approved PRD or explicit parent; Ready Batch | per-Issue targeted checks, Batch full CI, independent review |
| High | Approved PRD plus applicable design/rollback evidence | exact candidate SHAs, full CI per repo, integration evidence for joint releases, independent review |

Risk controls verification depth, not implementation size. A cross-repository
Batch is rejected unless it is an indivisible High-risk release with one PR and
candidate evidence per repository. Missing verification must block delivery;
it does not authorize new platforms or broad test infrastructure.
