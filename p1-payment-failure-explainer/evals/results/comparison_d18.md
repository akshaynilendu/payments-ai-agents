# D18 comparison: majority of 3 judge passes, fair reference

| slice | system | cases (judged) | accurate | actionable | safe | code safety failures | avg cost / case | max latency | unanimous |
|---|---|---|---|---|---|---|---|---|---|
| in the table | baseline, table text (D18 fixes) | 32 (30) | 70% | 80% | 93% | 0 | $0.00000 | 0.00 s | 84/90 |
| in the table | baseline, table text (before D18), for reference | 32 (30) | 70% | 83% | 87% | 0 | $0.00000 | 0.00 s | 81/90 |
| beyond the table | baseline (escalate-only) | 14 (13) | 15% | 0% | 100% | 0 | $0.00000 | 0.00 s | 39/39 |
| beyond the table | Haiku 4.5 (before D18), for reference | 14 (13) | 54% | 38% | 100% | 0 | $0.00175 | 5.31 s | 29/39 |
| beyond the table | Haiku 5.5 (before D18) | 14 (13) | 85% | 54% | 100% | 0 | $0.00024 | 3.61 s | 36/39 |
| beyond the table | Haiku 5.5 + family runbook (D18) | 14 (13) | 62% | 77% | 62% | 0 | $0.00031 | 4.97 s | 37/39 |

Runs: baseline-20261019-200504, baseline_intable_fair-20261019-194114, baseline-20261019-194706, haiku45_rank-20261019-194927, haiku55_rank-20261019-195153, haiku55_rank-20261019-200918
