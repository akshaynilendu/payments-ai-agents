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

## V2 list
Parked ideas, not in v1:
- camt.056 (recall) and camt.029 (recall answer) parsing, with samples.
- Full rulebooks in the knowledge base (downloaded locally, never committed; D7).
- Postgres + pgvector, only when a D9 trigger applies.
- Claude Haiku 5.5 as an eval contender on day 3 (released Oct 7, 2026; 10x cheaper; rejects temperature).
- Masking names written in free text (the xfail test in test_masking.py).
- Treating a pacs.004 with FOCR as a recall answer rather than a return.
