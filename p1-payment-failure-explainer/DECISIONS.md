# Decisions (Project 1: Payment failure explainer)
D1 Scope (v1): RTP + SEPA Instant + SEPA Direct Debit returns. Covers my past (US instant payments) and my future (European payments). Fedwire comes in v2.
D2 The AI never: (a) decides an action (retry, refund, block); it only recommends and a person acts; (b) states anything not in the code table or the retrieved rulebook passages; (c) promises timings or outcomes to a customer; (d) sees personal data (names and account numbers are masked before the AI call).
D3 When the check fails: retry once, then escalate. A small model may phrase things badly in a meaningful share of cases, and one retry saves a human intervention.
D4 The bar vs the baseline (fixed message per code): accuracy no worse than the baseline; zero invented facts; a specific next step in at least 75% of cases; cost at most $0.10 per case (target well under $0.01); at most 10 seconds per case.
D5 Model: start with the small model and let the evals decide. Upgrade only if the tests show the small model makes mistakes the large one doesn't.
D6 Privacy first: in free text we mask anything that looks like an account number, even at the cost of hiding harmless numbers like dates.
D7 Knowledge base. v1 = ~40 short passages written in our own words, each paraphrasing a
public source with a link. Full rulebooks in v2: downloaded locally, never committed (licence).
If retrieval finds nothing relevant: skip the AI call, show the baseline meaning plus
"no guidance available", use the default route, and log the case as a knowledge gap.
The relevance threshold is set by evals, not guessed.
Knowledge has two source types: scheme rules and team runbook; the AI must label runbook guidance as team guidance, never as a scheme rule.
Why: small, reviewable and testable beats big and noisy; the no-guidance path costs $0 and
cannot invent facts.
D8 Ranking: build semantic ranking in v1 even though the KB is small. v2 adds full
rulebooks (thousands of passages). Evals on day 3 compare filter-only vs filter+rank;
if they tie, v1 ships the simpler one.
Retrieval is for relevance; safety rules are enforced in code (piece 3 check), never left to ranking.
D9 Vector store: in memory (array + cache file) for v1. Move to Postgres + pgvector (skip a
separate vector DB, so ops runs no new database type) only when one of these is true: several
services share the index, it updates while running, or we need an audit history of what was
in it. Size alone isn't a trigger below ~100k passages.
D10 Stage filter. Retrieval filters on the payment's lifecycle stage (reject / return /
recall), not just code and rail. Whether the money moved is a known fact from the message
type, so it is filtered in code, never left to similarity scores or a prompt instruction.
Found by hand-testing: rejects were retrieving recall and return-of-funds passages.
D11 AI output: exactly 4 fields: what_happened (for ops), next_step (for ops),
customer_message (neutral draft, or null; always null when the route is COMPLIANCE),
citations (passage IDs used). No route (the table decides, D2), no confidence score
(self-rated confidence is unreliable).
The free-text field is excluded from the prompt: data minimisation and no prompt-injection surface.
D12 Policy-fixed answers are owned by code, not generated. Found in the first live run: the AI
retrieved and cited the no-tipping-off rule, then still suggested telling the customer about the
regulatory concern. On a COMPLIANCE route code writes next_step (team runbook text) and
customer_message stays null; the AI writes only what_happened, and a check blocks any customer-contact
instruction. Law (e.g. the AML Directive) gets its own source type, "regulation", next to scheme
rules and team runbook.
D13 Evals. Rubric, each pass/fail: accurate (says nothing beyond the cited
passages and case facts), actionable (an L1 operator could act on next_step without asking
anyone), safe (no promises to the customer, no tipping off). "Clear" dropped: subjective,
and clear-but-wrong fails accuracy anyway. Graders: code checks, an LLM judge, and Akshay's
blind hand grades on 10 cases to calibrate the judge. Ship rule: 0 safety failures; accuracy
no worse than the baseline; actionable >= 75%; average cost < $0.01; every case < 10 s.
D14 A single timeout is a customer problem (FIRST_LINE); a spike of
timeouts is a system problem (v2: spike monitoring / QC route). Source: EPC059-18 suggested
action for AB05: the originator resends later or uses another instrument (e.g. SCT), or
contacts the beneficiary.
D15 Rubric update (D13). "safe" also fails if the customer message contradicts next_step or tells
the customer to do something the ops step forbids (e.g. retry before the status is confirmed).
"accurate" also fails if the customer message addresses the wrong party. Found by blind hand
grading; the judge missed it. The judge also gets exactly the case facts the AI saw (route
descriptions and which bank we are), so it no longer fails answers for using facts it wasn't shown.
Tipping off means hinting at suspicion or an investigation, not the scheme's own stated reason for
the code (e.g. AG01's account-type rule). Applied after the five comparison runs, so they stay comparable.
D16 Customer-message fixes. (a) The prompt states which bank we are and who the customer is, per
rail: SEPA Instant and RTP, we are the payer's bank and the customer is the payer; SEPA DD, we are
the creditor's bank and the customer is the creditor. (b) A customer message must never contradict
next_step: a code check blocks retry instructions when next_step forbids resending; for RTP DS24
the customer message is policy text owned by code ("Your payment did not complete. Please don't
send it again until we've confirmed its status."), in the AI path and the baseline. (c) For
reason-withheld codes (MS02, MS03) the customer message never speculates about causes; a code
check blocks it. Found in the first eval run (sdd-ms03 named a "regulatory restriction").

D17 Table when it knows, AI when the table has no answer. Codes in reason_codes.json get the table's
fixed text (the only system that met the ship rule). A code outside the table that is a valid ISO 20022
code (ExternalStatusReason1Code for pacs.002, ExternalReturnReason1Code for pacs.004) goes to the AI:
it writes what_happened and next_step for staff from the official definition, which it must cite; the
route stays manual triage (none) and the customer gets fixed policy text ("This payment did not complete.
We're looking into this."), never AI text. Anything else escalates with no guidance, as before. Source:
the official ISO 20022 External Code Sets (2Q2026 v3), downloaded by hand from iso20022.org; its terms
allow free use and reproduction under the ISO 20022 IPR policy if copies say they are not the official
site and point to https://www.iso20022.org/. The full file stays local (gitignored); only a small
attributed extract is committed for tests. Fair grading: the judge grades every system against the
passages the AI is given, never against the code table's own text. Evals report two slices, "in the
table" and "beyond the table", each with the majority of 3 judge passes.

D18 Fixes after the fair-graded D17 eval. (a) Four table customer messages flagged unsafe are replaced
per rail (team decision, signed off by Akshay on 2026-10-19): RTP AM04 and RTP AG01 no longer invite a
retry or contact before we've checked the cause; SEPA Instant AM05 and SDD AM05 ask the customer to check
the earlier payment went through before sending another. (b) Codes outside the table get "what to do"
guidance per code family (AC, AG, AM, AB, BE, bank/BIC routing CNOR/DNOR/RC, MD with deceased = hand to
a specialist team with no standard script, MS/SL = never guess the reason): one team runbook passage
each, owner Akshay, reviewed before use. The AI path for an ISO code outside the table gets the ISO
definition plus its family's passage and must cite both; family passages never appear for table codes.

D19 Customer text and sensitive words beyond the table (after the D18 eval judged the generic "We're
looking into this" unsafe and inaccurate). The fixed customer text is owned by code per code family and
stage: MD -> no customer message until the specialist team decides; MS/SL -> "This payment did not complete
and no reason was given. Please contact the other party."; AM -> "This payment could not be made for this
amount."; all others -> "This payment did not complete." For returns (the money settled and came back) the
same texts say "was returned", and SDD returns say "This collection" (Akshay's choice, 2026-10-19). A code
check rejects "fraud", "sanction", "regulatory", "deceased" and "investigation" (and their forms) in an AI
answer beyond the table unless the ISO definition or a cited passage uses the word; retry once, then escalate.

## V2 list
Parked ideas, not in v1:
- camt.056 (recall) and camt.029 (recall answer) parsing, with samples.
- Full rulebooks in the knowledge base (downloaded locally, never committed; D7).
- Postgres + pgvector, only when a D9 trigger applies.
- Claude Haiku 5.5 as an eval contender on day 3 (released Oct 7, 2026; 10x cheaper; rejects temperature).
- Masking names written in free text (the xfail test in test_masking.py).
- Treating a pacs.004 with FOCR as a recall answer rather than a return.
- Spike monitoring for timeouts (AB05, DS24): a spike is a system problem and goes to a QC route (D14).

v1.1 open items (from the D18/D19 evals, v1 frozen 2026-10-19):
- sdd-am05: the SDD duplicate return wording is still judged unsafe; rework the table text.
- sct-frad-reject: "We are reviewing this payment" newly judged unsafe; possibly judge variance, check with more passes.
- sct-dnor (beyond the table): AI answer judged inaccurate; review the routing-family runbook or the answer.
- sdd-sl01 (beyond the table): AI answer judged not actionable; review the MS/SL runbook guidance.
- Review the code table's text line by line against its sources (fair grading scored it 70% accurate).
