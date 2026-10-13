# payments-ai-agents
A public portfolio of AI workflows and agents for payments operations, built by Akshay Nilendu (ex-Java developer on US real-time payments, now an MBA aiming for AI product roles in payments). Five projects, one folder each.

## Rules
- Data: made-up or public data only. Nothing from any employer (no Legnds, no The Clearing House data). No real personal data.
- Secrets: never write API keys into any file. Read ANTHROPIC_API_KEY from the environment only. Keep .env files out of git.
- Money: test environments only, never real money. Never deploy anything.
- Git: never commit or push without asking me first.
- Before writing each piece of code: explain in 2-3 plain sentences what it does, why, and the Java equivalent (I know Java, not much Python). Then build it, then stop and wait for me.
- Small steps: one piece at a time, with tests (pytest). No big rewrites.
- Code: simple and readable; comments explain WHY, not what. Python 3.14, one virtual environment per project.
- Models: default to the small model (claude-haiku-4-5-20251001), set in one config value so evals can compare it with a larger one.
- Every project README covers: the problem, the user, the decisions and why, evals vs a simple baseline, cost and speed per case, ops metrics (handling time, error rate, cost per case), what broke and how it was fixed, regulation notes (GDPR, EU AI Act), and what v2 would add.
