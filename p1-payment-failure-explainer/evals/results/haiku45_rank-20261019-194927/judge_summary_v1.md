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

- sct-cnor (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer expands CSM as 'Credit Transfer Scheme Management system', which the reference does not support (CSM is not defined there), and adds that it 'prevented the payment from being processed', an unsupported inference.; actionable: The next_step is vague: it says to check whether the BIC is correct and registered in the CSM without saying where or how to check, and 'verify the payment details with the customer if needed' gives no specific action.
- sct-ab06 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: next_step says to check whether the timeout was at an intermediary or the beneficiary's bank and whether a retry or alternative routing is appropriate, but it gives no concrete method, system or decision rule, so an L1 operator would have to ask someone.
- sct-ab07 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step is vague: 'verify current online status of relevant agents' and 'consider whether the payer should retry' do not tell an L1 operator how to check or what to decide, and the reference gives no basis for the retry advice.
- sct-am23 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference only says the amount exceeds the settlement limit; it does not say the limit is specific to SEPA Instant Credit Transfer, nor does it support the next_step claims about resubmitting with a compliant amount or 'other options'.; actionable: The next_step is vague: it says to check the amount against 'applicable' limits and 'verify whether... or if other options apply' without naming which limit, where to find it, or what concrete action to take in each outcome.
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-be04 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-dnor (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The answer expands CSM as 'Central Switch Management', which the reference material does not state, and it also adds a speculative cause ('recent changes to our registration status') that is not supported.
- sct-md07 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference only says 'End customer is deceased' without specifying whether this is the payer or the beneficiary, yet what_happened asserts it is the payer, and next_step adds unsupported claims about freezing the account, authorized representatives and estate documentation.; actionable: next_step tells the operator to 'verify the deceased status' without saying how or against what source, and the freezing, authorized-representative and documentation items are vague considerations with no concrete steps or decision criteria.
- sdd-be05 (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The what_happened adds unsupported claims: that the debtor 'rejected the payment instruction' and that the creditor's details matched or changed are not in the reference, and the next_step assumes mandate/identifier causes beyond the reference material.
- sdd-md07 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=FAIL. accurate: The claim that 'the funds have been returned to your account' is not supported by the reference material or case facts, and the customer message 'We're looking into this' adds an unsupported claim of investigation.; actionable: The next_step tells the operator to check for documentation of death, estate instructions and disputes, but the operator has no stated source for these and no concrete action or outcome, so it remains vague manual triage.; safe: 'We're looking into this' hints at an investigation, and although it is not a regulatory concern, it implies follow-up action and is not consistent with the policy-set message.
- sdd-sl01 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step is vague: it says to check the debtor agent's service offering and documentation and then determine next actions, without naming a concrete source, contact or action an L1 operator could carry out unaided.
- sdd-ac13 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
