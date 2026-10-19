# Beyond the table: D18 vs D19 (majority of 3 judge passes, fair reference)

| system | cases (judged) | accurate | actionable | safe | code safety failures | avg cost / case | max latency | unanimous |
|---|---|---|---|---|---|---|---|---|
| baseline (escalate-only) | 14 (13) | 15% | 0% | 100% | 0 | $0.00000 | 0.00 s | 39/39 |
| Haiku 5.5 before D18 | 14 (13) | 85% | 54% | 100% | 0 | $0.00024 | 3.61 s | 36/39 |
| Haiku 5.5 + family runbook (D18) | 14 (13) | 62% | 77% | 62% | 0 | $0.00031 | 4.97 s | 37/39 |
| Haiku 5.5 + D19 texts and word check | 14 (13) | 92% | 92% | 100% | 0 | $0.00037 | 5.04 s | 36/39 |

New run: haiku55_rank-20261019-202858
