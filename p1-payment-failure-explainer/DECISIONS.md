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
