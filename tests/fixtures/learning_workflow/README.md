# Learning workflow evaluation fixtures

`fixtures/` contains explicitly synthetic source packets and their SHA-256
manifest. `validation-cases.json` contains fixed requests and evaluator-only
behavioral expectations. They were preserved byte-for-byte from the migration
campaign; `not_run` fields describe that frozen specification, not current test
results. Keep acting-agent inputs separate from evaluator oracles.

See [material construction and scope](fixtures/README.md). Its reference to
`validation-cases.json` denotes the parent-level case file. Historical campaign
receipts, source snapshots, user feedback and pilot outputs are local task
records and are not prerequisites for running new bounded trials. Passing local
unit tests does not establish native-host behavior or library integration.
