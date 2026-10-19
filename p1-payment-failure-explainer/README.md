# Payment Failure Explainer

When a payment fails, the bank gets back a short reason code (like `AM04` or `AC04`) inside an ISO 20022 message. Someone in operations then has to work out **what it means, what to do next, and who should act on it**.

This project combines a plain lookup table with AI: **the table answers when it knows the code; the AI helps staff when the table has no answer.** Both are measured against each other.

> Built as a portfolio project. **Made-up test data only.** No real payments, customers or bank data.

---

## The problem

I spent six years building real-time payments infrastructure. A familiar pattern: a payment fails, a ticket lands with first-line support, and the code alone doesn't tell them much. The same code can even mean different things on different rails. On US RTP, `AM04` ("insufficient funds") usually points to the bank's own prefunded balance, which is a treasury problem, not a customer one. Misrouted tickets cost hours, and unfamiliar codes go straight up the support ladder with no context.

**Users:** first-line payments operations (L1), with escalation to developers, treasury, fraud and compliance.
**Rails in scope (v1):** US RTP and SEPA Instant (push payments), SEPA Direct Debit (pull payments). Standard SEPA Credit Transfer and Fedwire come in v2.

---

## How it works

1. **Read the message.** Parse the ISO 20022 status report (pacs.002 / pacs.004) and mask names and account numbers before anything else.
2. **Check the table first.** If the code is in our reviewed table, the table's pre-approved answer is used, and the table decides the route (which team acts).
3. **If the table has no answer, the AI helps staff.** It explains the code using the **official ISO definition** plus rulebook passages (filtered by rail and **payment stage**: did the money actually move?), and must cite its sources. The case still goes to a human for routing, now with a ready-made explanation attached.
4. **Customers never see AI-written text.** Customer messages are pre-approved text, matched to the type of problem and the payment stage, or none at all where a specialist must decide first.
5. **Code checks every AI answer.** No invented sources, no promises, no tipping off on compliance cases, no contradictions. One retry, then hand over to a human.

---

## What I tested, and what I found

**First test (33 cases, all codes the table covers):** the plain table won. The AI's mistakes were almost all in **customer messages**: telling a customer to "try again" on a possible duplicate, revealing an internal treasury review, guessing at a reason the bank is legally not allowed to give.

**Then I noticed the test was unfair.** Every case was on the table's home turf, and the table was being graded against its own text. The real question is what happens with the **hundreds of ISO codes nobody has written an entry for**, where the table can only say "unknown, escalate".

**Second test: two slices, every answer graded against the same sources (majority of 3 grading passes):**

| Slice | System | Accurate | Actionable | Safe | Cost / case |
|---|---|---|---|---|---|
| 32 codes **in** the table | Plain table (reviewed text) | 70% | 80% | 93% | $0 |
| 14 codes **beyond** the table | Escalate only (today's process) | 15% | 0% | 100% | $0 |
| 14 codes **beyond** the table | **AI for staff** (Haiku 5.5 + ISO definition + team guide) | **92%** | **92%** | **100%** | **$0.0004** |

Graded against its own text, the table had scored 97%. Graded against the rulebook sources, it scores 70%: the gap is partly team knowledge that isn't written down as a source, and partly real errors. I found and fixed four unsafe customer messages that way.

Getting the AI to 92% took three rounds, each driven by the grades: adding a short "what to do" guide per code family (actionability 54% → 77%), then making the customer message match the type of problem and the payment stage (a return is not "did not complete"; no message at all for a deceased customer until a specialist decides).

**What I learned:**
- **A well-written table is hard to beat on the cases it was written for**, so it should stay in charge there.
- **The AI's value is coverage**: explaining codes nobody has written up yet, from official sources.
- **Keep AI away from customers until it's proven.** Its errors clustered exactly where policy matters.
- **Safety rules belong in code, not prompts.** In the first live test, the model cited the anti-tipping-off law and still suggested raising the regulatory concern with the customer.
- **Check that the test is fair before trusting it.** My first result looked conclusive, but it only measured the table's home turf.

**Decision:** known codes use the reviewed table; unknown ISO codes get an AI explanation for staff (internal pilot), with a human choosing the route; anything else goes to a human. In short: **deterministic where you can, AI where you must.**

**Known open items (v1.1):** two table messages still flagged (an SDD duplicate return, and a fraud-hold message that may be grader noise); two AI answers below the bar (a bank-registration code and a "bank-specific service" code); the table's text should be checked line by line against its sources.

---

## Key decisions (full list in `DECISIONS.md`)

- **The AI explains; it never decides.** Routes come from the table or a human; compliance next steps are fixed by code.
- **No unsourced facts.** Every claim cites a source; invented citations are rejected.
- **Privacy first.** Names, account numbers and free text never reach the model (which also removes the prompt-injection route).
- **Filter what you know, rank only what's fuzzy.** Payment stage is a filter, not a similarity score; found by hand-testing.
- **Clean sources.** Public rulebooks, the official ISO code list and a signed-off team runbook only. I dropped a document that came with a usage agreement.
- **Measure against a strong baseline**, and make sure the test covers the cases that matter.

---

## How I'd roll it out

1. **Shadow mode:** the AI runs on unknown codes alongside the current process, invisible to staff; a weekly sample is reviewed.
2. **Internal pilot:** AI explanations shown to L1 staff for unknown codes only.
3. **Grow the table** from what the AI keeps seeing: frequent unknown codes get a reviewed table entry.

**Switch it off if:** any safety failure is found in review, accuracy drops on the weekly sample, cost exceeds $0.01 per case, or answers take more than 10 seconds.

---

## Regulation and safety

- **GDPR / data minimisation:** personal data is masked before any model call; embeddings run locally.
- **AML tipping-off rules:** compliance cases never get a customer message, enforced in code.
- **Human oversight:** the AI never routes a case or writes to a customer; every answer shows its sources (scheme rule, regulation, ISO definition or team guidance).

---

## What's next (v2)

- Standard SEPA Credit Transfer and Fedwire
- Recall messages (camt.056 / camt.029)
- Spike monitoring: one timeout is a customer problem, a spike of timeouts is a system problem
- A simple demo screen

---

## Run it

```bash
cd p1-payment-failure-explainer
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                   # offline tests, no API key needed
python scripts/explain_sample.py <sample>   # one live call (needs your own API key in .env.server)
```
