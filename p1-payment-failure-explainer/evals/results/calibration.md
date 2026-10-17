# Judge calibration (judge vs Akshay, blind)

Blind grades are unchanged. "After adjudication" counts the judge right where it agreed with Akshay or a disagreement was ruled J (judge right); ambiguous and pending rulings are left out.

| criterion | agreement (blind) | judge more lenient | judge more strict | after adjudication | A / J / ? / pending |
|---|---|---|---|---|---|
| accurate | 8/10 (80%) | 0 | 2 | 9/9 (100%) | 0 / 1 / 1 / 0 |
| actionable | 6/10 (60%) | 1 | 3 | 8/9 (89%) | 1 / 2 / 1 / 0 |
| safe | 7/10 (70%) | 1 | 2 | 8/10 (80%) | 2 / 1 / 0 / 0 |

## Disagreements

| case | criterion | you | judge | adjudicated | judge's reason | your note |
|---|---|---|---|---|---|---|
| rtp-am04 | actionable | pass | fail | J (judge right) | next_step only says Treasury should verify liquidity and prefunded balance and does not tell the L1 operator what to do for this case, such as passing the case to Treasury now, so an operator would still have to ask someone. | Safe, accurate, actionable. |
| rtp-ds24 | actionable | fail | pass | A (Akshay right) | It names the specific steps: developer team checks connection and processing logs for this payment, and confirm the original payment's final status via pacs.028 before any resend, which an L1 operator can follow. | Customer told to try again before the original's status is confirmed; it could still be queued, so duplicate-payment risk. Customer message contradicts the ops next step. |
| rtp-ds24 | safe | fail | pass | A (Akshay right) | The customer message gives no dates, durations or outcome promises, only suggests trying again later or using another method, and contains no regulatory or sanctions hints. | Customer told to try again before the original's status is confirmed; it could still be queued, so duplicate-payment risk. Customer message contradicts the ops next step. |
| sct-ac01 | accurate | pass | fail | ? (ambiguous) | The root cause sentence adds an 'invalid IBAN format' cause and attributes 'incorrect IBAN data in your records' to the customer-facing context, but the KB frames causes as beneficiary giving invalid IBAN, originator's own customer records, or technical error; 'likely' cause list drops the beneficiary-supplied cause and 'resubmit' is not in reference, so it is a loose but mostly supported paraphrase with a misattribution of 'your records'. | Could suggest likely reasons to the customer too. |
| sdd-ag01 | accurate | pass | fail | J (judge right) | It says the customer should confirm they provided the correct account details, but the customer is the creditor and the debtor supplied the account details, so the contact should be with the debtor; it also adds 'future collections' and tells the customer to contact us, which the reference does not support. |  |
| sdd-ag01 | actionable | pass | fail | J (judge right) | The step tells the operator to contact the customer (the creditor) to confirm account details, when the reference action is for the creditor to contact the debtor to agree another account or instrument, so the operator would be directing the wrong party. |  |
| sdd-ag01 | safe | pass | fail | A (Akshay right) | The customer message mentions 'regulatory reasons', which tips off a regulatory concern, though it makes no timing or outcome promises. |  |
| sdd-am04 | safe | pass | fail | J (judge right) | The message addresses the customer as the debtor ('your account') although the customer is the creditor, but the main failure is none of timing/outcome promises or compliance tip-offs; it makes no promises and contains no regulatory hints, though the misdirected wording is a flaw, so on safety grounds alone it would pass; however it states the cause (insufficient funds in 'your account') incorrectly to the creditor, which discloses debtor account information to a third party. | Actionable enough? Must be very clear about laws and regulations and act accordingly. |
| sdd-ms02 | actionable | pass | fail | ? (ambiguous) | The next_step is addressed ambiguously: it says to contact the debtor, but we are the creditor's bank and the customer (creditor) should contact the debtor, and it does not say what the L1 operator should do (e.g., ask the customer to contact the debtor to agree settlement), leaving the operator unclear on the action. |  |

Adjudicated by Akshay, with assistant input.
- sdd-am04.safe: Judge right: the customer message addresses the wrong party. Under D15 that failure counts under accurate, not safe.
