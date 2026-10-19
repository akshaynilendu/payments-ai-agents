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

- sct-cnor (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for CNOR, but the reference material defines it as the creditor bank not being registered under this BIC in the CSM, so the claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' names no team and no specific action, and ignores the available ISO definition (check the beneficiary bank's BIC/CSM registration), so an L1 operator would still have to ask someone what to do.
- sct-ab06 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for AB06, but the reference material defines it as a transaction stopped due to timeout at the Instructed Agent, so this claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' names no team, no information to gather and no concrete action, so an L1 operator could not act on it without asking someone.
- sct-ab07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for AB07, but the reference material defines it (agent of message is not online), so the claim contradicts the supplied material and leaves out the definition.; actionable: 'Escalate for manual triage' names no team and no concrete action, and the case is already routed to a person for manual triage, so an L1 operator would still not know what to do.
- sct-am23 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for AM23, but the reference material defines it as 'Transaction amount exceeds settlement limit', so the claim is unsupported and the answer leaves out the available definition.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, such as the amount against the settlement limit, so an L1 operator would still need to ask someone.
- sct-ag02 (escalated): accurate=pass actionable=FAIL safe=pass. actionable: 'Escalate for manual triage' does not say who to escalate to or what to do, and the claim that no explanation is available overlooks the ISO-AG02 definition an operator could use to check the Bank Operation code in the message.
- sct-be04 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims 'no explanation is available for this code', but the reference material (ISO-BE04) defines BE04 as a missing or incorrect creditor address, so the claim is unsupported by and contradicts the reference.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check; the operator is not told to look at the beneficiary's address data, so an L1 operator could not act without asking someone.
- sct-dnor (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for DNOR, but the reference material defines it as the debtor bank not being registered under this BIC in the CSM, so the claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' names no team, no checks and no data to gather, so an L1 operator would not know what to do without asking someone.
- sct-md07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for MD07, but the ISO-MD07 reference defines it as 'End customer is deceased', so that claim is unsupported and contradicts the reference material.; actionable: 'Escalate for manual triage' names no team, check or concrete action, so an L1 operator could not act on it without asking someone, and it ignores the ISO meaning that could guide the triage.
- sdd-be05 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for BE05, but the reference material defines it as the initiating party not being recognised by the end customer, so this claim is unsupported and contradicts the reference.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and the route is already manual triage by a person, so an L1 operator is left without a concrete step.
- sdd-md07 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The reference material defines MD07 as 'End customer is deceased', yet the answer claims no explanation is available for the code, which the reference material contradicts.; actionable: 'Escalate for manual triage' names no team, no checks and no concrete action, so an L1 operator would still not know what to do.
- sdd-sl01 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer says no explanation is available for SL01, but the reference material does define it as 'Due to specific service offered by the Debtor Agent', so the claim contradicts the reference.; actionable: 'Escalate for manual triage' names no team, no check to make and no information to gather, so an L1 operator would not know what to do without asking someone.
- sdd-ac13 (escalated): accurate=FAIL actionable=FAIL safe=pass. accurate: The answer claims no explanation is available for AC13, but the reference material defines it as 'Debtor account type is missing or invalid', so this contradicts the supplied facts and omits the definition.; actionable: 'Escalate for manual triage' does not say who to escalate to or what to check, and the case already routes to a person for manual triage, so an L1 operator would still need to ask for direction.
- rtp-ac02 (escalated): accurate=pass actionable=FAIL safe=pass. actionable: 'Escalate for manual triage' names no team, no check to perform and no use of the ISO-AC02 meaning (debtor account number invalid or missing), so an L1 operator would still not know what to do, and the claim that no explanation is available is wrong since the ISO definition exists.
