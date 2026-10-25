"""Model settings, prices and limits in one place (same conventions as Project 1)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env.server"  # gitignored; holds ANTHROPIC_API_KEY, never committed or printed

CLAUDE_MODEL = "claude-haiku-5-5"
LLM_TIMEOUT_SECONDS = 30.0
LLM_SDK_RETRIES = 1

# Capabilities as checked for Project 1 (2026-10-17): Haiku 5.5 rejects temperature; effort low is enough for a
# short, tightly constrained task; thinking counts toward max_tokens, hence the cap.
MODEL_SETTINGS = {
    "claude-haiku-5-5": {"max_tokens": 4096, "effort": "low"},
    "claude-sonnet-5-5": {"max_tokens": 4096, "effort": "medium", "timeout_s": 60.0},
}

PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICING_CHECKED_ON = "2026-10-17"
MODEL_PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}

RUN_COST_CAP_USD = 2.00  # a whole eval run stops if it would spend more than this
RUNS_DIR = PROJECT_ROOT / "var" / "runs"  # gitignored
