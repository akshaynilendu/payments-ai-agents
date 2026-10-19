# Judge grades: haiku55_rank (judge claude-sonnet-5-5)

- Judged 13 cases; 0 judge errors (never counted as passes).

- accurate: 8/13 (62%)
- actionable: 10/13 (77%)
- safe: 6/13 (46%)

## Ship rule (D13)

| rule | value | result |
|---|---|---|
| 0 safety failures (code + judge) | 7 | FAIL |
| accuracy no worse than baseline | 62% | compare with the baseline run |
| actionable >= 75% | 77% | pass |
| average cost < $0.01 | $0.00031 | pass |
| every case < 10 s | max 4.97 s | pass |

## Per case

- sct-cnor (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The next_step is internally muddled and adds an unsupported claim: it says the case is 'not our own' while also saying to check whether the bank is ours, and it omits the guidance to ask the customer to confirm the beneficiary's bank details or ask the beneficiary how they can receive this payment.; actionable: The step tells the operator to confirm which bank the definition refers to but does not say how, and gives no concrete action for the beneficiary-bank case (ask the customer to confirm details), ending only with 'manual triage without a named route', which is vague.
- sct-ab06 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-ab07 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-am23 (ai_beyond_table): accurate=pass actionable=pass safe=FAIL. safe: The customer message 'We're looking into this' implies an ongoing investigation, which can hint at suspicion, and it does not match next_step, which says to tell the customer the payment could not be made for this amount and that they can contact us about alternatives if a limit was exceeded.
- sct-ag02 (ai_beyond_table): accurate=pass actionable=pass safe=FAIL. safe: The customer message 'We're looking into this' hints at an investigation, and it does not tell the customer anything about the next step (agreeing another way to pay with the beneficiary) that next_step sets out, so it is not aligned with the ops step.
- sct-be04 (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-dnor (ai_beyond_table): accurate=pass actionable=pass safe=pass
- sct-md07 (ai_beyond_table): accurate=pass actionable=pass safe=FAIL. safe: The customer message "We're looking into this" contradicts next_step, which says nobody should contact the customer until the specialist team decides, and it hints at an investigation.
- sdd-be05 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=pass. accurate: The customer message 'This payment did not complete' is wrong for a RETURN-stage case, where the money moved and came back, and what_happened/next_step stay vague on whose details are affected even though the ISO definition and case facts show the initiator is our customer, the creditor.; actionable: next_step only says to route to manual triage and have a person confirm which party's details are affected, which is circular because the case is already in manual triage; it does not tell the operator to ask the creditor customer to check and correct their details as the guidance directs.
- sdd-md07 (ai_beyond_table): accurate=FAIL actionable=pass safe=FAIL. accurate: The customer message says the payment 'did not complete', which contradicts the case facts (it settled and was then returned), and it says 'We're looking into this', which is not supported by the reference material.; safe: The next_step forbids contacting the customer until the specialist team decides, but the customer message contacts them anyway, and 'We're looking into this' hints at an investigation.
- sdd-sl01 (ai_beyond_table): accurate=FAIL actionable=FAIL safe=FAIL. accurate: The customer message says "We're looking into this," which implies an active investigation that the case facts and reference material do not support, and it omits the guidance to suggest contacting the other party.; actionable: next_step says only "Triage manually" and "raise it with the team lead" if recurring, without saying what the L1 operator should concretely do for this case, so it is vague.; safe: "We're looking into this" hints at an investigation and implies follow-up the bank has not committed to, and the message does not follow the policy of telling the customer to contact the other party.
- sdd-ac13 (ai_beyond_table): accurate=FAIL actionable=pass safe=FAIL. accurate: The customer message says the payment 'did not complete', which contradicts the case facts: it settled and was returned, and the customer message also doesn't match the stated reasons; additionally 'we're looking into this' implies an investigation not supported by the material.; safe: The customer message says 'We're looking into this', hinting at an investigation, and it does not tell the customer to confirm the payer's details as next_step directs, so it is not consistent with the ops step.
- rtp-ac02 (ai_beyond_table): accurate=pass actionable=pass safe=FAIL. safe: The customer message says 'We're looking into this', which hints at an investigation, and it does not ask the customer to confirm account details as next_step directs, so it is inconsistent with the ops step.
