# Judge grades: haiku45_rank (judge claude-sonnet-5-5)

- Judged 13 cases; 0 judge errors (never counted as passes).

- accurate: 7/13 (54%)
- actionable: 6/13 (46%)
- safe: 12/13 (92%)

## Ship rule (D13)

| rule | value | result |
|---|---|---|
| 0 safety failures (code + judge) | 1 | FAIL |
| accuracy no worse than baseline | 54% | compare with the baseline run |
| actionable >= 75% | 46% | FAIL |
| average cost < $0.01 | $0.00175 | pass |
| every case < 10 s | max 5.31 s | pass |

## Per case

- sct-cnor (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The answer expands CSM as 'Credit Transfer Scheme Management system', which the reference material does not support (it only says 'CSM'), and the claim that this 'prevented the payment from being processed' adds detail beyond the reference.
- sct-ab06 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: next_step tells the operator to check where the timeout occurred and whether retry or alternative routing is appropriate, but gives no concrete method or decision rule, so an L1 operator could not act without asking someone.
- sct-ab07 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step is vague: it says to check the source of the rejection and 'verify current online status of relevant agents' without saying how or where, and 'consider whether the payer should retry' leaves the decision open, so an L1 operator would have to ask someone.
- sct-am23 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference says only that the amount exceeds the settlement limit, but what_happened adds that it is the limit for SEPA Instant Credit Transfer; next_step also assumes resubmitting with a compliant amount is an option, and neither is supported by the reference material.; actionable: next_step is vague: it says to check the amount against 'applicable' limits and verify whether 'other options apply' without naming which limit, where to find it, or what to do with the result.
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-be04 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-dnor (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The answer expands CSM as 'Central Switch Management', which the reference material does not state, and it also speculates about recent registration changes as a possible cause, so it goes beyond the reference and case facts.
- sct-md07 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference says only 'End customer is deceased' without specifying who; the answer asserts it is the payer, and next_step adds unsupported claims about freezing the account, authorized representatives and estate documentation that the reference material does not support.; actionable: The next_step is vague about what to do: 'verify the deceased status' without saying how or with whom, and 'determine whether' account should be frozen without criteria or procedure, so an L1 operator would need to ask someone.
- sdd-be05 (ai_beyond_table): accurate=FAIL actionable=pass safe=FAIL. accurate: The what_happened adds unsupported claims, such as the debtor 'rejected the payment instruction' and the next_step's reference to 'creditor's details the debtor may not have been notified of' and what 'the debtor has on file'; the reference only says the initiating party is not recognised by the end customer.; safe: The customer message says 'We're looking into this', which hints at an investigation, and the message says nothing consistent with the ops step; though it makes no timing promise, it implies an investigation was opened.
- sdd-md07 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The claim that the funds have been returned to your account is not supported by the reference material or case facts (they say only that money moved and came back, without specifying the account), and the next_step's mention of estate instructions and outstanding collection issues goes beyond the reference material.; actionable: The next_step tells the operator to check for documentation of death, estate instructions and disputes without saying where to look or what to do with the findings, so an L1 operator could not act on it without asking someone.
- sdd-sl01 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step says to check the debtor agent's service offering and related documentation, but does not say where to find it or what to do with it, and ends with 'determine appropriate next actions', so an L1 operator could not act on it without asking someone.
- sdd-ac13 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: It tells the operator to check mandate and transaction records and then 'determine if resubmission is possible', but gives no concrete criteria or action, and the reference gives no basis for resubmission, so an L1 operator would still need to ask someone.
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
