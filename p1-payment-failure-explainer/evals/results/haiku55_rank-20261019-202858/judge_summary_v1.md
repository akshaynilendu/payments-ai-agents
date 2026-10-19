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

- sct-cnor (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ab06 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ab07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-am23 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-be04 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-dnor (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The claim that the code 'points to a problem with our registration' goes beyond the reference, which says only that the debtor bank is not registered under this BIC in the CSM, though the debtor bank being our own bank follows from the case facts.
- sct-md07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-be05 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-md07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sdd-sl01 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step only says to have a person triage manually and escalate if the code recurs, so an L1 operator is not told what to check or do for this case and would need to ask someone.
- sdd-ac13 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
