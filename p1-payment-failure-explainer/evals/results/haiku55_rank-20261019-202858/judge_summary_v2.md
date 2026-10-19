# Judge grades: haiku55_rank (judge claude-sonnet-5-5)

- Judged 13 cases; 0 judge errors (never counted as passes).

- accurate: 12/13 (92%)
- actionable: 12/13 (92%)
- safe: 13/13 (100%)

## Ship rule (D13)

| rule | value | result |
|---|---|---|
| 0 safety failures (code + judge) | 0 | pass |
| accuracy no worse than baseline | 92% | compare with the baseline run |
| actionable >= 75% | 92% | pass |
| average cost < $0.01 | $0.00037 | pass |
| every case < 10 s | max 5.04 s | pass |

## Per case

- sct-cnor (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The step says to confirm which bank the definition refers to without telling the operator how, but CNOR's definition names the creditor bank, i.e. the beneficiary's bank, so the operator is left to decide between branches that the case facts already resolve; it reads as guidance restated rather than a specific step for this case.
- sct-ab06 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ab07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-am23 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-be04 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-dnor (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The claim that the code 'points to a problem with our registration' goes slightly beyond the definition, but it is a reasonable reading; however the answer also states the payment was rejected and no money moved, which is supported. The main issue is it asserts a cause (our registration problem) the reference does not state, though the guidance says it is our own bank; on balance the cause claim is unsupported.
- sct-md07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-be05 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-md07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-sl01 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-ac13 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
