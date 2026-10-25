# Decisions (Project 2: Fraud alert investigator)
D1 Scope (v1): the payer's bank, deciding on a flagged outgoing payment on UK Faster Payments or SEPA
Instant. Six outcomes (GENUINE, ACCOUNT_TAKEOVER, APP_IMPERSONATION, APP_INVESTMENT, APP_PURCHASE,
APP_INVOICE_CEO); mule signals on the receiving account are evidence, not an outcome. Made-up data only.
Tonight's build is offline: Version A (code only), no model calls.
D2 Two flows, one engine. A shared core (checks, evidence, Version A rules, guardrails, schema core) and
one flow per rail, selected by alert.rail:
- UK FPS (post-hold decision): FCA FG24/6 deadlines; the name check is labelled Confirmation of Payee; the
  summary adds APP reimbursement facts; menu: RELEASE_WITH_NOTE, CALL_CUSTOMER_REGISTERED_NUMBER,
  ASK_PAYMENT_PURPOSE, REQUEST_INFO_RECEIVING_BANK, ESCALATE_MLRO.
- SEPA Instant (pre-execution decision): no deadlines, with the note "Held before execution; no regulated
  hold window; not sent until decided"; the name check is labelled Verification of Payee; no reimbursement
  facts; menu: EXECUTE_WITH_NOTE, REJECT_BEFORE_EXECUTION, CALL_CUSTOMER_REGISTERED_NUMBER,
  ASK_PAYMENT_PURPOSE, ESCALATE_MLRO.
REQUEST_RECALL_CAMT056 is removed from both menus in v1: we decide before money moves.
D3 UK deadlines (FCA FG24/6, 22 November 2024, paras 3.3-3.4): a PSP may delay a payment until the end of
the 4th business day after receipt if reasonable grounds to suspect fraud are established by the end of
the business day after receipt. Business days exclude weekends and England & Wales bank holidays (gov.uk
bank-holidays.json, Open Government Licence v3.0). A payment received on a non-business day, or at or
after the cut-off (17:00 Europe/London, configurable), counts as received on the next business day; the
cut-off is our modelling assumption. Source: https://www.fca.org.uk/publication/finalised-guidance/fg24-6.pdf
D4 APP reimbursement facts (UK only; facts and arithmetic, never a verdict): the maximum reimbursement is
£85,000 per claim from 7 October 2024 (PSR PS24/7, 2 October 2024,
https://www.psr.org.uk/ps24-7-app-scams-reimbursement-confirming-max-level/). The sending PSP may apply
an excess of up to £100 per claim, or a lower or no excess; it does not apply when the consumer is
vulnerable and the vulnerability had a material impact on their ability to protect themselves, assessed
case by case. The receiving PSP pays 50% of the cost; claims more than 13 months after the last payment
are out of time (PSR PS23/4, December 2023, chapter 3 and chapter 6,
https://www.psr.org.uk/media/kwlgyzti/ps23-4-app-scams-policy-statement-dec-2023.pdf). The summary shows
"up to £100 excess may apply" as a fact, and notes the vulnerability exception when the customer has a
vulnerability flag. Scope is shown as "in scope if confirmed as an APP scam", listing the criteria checked.
D5 Version A conflicts: rules have a fixed priority order. The highest-priority rule that fires sets the
leading hypothesis; evidence from every other rule that fires goes to evidence_against.
INSUFFICIENT_EVIDENCE only when no rule fires.
D6 No demographic profiling: age band is never a signal for any fraud type. It is used only as a
vulnerability flag. A test changes every customer's age band and checks Version A's hypothesis never moves.
D7 Payment data is data. The reference and payee name are quoted in facts and never parsed for meaning or
instructions; rules read only structured check results. Two hard cases carry prompt-injection text (one in
a UK payment reference, one in a SEPA payee name).
D8 Fair test, no leakage. Every past case is dated before every alert; the gold answers live in gold/,
which no version reads (the loader refuses that folder, and a test scans the code). Alerts: 24 UK, 16 SEPA;
every outcome on both rails; 6 hard cases (UK: 1 mixed, 2 novel, 1 injection; SEPA: 1 mixed, 1 injection).
D9 Details settled while building Version A (offline):
- Reimbursement scope adds a fourth criterion: the receiving account is not controlled by the customer.
  PS23/4 (p.17) adds "account controlled by the consumer" to the definition of an APP scam payment; the
  full wording is in the legal instruments, which we have not read yet. Version A flags an own-name payee
  as "to be checked", never as out of scope.
- evidence_for holds the leading rule's evidence, plus receiving-account (mule) evidence for any fraud
  hypothesis: it supports, it never decides. evidence_against holds the other rules' evidence (D5) and,
  for a fraud hypothesis, "payee is one of the customer's usual payees".
- ESCALATE_MLRO is added when the receiving account shows a mule pattern (opened < 7 days ago and >= 10
  unrelated payers), >= 2 fraud reports, or one of our own closed fraud cases paid it.
- Version A never proposes REJECT_BEFORE_EXECUTION: refusing a payment is the human's call.
- Thresholds (3x usual, 2,500 modest, 72 h SIM swap, 90/180/7 day account ages, 10 inbound payers,
  60 min money-out, similarity >= 0.5) live in one block in investigator/checks.py.
- (Superseded by D10.) Version A first scored 36/36 on familiar cases, by construction: the generator and
  the rules shared the same signal profiles.
D10 Realistic variants (Oct 24). A baseline that scores 100% has written its own exam (the P1 lesson). 11 of
the 34 familiar alerts are now ordinary cases that don't match the textbook profile, in both directions:
- fraud that misses one tell-tale signal: account takeover by phishing with no SIM swap; a SIM swap 4-6 days
  old; an impersonation victim coached to keep the amount at 2-2.8x usual; a first, already-large investment
  deposit (no series yet); a brand-new seller account nobody has reported; landlord-bank-details fraud
  against a retail customer;
- genuine payments that trip a rule: a phone upgrade then a new tradesperson; paying a relative for a car
  while on the phone with them (x2); a second-hand purchase from a young account with one unfounded report;
  a real supplier that moved banks.
They stay "familiar" (real queues are full of them); gold records the variant name. Caveat for the write-up:
the variants were written knowing the rules, so they are a stress test of the rule set, not a measured
real-world miss rate.
Version A after D10 (scripts/score_version_a.py): 25/40 (62%); textbook 23/23; variants 0/11; hard 2/6;
FPS 13/24, SEPA 12/16. It never labels a fraud case GENUINE (pinned by a test): its misses are false alarms
on genuine payments or "insufficient evidence" on fraud, which sends the case to a human.
D11 Version B: fixed workflow + AI assessment (Oct 24). Every check runs (same as A); Haiku 5.5 then picks the
leading hypothesis, the evidence for and against (by id only), up to 4 missing-information questions (no
numbers) and a one-or-two sentence rationale citing facts as [id].
- The model picks, code writes the facts: evidence text always comes from the checks, so invented facts in the
  evidence are impossible by design (the PayPal SAR-drafting failure). The rationale is checked: every [id]
  must exist and every number must appear in a cited fact.
- Payment data (reference, payee name) goes in a separate <payment_data> block and is never instructions; an
  answer whose case rests on payment data alone is rejected (D7).
- Next steps and MLRO escalation stay code-owned, exactly as in Version A, so A vs B tests judgement only.
- One retry with the failed checks listed; then fall back to Version A's summary, recorded in the run.
- Cost cap: $2 per eval run (config.RUN_COST_CAP_USD).
D12 Error costs for scoring (assumptions; only their order matters): steering a fraud case toward release
(labelled GENUINE) costs the payment amount; a false alarm on a genuine payment 25; "insufficient evidence"
15; the wrong fraud type 10. Hard gates before any comparison: zero fraud cases labelled GENUINE, zero
injection cases labelled GENUINE.
D13 Version B, round 2 (Oct 24), after the first full run (v1: 24/40; textbook 17/23, variants 5/11, hard 2/6;
one fraud case labelled GENUINE, AL-022; 20 retries, 5 fallbacks). Three general fixes, no case-specific tuning;
both runs are reported.
- Numbers in missing_information are allowed only if they appear in the facts (same rule as the rationale).
  The blanket "no numbers" rule caused 24 of the retries.
- The prompt now says vulnerability indicators change how carefully the customer is treated, never what is
  suspected (v1 asked for a call-back on a usual payee because the customer was a carer). Same principle as D6.
- GENUINE gate, in code: the model may not label a payment GENUINE while a red flag is present (new device,
  recent SIM swap, remote access, on a call, mule pattern, repeated reports, our own fraud cases on the
  account, name check no match, known name with a new account, or a payment >= 3x usual to a new payee). The
  case becomes INSUFFICIENT_EVIDENCE, the model's reasoning is kept, and the run records the flags. v1 labelled
  a 20x payment to a new own-name account (a classic investment-scam route via an own-name crypto account)
  GENUINE. Policy in code, not prompts (Project 1's lesson).
Caveat: rounds 1 and 2 use the same 40 alerts, so round 2 can overfit; the fixes are general rules, and the
write-up reports both rounds.
