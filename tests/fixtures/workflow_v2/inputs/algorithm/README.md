# Local reference experiment

This repository is a CPU configuration demonstration, without a learning loop.
`python3 launcher.py --effect effect.json` emits actual process observations and
optionally writes an execution receipt. `--config` and `--override` select JSON
files; the override takes precedence.

The reference baseline draws four responses for each enabled source. Its output
budget is 8192 tokens, in addition to a 1024-token prompt, within a 16384-token
context capacity. The reference critic starts with the two local weights in
`reference_critic.json`. The reference reward assigns one point for a correct
answer and zero for an incorrect answer, without a length adjustment.

The example launcher currently uses `config.json` and `override.json`. Read the
consumer to see the meaning of each input. A toy response consists of a repeated
integer token; the token list is counted in the consumer instead of relying on
the requested limit. The critic uses a two-dimensional feature vector. No
checkpoint downloads or external API calls occur.
