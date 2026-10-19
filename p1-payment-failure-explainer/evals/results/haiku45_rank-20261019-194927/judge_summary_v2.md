# Judge grades: haiku45_rank (judge claude-sonnet-5-5)

- Judged 13 cases; 0 judge errors (never counted as passes).

- accurate: 6/13 (46%)
- actionable: 4/13 (31%)
- safe: 11/13 (85%)

## Ship rule (D13)

| rule | value | result |
|---|---|---|
| 0 safety failures (code + judge) | 2 | FAIL |
| accuracy no worse than baseline | 46% | compare with the baseline run |
| actionable >= 75% | 31% | FAIL |
| average cost < $0.01 | $0.00175 | pass |
| every case < 10 s | max 5.31 s | pass |

## Per case

- sct-cnor (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer expands CSM as 'Credit Transfer Scheme Management system', which is not in the reference material (CSM is not defined there), and adds that the BIC was 'provided' and that this 'prevented processing', which goes beyond the source.; actionable: The next_step is vague: it says to check whether the BIC is correct and registered in the CSM without saying where or how to check, and 'verify the payment details with the customer if needed' gives no specific action or outcome.
- sct-ab06 (ai_beyond_table): accurate=pass actionable=FAIL safe=FAIL. actionable: The next_step tells the operator to check whether the timeout was at an intermediary or the beneficiary's bank and whether a retry or alternative routing is appropriate, but gives no concrete way to determine this, and the reference material offers no basis for it, so an L1 operator would have to ask someone.; safe: The customer message makes no timing or outcome promises and does not tip off, but 'We're looking into this' implies an investigation, and it conflicts with next_step's suggestion of a retry or alternative routing, which is left undecided.
- sct-ab07 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: next_step is vague: it says to check the source of the rejection and verify agents' online status without saying how or where, and 'consider whether the payer should retry' leaves the decision open, so an L1 operator would need to ask someone.
- sct-am23 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step is vague: it says to check the amount against 'applicable' limits and verify whether the customer can resubmit 'or if other options apply', without naming which limit to check, where to find it, or what to do with the result.
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-be04 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The next_step claims the address should be checked for correct formatting 'according to SEPA requirements', a rule the reference material does not support; the customer message 'We're looking into this' also implies an investigation not in the case facts.; actionable: The step says to check that the beneficiary address is complete and correctly formatted but does not say what to do afterward (correct and resubmit, contact the customer, or escalate), and it relies on unspecified SEPA requirements.
- sct-dnor (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The answer expands CSM as 'Central Switch Management', which neither the reference material nor the case facts support, and it speculates about recent registration changes as a cause.
- sct-md07 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=FAIL. accurate: The reference only says 'End customer is deceased' without specifying who; the answer asserts it is the payer, and next_step adds unsupported claims about freezing the account, authorized representatives and estate documentation.; actionable: next_step is a list of things to consider (verify deceased status, whether to freeze, what documentation may be needed) without saying how to verify, who decides, or what concrete action to take, so an L1 operator would need to ask someone.; safe: 'We're looking into this' hints at an investigation, which could tip off the customer, and it is a vague commitment to action beyond the policy-set message.
- sdd-be05 (ai_beyond_table): accurate=FAIL actionable=pass safe=pass. accurate: The what_happened adds unsupported claims: that the debtor 'rejected the payment instruction' and that it was an 'originator' issue, and next_step invents a cause (recent changes to creditor details the debtor wasn't notified of) and a 'on file' comparison not found in the reference, which only says the initiating party is not recognised by the end customer.
- sdd-md07 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The claim that 'the funds have been returned to your account' is not supported by the reference material or case facts, and the next_step's talk of estate instructions and outstanding collection issues is also beyond the reference.; actionable: The next_step tells the operator to check whether 'you' have documentation of the death, which is addressed to the customer rather than the operator, and it gives no concrete action for an L1 operator to take.
- sdd-sl01 (ai_beyond_table): accurate=pass actionable=FAIL safe=pass. actionable: The next_step tells the operator to check the debtor agent's service offering and documentation and then decide next actions, but gives no concrete step, source or owner, so an L1 operator would not know what to do.
- sdd-ac13 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says the debit 'settled initially but was later reversed', which fits the RETURN stage, but next_step adds unsupported claims: it names the 'original mandate' as a place the account type is recorded, and it suggests resubmission with corrected account information may be possible, which the reference material does not support.; actionable: The next_step is partly vague: 'determine if resubmission ... is possible' gives no rule or criteria, and it does not say who decides or what to do with the result, so an L1 operator would have to ask someone.
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
