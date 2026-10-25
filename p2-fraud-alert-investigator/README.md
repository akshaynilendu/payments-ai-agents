# Fraud Alert Investigator

A bank's fraud system flags a payment. An investigator now has to work out **what kind of fraud it might be, what the evidence says for and against, and what to do next**, before the money moves. This project builds an assistant that does that research and writes a cited case summary. **The investigator always decides.**

> Portfolio project. **Made-up data only.** No real payments, customers or bank data.

---

## The problem

Fraud teams review thousands of flagged payments a day. Most are genuine, but each still takes 15–30 minutes of digging: is this normal for the customer, is it their device, who is receiving the money, have we seen this before? Meanwhile real fraud hides in the pile, and today most of it is **authorised push payment (APP) scams**, where the genuine customer is tricked into paying (UK losses £576.4m in 2025, up 19%: UK Finance). With instant payments, the money is gone in seconds.

At The Clearing House I built the reporting banks used to track fraud recall requests (camt.056, reason FRAD): the end of the line, after the money has gone. This project works at the start of the line.

**User:** an L1/L2 fraud investigator at the **payer's** bank, deciding on a flagged outgoing payment.
**Rails (v1):** UK Faster Payments and SEPA Instant, as **two flows on one engine**: same evidence, different decision rules.

| | UK Faster Payments | SEPA Instant |
|---|---|---|
| When the decision happens | Payment held; decide by end of 4th business day (FCA FG24/6) | Before execution; no regulated hold window |
| Name check | Confirmation of Payee | Verification of Payee |
| Refund rules | Mandatory APP reimbursement facts (£85,000 cap, 50:50 split, excess, vulnerability exception) | None in force yet |

---

## How it works

1. **Core checks always run** (code, read-only): customer history, device and login, **payee and receiving-account risk** (mandatory: in authorised scams the payer side looks clean, the evidence is on the receiving side), prior reports, similar past cases.
2. **Code rules first.** If a written rule fires (e.g. new device + recent SIM swap → account takeover), its answer stands. Fast, free, predictable.
3. **AI only where the rules have no answer.** The model picks the likely fraud type, the evidence for and against, and what's missing. **It refers to evidence by id only; the fact text always comes from the checks**, so it cannot put an invented fact into the evidence.
4. **Code checks every AI answer:** every id must exist, every number in its rationale must appear in a cited fact, payment data (reference, payee name) is fenced off as untrusted text and can never carry the case on its own.
5. **The GENUINE gate (code):** the AI may never label a payment genuine while a red flag is present (new device, recent SIM swap, remote access, large first payment to a new payee, mule pattern…). The case goes to a human instead.
6. **Next steps come from a fixed menu per rail**, chosen by code. The tool cannot release, hold, block or contact anyone, and writes no customer text (no tipping off).

---

## What I tested, and what I found

**40 made-up alerts** (24 UK, 16 SEPA): 23 textbook cases, **11 realistic variants** (fraud missing one tell-tale sign; genuine payments that trip a rule), 6 hard cases (mixed signals, novel patterns, 2 prompt-injection attempts). Correct answers kept in a separate file no version can read.

| Version | Right (of 40) | Textbook (23) | Variants (11) | Hard (6) | Fraud labelled genuine | Error cost* | $ per alert |
|---|---|---|---|---|---|---|---|
| A. Code rules only | 25 | **23** | 0 | 2 | 0 | 280 | $0 |
| B. AI on every alert | 26 | 19 | 5 | 2 | 0 | 245 | $0.00075 |
| C. AI agent with investigation tools | 29 | 20 | **6** | 3 | 0 | 205 | $0.00134 |
| **H. Code first, AI on the gaps** (3 runs) | **30, 30, 30** | **23** | 4 | 3 | **0** | **200** | **$0.00017** |
| HC. Code first, agent on the gaps (3 runs) | 30–31 | 23 | 5 | 2–3 | 0 | 190–205 | $0.00028 |

*Error cost weights the mistakes: steering a fraud case toward release costs the payment amount; a false alarm 25; "insufficient evidence" 15; the wrong fraud type 10. Only the order matters.

**What happened along the way:**
- **My first baseline scored 100% on everyday cases.** That told me the test data was too clean: the same profiles had written the data and the rules. Adding realistic variants dropped it to 62%, an honest baseline.
- **The first AI run labelled a 20× payment to a new own-name account "genuine"**, a classic investment-scam route via an own-name crypto account. That led to the **GENUINE gate in code**. After it, no version waved fraud through in any run.
- **The AI asked for a call-back on a routine payment because the customer was flagged as a carer.** Vulnerability changes how carefully you treat someone, never what you suspect; the prompt now says so (and age is never used as a fraud signal).
- **The agent barely used its tools** (one extra lookup per run in HC). The small HC–H gap is run-to-run noise, at 65% more cost.

**Decision:** ship **H, code first, AI on the gaps.** Perfect on textbook patterns, stable across runs, zero fraud waved through, $0.0002 per alert. In short: **deterministic where you can, AI where you must.** (Project 1 reached the same design independently.)

**What I learned:**
- **A baseline that scores 100% has written its own exam.** Make the test data messy before trusting any score.
- **Code and AI fail on different cases.** Rules are perfect on the patterns they were written for and blind beyond them; the AI catches some of what rules miss. Combine them; don't choose.
- **Put the costliest mistake behind code.** The AI can suggest "genuine"; code decides when it's allowed.
- **More freedom isn't automatically better.** I built the agent and measured it; the simpler workflow won.

**Limits (stated plainly):** 40 made-up alerts; variants were written knowing the rules (a stress test, not a measured miss rate); round 2 fixed checks after seeing round 1 on the same alerts; AI answers vary run to run. Next: a held-out set nobody has tuned on.

---

## Key decisions (full list in `DECISIONS.md`)

- **The AI never decides** and has no tool that moves money or contacts anyone.
- **The model picks, code writes the facts** (evidence by id), with numbers and ids checked.
- **Payment data is data, never instructions**; a case can't rest on it alone.
- **No demographic profiling:** age is a vulnerability flag only, tested so it never changes the hypothesis.
- **No hindsight:** similar-case search and tools only see cases closed before the alert.
- **Two rails, one engine:** UK and SEPA differ in timing, name checks, refunds and menus, not in evidence.

---

## Regulation and safety

- **UK:** FCA FG24/6 payment delay deadlines; PSR APP reimbursement (£85,000 cap, 50:50 sending/receiving split, up to £100 excess, vulnerability exception), shown as facts, never a verdict.
- **EU:** Verification of Payee (Instant Payments Regulation, from Oct 2025); SEPA Instant has no hold window.
- **Tipping off:** no customer-facing text at all in v1; escalation to the money-laundering reporting officer is a code-owned menu step.
- **EU AI Act:** fraud detection is outside the high-risk credit-scoring category; the tool's purpose is documented as fraud investigation support only.

---

## Run it

```bash
cd p2-fraud-alert-investigator
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pytest -q                                        # offline tests, no API key needed
python scripts/run_eval.py --version A           # code only, $0
python scripts/run_eval.py --version H           # needs your own ANTHROPIC_API_KEY in .env.server
```
