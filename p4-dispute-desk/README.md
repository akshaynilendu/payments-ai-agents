# Dispute Desk

An AI agent that answers card chargebacks for a small online shop. The agent reads the dispute and the shop's records and proposes fight, accept, already refunded, or ask a person. A rules engine behind an MCP server decides. It can only make a proposal safer. It never turns an acceptance into a fight. Everything is made up: the shop, the customers, the cards and the tracking.

**Result:** the agent got 28, 27 and 27 of 30 right across three runs, with 0 or 1 wrong, no missed deadlines, about £226 + €84 recovered after fees, at $0.001 per dispute. The code-only baseline got 19/30 and left winnable fights on the table. The agent was not fooled by an instruction hidden in the cardholder message. What it missed was caution, a missing citation, and one case where two emails disagree.

## The problem
Merchants lose disputes in two ordinary ways. They miss the reply date, and the scheme decides for the cardholder with no hearing. Or they fight without the evidence the reason code requires, and pay staff time on a case they cannot win. A small shop's ops person has the order, the carrier scan, the emails and the refund ledger, and not enough time to open all of them for every case.

## The user
The person who runs disputes for Hollowbrook Ceramics, the same fictional shop as Project 3. They want a first response: fight with a pack, accept, record that the order was already refunded, or hand the case to a person. They do not want the agent talking to Visa.

## How it works
```
dispute ──> agent (Haiku, via Project 3's client) ──MCP──> desk
                                                          ├─ read-only: get_dispute, lookup_order, lookup_shipment,
                                                          │             lookup_customer_emails, lookup_refunds, lookup_prior_orders
                                                          └─ propose_response ──> guardrail engine (code, no AI) ──> decision + audit log
```
- The server sets the dispute id. The agent cannot point a proposal at a different case, and only the first proposal counts.
- The cardholder message is data. Text in it that tells the model to accept, hide tracking, or ignore the rules is not evidence.
- **The guardrail** starts from the proposal and can only move toward safer. It forces ALREADY_REFUNDED when this order id is fully refunded on the ledger. It forces ACCEPT when the amount is below the fight-cost floor (£25 / €25). It marks LATE if `respond_by` has passed, and SUBMIT_TODAY if the reply is due today or tomorrow. It downgrades a FIGHT that fails Compelling Evidence 3.0, or that does not attach the records that reason code needs, to ASK_HUMAN. It never upgrades ACCEPT or ASK_HUMAN to FIGHT, and it does not judge "not as described" from email prose. A delivery to a different address may stay a fight only when the proposal cites an email from the cardholder's own address that asks for that place.
- **Every decision** goes into a hash-chained audit log, the same construction as Project 3. Changing a past entry breaks every hash after it. Some refunds in this set were paid by that project; the pack cites the seq and hash from its console export.
- The desk's day is Monday 16 November 2026. `respond_by` is `opened_at` plus 30 calendar days. The acquirer keeps a £15 / €15 fee on a win and on an acceptance. Recovered after fees on a right fight is amount − fee − fight cost, and it can be negative. A right acceptance books amount + fee. Already refunded recovers 0 and is not paid twice.

## Visa reason codes
The cases and the engine use the Visa code. The Mastercard column is a reading aid only. Mastercard has been folding several consumer-dispute codes into 4853, so a live feed needs the sub-reason, not just the number.

| Visa | Meaning | Mastercard | Meaning |
|---|---|---|---|
| 10.4 | Fraud, card not present | 4837 | No cardholder authorization |
| 13.1 | Merchandise not received | 4855 | Goods or services not provided |
| 13.3 | Not as described or defective | 4853 | Cardholder dispute |
| 12.6 | Duplicate processing | 4834 | Point-of-interaction error (duplicate) |
| 13.2 | Cancelled recurring | 4841 | Cancelled recurring transaction |

**Compelling Evidence 3.0** is how Visa lets a merchant fight 10.4. It ties the disputed payment to earlier purchases on the same card. A fight is allowed only with at least two earlier orders, each 120 to 365 days before this one, not themselves disputed or refunded, each sharing at least two of IP address, device id, shipping address and account login. Fewer than that, and a 10.4 fight loses, so the right proposal is ACCEPT. The first draft of this project invented a "three earlier orders" rule. That is not the scheme rule, and it was replaced.

## Versions compared
| | What it is |
|---|---|
| A | Code only: keywords and a few fields propose an outcome. Not tuned on the traps |
| B | One agent, reaching the desk only through the MCP server. The engine is the guardrail |

## Results
30 synthetic disputes: 8 textbook, 4 messy (French, German, typos), 12 tricky, 6 traps. "Safe, not ideal" means the agent asked a person on a case the key decides, and the deadline was not tomorrow. Three runs of B.

| Version | Right | Safe, not ideal | Wrong | Recovered after fees | $/dispute | Time |
|---|---|---|---|---|---|---|
| A code | 19/30 | 2 | 9 | £130 + €80 | $0 | <0.1 s |
| **B agent** | **28, 27, 27** | 2 | **0–1** | **£226 + €84** | $0.001 | ~4.5 s |

What each row taught:
- **A** never missed the deadline, and the guardrail stopped fights that had no delivery, no compelling evidence, or a partial refund. It still fought damage cases because a keyword saw the word "delivered", and it accepted winnable ones (a cancellation after the charge, a voided duplicate, two real orders, a fraud code that actually had the history) because it does not read the records the way a person would. Guardrails stop a bad fight. They cannot supply the fight the keywords never proposed.
- **B** picked up those fights and cited the records. Recovered money went from £130 + €80 to £226 + €84. It still handed two cases to a person, and in two runs it accepted a case whose emails disagree. No run missed the one deadline (DP-25, due the next day, filed as SUBMIT_TODAY).

**Shipped: B.** Same lesson as Projects 1 to 3: deterministic where you can, AI where you must, and the simplest design that passes.

## Ops metrics (B)
- Cost: $0.001 per dispute, so about $1 per 1,000 cases. A run of 30 was about $0.03.
- Handling time: about 4.5 s per dispute (the three runs were 4.3 s, 4.4 s and 5.0 s).
- Errors: 2 wrong outcomes in 90 decisions, both the same case (DP-19). Two more per run were cautious hand-offs, not wrong fights. Missed deadlines: 0.
- The person still sees ASK_HUMAN (partial refund, split shipment, amount that is not the order total, emails that disagree) and any fight the guardrail refused.

## What broke and how it was fixed
- **The engine decided the answer itself.** The first version recomputed the outcome from the records, so a bad proposal still scored 30/30. It upgraded 6 ACCEPTs to FIGHT. It is now a guardrail, like Project 3's policy engine: it can force a refund, force a cheap acceptance, or stop a fight, and it cannot invent one.
- **The fraud rule was made up.** "Three earlier orders" is not what Visa asks for. Reason 10.4 now uses Compelling Evidence 3.0: two earlier undisputed orders, 120 to 365 days before, on the same card, sharing two data elements. A first order fails it. Two recent orders fail it. Two orders inside the window pass it.
- **A deadline of tomorrow was treated as "ask a person".** That is how the deadline gets missed. The outcome stays whatever the evidence supports, and the priority is SUBMIT_TODAY. A late response, once `respond_by` has passed, is an automatic loss.

## The honest misses
- **DP-05, every run.** A Clay Club renewal with no cancellation on file. The key is FIGHT. The agent asked a person. Safe, and it leaves a small fight (£32, which is £8 under water after the fee and the staff time) unfiled.
- **DP-30, every run.** Two real orders a week apart, both delivered, same amount. The agent proposed FIGHT but did not cite the other order. The guardrail will not go and find that order for it, so the fight became ASK_HUMAN.
- **DP-19, two runs of three.** One email says the platter arrived fine, a later one says it is cracked. The key is ASK_HUMAN. The agent accepted. The engine does not judge "not as described", so the acceptance stood.

## Regulation notes
- **Scheme rules, not a statute.** The reply window and the evidence for each reason code are Visa's. Missing the date is a loss. This desk does not connect to a scheme or an acquirer.
- **GDPR:** the cardholder message, emails, name, address, IP and device id are personal data. The agent is shown one dispute's records. The audit log keeps the pack a dispute needs. Every field here is synthetic, including the card numbers (they are not real PANs) and the Project 3 ledger hashes.
- **EU AI Act:** as far as I can tell, drafting a chargeback response is not an Annex III high-risk use (credit scoring is the neighbour). The safeguards people expect are still here: a person can be asked, the model cannot upgrade its own proposal into a fight, and every decision is logged.
- **Not real:** no scheme API, no live card, no real customer. The audit hash shows tampering. It is not a signature.

## Owner console
`scripts/export_console_data.py` turns the latest Version B run into `console/console_data.json`: each dispute with the message, the deadline, the priority, the proposal, the decision, the reasons, the evidence pack and the money at stake, plus the 30 decisions re-chained into one log in the order the disputes were opened. Each entry keeps `hashed_body`, the exact string that was hashed, same as Project 3, so a console can recompute SHA-256. A test checks the chain verifies. There is no hosted demo in this folder yet.

## What v2 would add
- Pre-arbitration, for when the issuer comes back after this first response.
- Mastercard reason codes as input, not only the reading-aid table above.
- Live PSP dispute APIs, so a response is filed rather than written into a JSON file.

## Run it
```
cd p4-dispute-desk
~/venvs/p3/bin/python scripts/generate_data.py          # rebuild the made-up world (same seed)
~/venvs/p3/bin/python -m pytest -q                      # no network
~/venvs/p3/bin/python scripts/run_eval.py --version A
~/venvs/p3/bin/python scripts/run_eval.py --version B   # reads the key from Project 3's env file; never prints it
~/venvs/p3/bin/python scripts/export_console_data.py
```
The interpreter is Project 3's virtualenv. This folder does not keep its own. Made-up data only. Nothing from any employer.
