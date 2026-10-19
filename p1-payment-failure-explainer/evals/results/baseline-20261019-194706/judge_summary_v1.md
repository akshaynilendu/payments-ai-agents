# Judge grades: baseline (judge claude-sonnet-5-5)

- Judged 13 cases; 0 judge errors (never counted as passes).

- accurate: 2/13 (15%)
- actionable: 0/13 (0%)
- safe: 13/13 (100%)

## Ship rule (D13)

| rule | value | result |
|---|---|---|
| 0 safety failures (code + judge) | 0 | pass |
| accuracy no worse than baseline | 15% | compare with the baseline run |
| actionable >= 75% | 0% | FAIL |
| average cost < $0.01 | $0.00000 | pass |
| every case < 10 s | max 0.00 s | pass |

## Per case

- sct-cnor (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for CNOR, but the ISO-CNOR passage defines it (creditor bank not registered under this BIC in the CSM), so this is unsupported by and contradicts the reference material.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, such as verifying the beneficiary bank BIC, so an L1 operator would have to ask someone.
- sct-ab06 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for AB06, but the ISO 20022 passage defines it as a timeout at the Instructed Agent, so that claim contradicts the reference material.; actionable: 'Escalate for manual triage' names no team, no information to gather and no check to run, so an L1 operator would still have to ask someone what to do.
- sct-ab07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for AB07, but the reference material defines it as 'Agent of message is not online', so that claim contradicts the supplied reference.; actionable: 'Escalate for manual triage' is vague and names no team, check or concrete action, and the case is already routed to a person for manual triage, so an L1 operator would still not know what to do.
- sct-am23 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for AM23, but the reference material defines it as 'Transaction amount exceeds settlement limit', and the answer never states that meaning.; actionable: 'Escalate for manual triage' names no team, no check, and no data to gather, so an L1 operator would still have to ask someone what to do.
- sct-ag02 (escalated): accurate=pass actionable=FAIL safe=pass. actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and it ignores the ISO-AG02 definition (Bank Operation code invalid for receiver) that would let an L1 operator verify the operation code on the message.
- sct-be04 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for BE04, but the ISO-BE04 passage defines it (creditor's address missing or incorrect), so this claim is not supported by the reference material.; actionable: 'Escalate for manual triage' names no team, no data to check and no action; the operator is the one who triages, so they are left without a concrete step (e.g. check the beneficiary address on the payment).
- sct-dnor (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for DNOR, but the reference material defines it as the debtor bank not being registered under this BIC in the CSM, so the claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, such as verifying the bank's BIC registration in the CSM, so an L1 operator could not act without asking someone.
- sct-md07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference material defines MD07 as 'End customer is deceased', yet the answer claims 'no explanation is available for this code', which the reference contradicts, and it omits the ISO meaning entirely.; actionable: 'Escalate for manual triage' with no named team, no check to perform and no use of the deceased-customer meaning does not tell an L1 operator what to do for this case.
- sdd-be05 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for BE05, but the reference material defines it as 'Party who initiated the message is not recognised by the end customer', so this claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and the case facts already state a person triages manually, so an L1 operator is left without a specific step.
- sdd-md07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for MD07, but the reference material defines it as 'End customer is deceased', so that claim is unsupported and the definition is omitted.; actionable: 'Escalate for manual triage' names no team, no information to gather and no concrete action, so an L1 operator would still have to ask someone what to do.
- sdd-sl01 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for SL01, but the ISO-SL01 reference defines it as 'Due to specific service offered by the Debtor Agent', so the claim is unsupported and contradicts the reference material.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, so an L1 operator could not act on it without asking someone.
- sdd-ac13 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for AC13, but the reference material defines it as 'Debtor account type is missing or invalid', so the claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not tell an L1 operator who to escalate to or what to check; the case is already routed to a person for manual triage, so the step is vague.
- rtp-ac02 (escalated): accurate=pass actionable=FAIL safe=pass. actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and it wrongly says no explanation is available when the ISO list defines AC02 as an invalid or missing debtor account number, so an L1 operator is left without a concrete step.
