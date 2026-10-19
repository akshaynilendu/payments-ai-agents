# D17 comparison: majority of 3 judge passes, fair reference (the passages the AI is given)

| slice | system | cases | accurate | actionable | safe | code safety failures | avg cost / case | max latency | judge stability |
|---|---|---|---|---|---|---|---|---|---|
| in the table | baseline (table text, fair-graded) | 32 (30 judged) | 70% | 83% | 87% | 0 | $0.00000 | 0.00 s | 81/90 unanimous |
| beyond the table | baseline (escalate-only) | 14 (13 judged) | 15% | 0% | 100% | 0 | $0.00000 | 0.00 s | 39/39 unanimous |
| beyond the table | haiku45 | 14 (13 judged) | 54% | 38% | 100% | 0 | $0.00175 | 5.31 s | 29/39 unanimous |
| beyond the table | haiku55 | 14 (13 judged) | 85% | 54% | 100% | 0 | $0.00024 | 3.61 s | 36/39 unanimous |

Runs: baseline_intable_fair-20261019-194114, baseline-20261019-194706, haiku45_rank-20261019-194927, haiku55_rank-20261019-195153
