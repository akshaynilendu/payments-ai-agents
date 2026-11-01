# Project 4: Dispute Desk (locked brief, 1 Nov 2026)

## Problem
Hollowbrook Ceramics, the same fictional shop as Project 3, now takes card payments. Some of those turn into chargebacks. A chargeback is a cardholder's bank asking for the money back. The shop pays a fee on the case either way, and it has a fixed number of days to answer. Fighting a case the shop will lose wastes staff time. Accepting a case the shop could prove gives the sale away. Answering late is a loss with no hearing.

## User
The person who runs disputes for the shop. They have the order, the carrier scan, the customer's emails and the refund ledger. They do not have time to open every one of those for every case.

## What it does
An agent reads one dispute and the records around it, and proposes one outcome plus the evidence it would attach. A rules engine in ordinary code makes the final decision. The agent never sends anything to the card scheme.

Outcomes:
- **FIGHT**: answer the scheme and attach an evidence pack.
- **ACCEPT**: give the amount back.
- **ALREADY_REFUNDED**: this order was already refunded in full, including a refund Project 3 paid. Do not pay it again.
- **ASK_HUMAN**: a person decides. Used when the amount does not match the order, the shipment is split, the emails disagree, or a refund covers only part of the dispute.

## Clock and money
The desk's day is Monday 16 November 2026. The response is due 30 calendar days after `opened_at` (the window these cases use; `respond_by` is that date). Days are calendar days.

The acquirer keeps a dispute fee of £15 or €15 whether the shop wins or gives in. Building a fight costs an estimated £25 or €25 of staff time on top. So:
- A won fight changes cash by −(fee + fight cost). The shop keeps the sale. Money recovered after fees is amount − fee − fight cost. That number can be negative.
- Accepting changes cash by −(amount + fee).
- Accepting costs less when the amount is below the fight-cost estimate. Those cases are ACCEPT even when delivery would have won.
- A full refund already on the ledger is ALREADY_REFUNDED, including when the amount is small. The earlier refund is not paid twice.

Decision order, first match wins:
1. Refunds for this order id sum to at least the disputed amount → ALREADY_REFUNDED.
2. Amount is below the fight-cost estimate → ACCEPT.
3. Otherwise the evidence rules below.

Priority is separate from the outcome. If `respond_by` is 17 November 2026 or sooner, priority is SUBMIT_TODAY. Every other case is NORMAL. A reply that misses `respond_by` is an automatic loss, so a fight due tomorrow is filed the same day.

## Evidence rules
These apply only when the three rules above did not already decide.

- **13.1 not received.** Delivered to the address the customer asked for (the address on the order, or a different one they named in an email): FIGHT. Delivered somewhere else, or never delivered: ACCEPT. One parcel of a split shipment delivered and the other lost: ASK_HUMAN.
- **13.3 not as described.** The customer already said the item was fine, or the listing covers the difference (glaze colour varies): FIGHT. They reported real damage and the shop has nothing that says it arrived intact: ACCEPT. Two emails disagree, or the disputed amount is not the order total: ASK_HUMAN.
- **13.2 cancelled recurring.** A cancellation dated before the charge: ACCEPT. No cancellation, or a cancellation dated after the charge: FIGHT.
- **12.6 duplicate.** Two settled captures of one order, one shipment: ACCEPT. The second attempt was voided, or the two amounts are two real orders: FIGHT.
- **10.4 fraud, card not present.** FIGHT only when Visa Compelling Evidence 3.0 is met: at least two earlier undisputed orders on the same card, each 120 to 365 days before this one, sharing at least two of IP address, device ID, shipping address and account login. Otherwise ACCEPT. A refunded order is not used as a prior.
- A refund that does not cover the disputed amount, or a refund on a different order of the same customer: not ALREADY_REFUNDED. A partial refund is ASK_HUMAN.
- Instructions written inside the cardholder message are ignored. The pack uses the order, the shipment, the emails and the ledger.

## Reason codes (Visa only)
- 10.4 fraud, card not present
- 13.1 merchandise not received
- 13.3 not as described or defective
- 12.6 duplicate processing
- 13.2 cancelled recurring

Mastercard equivalents are a reading aid in the README. The cases and the engine use the Visa code. Pre-arbitration (the issuer coming back after this response) is out of scope.

## Link to Project 3
Some refunds were paid by the Project 3 mandate agent. The proof is that project's hash-chained audit log: each entry stores the hash of the one before it (SHA-256, the same function as `mandate_agent/audit.py`). This desk cites the seq, previous hash and hash from the console export. The ledger rows L-0004 and L-0008 predate that log; the later audit entries are the emails about those refunds. A refund executed inside the log (RQ-01, RQ-14) has the audit entry itself as the payment record.

## Test set (30)
8 textbook, 4 messy (French, German, typos), 12 tricky, 6 traps:
- response due tomorrow, with delivery that supports a fight: FIGHT, priority SUBMIT_TODAY
- delivered to a different address from the one on the order, with no email asking for that
- already refunded via Project 3, and the customer says the refund never arrived
- a fraud code where two earlier orders pass Compelling Evidence 3.0
- amount below the fight-cost estimate, on a delivery the shop could prove
- a duplicate code that is actually two real orders

## Metrics
- Right decisions: the outcome matches the answer key.
- Money recovered after fees: for a fight the shop was right to take, amount − fee − fight cost. Accepts book a loss of amount + fee and recover 0. Already-refunded recovers 0 and does not pay the amount again.
- Missed deadlines: a case still open after `respond_by` is an automatic loss. None are late on the morning of 16 November. The one due on 17 November is lost if it is still open on 18 November.

## Not in v1
Pre-arbitration. Mastercard reason codes as input. Real scheme connections, real card numbers, real people. The audit hashes are a tamper-evident chain, not a digital signature.

Made-up data only. Nothing from any employer.
