# L40 verl/DPO Expansion Validation

Checked at: `2026-05-03T16:06:05+00:00`

| Check | Source | Source value | DB value | Result |
|---|---|---:|---:|---|
| `minirl_2z_sft_step275_math500` | `/data-1/model_weights/MINIRL-Qwen3-4B-MATH-2Z-SFT/step_275/inference_n3/eval_metrics.json` | 0.796 | 0.796 | PASS |
| `minirl_2z_sft_step300_aime` | `/data-1/model_weights/MINIRL-Qwen3-4B-MATH-2Z-SFT/step_300/inference_n3/eval_metrics.json` | 0.13333333333333333 | 0.13333333333333333 | PASS |
| `wdl_2a_sft_step275_aqua` | `/data-1/model_weights/WDL-SFT-Qwen3-4B-MATH-2A-SFT/step_275/inference_n3/eval_metrics.json` | 0.6627296587926509 | 0.6627296587926509 | PASS |
| `wdl_2a_sft_step300_amc` | `/data-1/model_weights/WDL-SFT-Qwen3-4B-MATH-2A-SFT/step_300/inference_n3/eval_metrics.json` | 0.6 | 0.6 | PASS |
| `dpo_wdl_code_ckpt39_lcb_rerun` | `/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1_rerun/eval_summary.json` | 0.155 | 0.155 | PASS |
| `dpo_wdl_code_ckpt39_bcb_rerun` | `/data-1/checkpoints/qwen3-4b-base-code-wdl-v3-m1-ckpt39/eval_code_n1_rerun/test/eval_summary.json` | 0.27456140350877195 | 0.27456140350877195 | PASS |
| `online_m55_step300_acc` | `/data-1/verl07/verl/recipe/on_policy_wdl_sft/validation/WDL-SFT-Qwen3-4B-MATH-M5-5_1775980322/300.jsonl` | 0.6590038314176245 | 0.6590038314176245 | PASS |
| `online_m56_step400_score` | `/data-1/verl07/verl/recipe/on_policy_wdl_sft/validation/WDL-SFT-Qwen3-4B-MATH-M5-6_1776095760/400.jsonl` | 0.3065134099616858 | 0.3065134099616858 | PASS |
| `online_minirl_gc500_step695_acc` | `/data-1/verl07/verl/recipe/joint_training/validation/Baseline-MiniRL-Qwen3-1.7B-MATH-GC500_1773643860/695.jsonl` | 0.6175908221797323 | 0.6175908221797323 | PASS |
| `online_labelfix_step300_score` | `/data-1/wandb_runs/WDL-SFT-Qwen3-4B-MATH-2A-BASE-LABELFIX/wandb/offline-run-20260428_033322-kto2ukn2/files/media/table/val/generations_299_c2378f0c92b90925fb16.table.json` | 0.3371647509578544 | 0.3371647509578544 | PASS |
