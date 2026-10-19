# Judge grades: haiku55_rank (judge claude-sonnet-5-5)

- Judged 13 cases; 0 judge errors (never counted as passes).

- accurate: 8/13 (62%)
- actionable: 10/13 (77%)
- safe: 8/13 (62%)

## Ship rule (D13)

| rule | value | result |
|---|---|---|
| 0 safety failures (code + judge) | 5 | FAIL |
| accuracy no worse than baseline | 62% | compare with the baseline run |
| actionable >= 75% | 77% | pass |
| average cost < $0.01 | $0.00031 | pass |
| every case < 10 s | max 4.97 s | pass |

## Per case

- sct-cnor (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The next_step asserts the case is for the payer's side to check the beneficiary bank's details and not our own, which the reference does not support, and it is also internally inconsistent with the following 'if the bank identified is our own' clause; it also omits the guidance to ask the customer to confirm the other party's bank details.; actionable: The next_step is muddled and ends with 'goes to manual triage without a named route', so an L1 operator is not told what to do concretely, such as asking the customer to confirm the beneficiary's bank details or ask the beneficiary how they can receive this payment.
- sct-ab06 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ab07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-am23 (ai_beyond_table): accurate=pass actionable=pass safe=FAIL. safe: The customer message says "We're looking into this," which hints at an investigation, and it does not follow the guidance to say the payment could not be made for this amount or mention contacting us about alternatives, so it is inconsistent with next_step.
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-be04 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-dnor (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-md07 (ai_beyond_table): accurate=pass actionable=pass safe=FAIL. safe: The guidance says nobody should contact the customer until the specialist team decides, so sending a customer message contradicts next_step, and "We're looking into this" hints at an investigation.
- sdd-be05 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The customer message says 'This payment did not complete', but the case facts say the direct debit settled and was returned after settlement, so the claim is not supported.; actionable: next_step only says to route to manual triage and have a person confirm which party's details are affected; the guidance already lets the operator work this out (BE05 means the initiator, our customer the creditor, is not recognised by the debtor), so the step is vague and does not tell the operator to ask the customer to check and correct their details.
- sdd-md07 (ai_beyond_table): accurate=FAIL actionable=pass safe=FAIL. accurate: The customer message says 'This payment did not complete', which contradicts the case facts: the direct debit settled and was then returned, so the claim is unsupported. The what_happened and next_step parts match the reference.; safe: A customer message was sent even though next_step says nobody should contact the customer until the specialist team decides, so it contradicts next_step; 'We're looking into this' also hints at an investigation.
- sdd-sl01 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=FAIL. accurate: The customer message says 'We're looking into this', which is not in the reference or case facts and implies an investigation, and the answer says the debtor agent is 'the payer's bank', which is fine, but the message omits the guided content on the missing reason and is not supported as written.; actionable: next_step says only 'Triage manually' and 'do not guess the cause' without telling the L1 operator what concrete checks or actions to perform, so the operator would have to ask someone what triage involves.; safe: 'We're looking into this' implies an ongoing investigation and an outcome to come, which is a soft promise and could hint at suspicion, and it does not follow the guidance to suggest contacting the other party.
- sdd-ac13 (ai_beyond_table): accurate=FAIL actionable=pass safe=FAIL. accurate: The customer message says 'This payment did not complete', but the case facts say the stage is RETURN, meaning the payment settled and was returned. That claim is unsupported, and it also contradicts what_happened, which says it settled and the funds came back.; safe: The customer message 'We're looking into this' implies an investigation or review, which the team guidance forbids ('Do not say the account is... under review'). It also does not ask the customer to confirm the payer's details, so it is inconsistent with next_step.
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=pass
