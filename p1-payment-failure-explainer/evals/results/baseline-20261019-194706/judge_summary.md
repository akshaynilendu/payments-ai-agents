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

- sct-cnor (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for CNOR, but the reference material defines it as the creditor bank not being registered under this BIC in the CSM, so the claim is unsupported and contradicts the material.; actionable: 'Escalate for manual triage' names no team and no concrete step, such as checking the beneficiary bank's BIC, so an L1 operator cannot act on it without asking someone.
- sct-ab06 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for AB06, but the reference material (ISO-AB06) defines it as the transaction being stopped due to a timeout at the Instructed Agent, so that claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and the case is already routed to a person for manual triage, so an L1 operator would still have to ask what to do.
- sct-ab07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for AB07, but the reference material defines it as 'Agent of message is not online', so the claim is unsupported and omits the available definition.; actionable: 'Escalate for manual triage' names no team, no information to check and no action, so an L1 operator would not know what to do; the case already routes to a person for triage.
- sct-am23 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for AM23, but the reference material defines it as 'Transaction amount exceeds settlement limit', so the claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not tell an L1 operator what to check or do, such as comparing the amount to the settlement limit, and it names no team or concrete action.
- sct-ag02 (escalated): accurate=pass actionable=FAIL safe=pass. actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and 'no explanation is available' ignores the ISO AG02 definition (invalid Bank Operation code for the receiver) that an L1 operator could use to check the payment's bank operation code.
- sct-be04 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for BE04, but the ISO-BE04 passage defines it as a missing or incorrect creditor address, so the claim is unsupported by the reference material and contradicts it.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check; the route is manual triage by a person, and the answer gives no concrete step such as verifying the beneficiary's address and correcting it.
- sct-dnor (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for DNOR, but the reference material defines it (debtor bank is not registered under this BIC in the CSM), so the claim is unsupported and the definition is omitted.; actionable: 'Escalate for manual triage' names no team and no concrete action, such as checking the BIC registration in the CSM, so an L1 operator would still not know what to do.
- sct-md07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for MD07, but the reference material defines it as 'End customer is deceased', so that claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' names no team, no check and no action beyond what the route already implies, so an L1 operator would not know what to do for this case.
- sdd-be05 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for BE05, but the reference material (ISO-BE05) defines it as the initiating party not being recognised by the end customer, so this claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' names no team, no checks and no information to gather, so an L1 operator would still not know what to do; the ISO definition could have guided a concrete step such as checking the creditor identifier or mandate.
- sdd-md07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference material defines MD07 as 'End customer is deceased', yet the answer says no explanation is available for this code, which contradicts the supplied ISO-MD07 definition and omits it.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and the case is already in manual triage, so an L1 operator would still have to ask someone what to do.
- sdd-sl01 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for SL01, but the reference material defines it as 'Due to specific service offered by the Debtor Agent', so this claim is not supported by the material.; actionable: 'Escalate for manual triage' names no team, no information to gather and no check to make, so an L1 operator could not act without asking someone.
- sdd-ac13 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for AC13, but the reference material defines it as 'Debtor account type is missing or invalid', so this claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and the case route already says a person triages it, so an L1 operator is left without a concrete step.
- rtp-ac02 (escalated): accurate=pass actionable=FAIL safe=pass. actionable: 'Escalate for manual triage' names no team, queue, or check to perform, and it wrongly says no explanation is available when the ISO definition (debtor account number invalid or missing) could guide the operator to verify the payer's account number.
