# Project 3: Payment Mandate Agent (locked brief, 25 Oct 2026)

## Problem
AI agents have started moving money. Visa and Mastercard agent payments went live with EU issuers in summer 2026, and TrueLayer is testing agent bank payments in the FCA sandbox. No regulator has agent-specific rules yet. Under PSD2 and the UK PSRs, a payment outside the user's instructions is likely "unauthorised", which leaves the payment provider liable (Taylor Wessing, Feb 2026; Pinsent Masons, Jul 2026). The hard part is proving the agent stayed inside its permission, not building the agent. So this project treats the mandate, the policy decision and the audit trail as the product.

## User
The finance or ops person at a small online business, who gives an agent a standing permission (a mandate) for two jobs:
- refunds to customers, from customer emails
- supplier transfers, from invoices and payment requests

## The mandate (modelled on Google AP2 v0.2 Payment Mandate and UK VRP consent control parameters)
max_per_payment, budget_total, monthly limit, max number of payments, allowed payees, allowed actions (REFUND, TRANSFER), valid_from / valid_to, bound agent_id, approval threshold. Any constraint the code doesn't recognise fails closed.

## What the agent does
It reads a messy request and proposes exactly one of: PAY, REFUND, ASK_HUMAN, DECLINE, with the fields it extracted. It never moves money.

## Architecture: MCP server = the bank side
The payment side is an MCP server, and every check lives inside it, so any agent that connects is bound by the same limits.
Tools: get_mandate, lookup_original_payment, check_payee, propose_payment, revoke_mandate.
Inside the server, code always:
1. checks the proposal against the mandate (fail closed)
2. screens the payee against a sanctions list (fuzzy match, logs list version and score) and runs a name-to-account check (Confirmation of Payee for FPS, Verification of Payee for SEPA Instant)
3. applies refund rules: linked to a real original payment, cumulative refunds no more than the original, money only back to the paying account
4. blocks duplicates (idempotency key: same key with different details returns a conflict) and business repeats (same invoice twice)
5. sends anything over the approval threshold, or to a new payee, to human approval (simulated passkey sign-off)
6. issues a single-use scoped payment token per payment; the kill switch revokes the mandate and its tokens
7. writes every decision to a hash-chained audit log and exports a dispute evidence pack

## Rails
UK Faster Payments (GBP) and SEPA Instant (EUR).

## Test set (~40 synthetic requests)
- textbook: clean in-mandate refunds and transfers
- tricky: over limit or over budget across payments, new payee, supplier bank details changed, refund above the original or to another account, duplicate invoice, expired or revoked mandate, sanctions near-match, payee name mismatch
- attacks: prompt injection in the email or invoice text, fake urgency
- truly ambiguous: the right answer is ASK_HUMAN

## Versions
- A: code only (template parsing + the same checks)
- B: one agent working through the MCP server (expected ship)
- C: the same agent with checks switched off in the server; test data only, to measure what gets through
- D: orchestrator plus refund and supplier specialist agents, through the same MCP server

## Hard gate
Zero money moved outside the mandate in any version we ship.

## Scoring
Right action; money wrongly sent (GBP/EUR); unnecessary human escalations; cost and time per request.

## Ship rule
Simplest version that passes the hard gate with the best score.

## Not in v1
Cards (account-to-account only); real cryptographic signatures (simulated with hashes, said so in the README); real sanctions data (a small made-up list styled like the UK list, no real people).

Made-up data only. Nothing from any employer.
