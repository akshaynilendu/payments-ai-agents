"""Model settings, prices and limits in one place (same conventions as Projects 1 and 2)."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = PROJECT_ROOT / ".env.server"  # gitignored; holds ANTHROPIC_API_KEY, never committed or printed

CLAUDE_MODEL = "claude-haiku-5-5"
LLM_TIMEOUT_SECONDS = 30.0
LLM_SDK_RETRIES = 1
MODEL_SETTINGS = {
    "claude-haiku-5-5": {"max_tokens": 4096, "effort": "low"},
    "claude-sonnet-5-5": {"max_tokens": 4096, "effort": "medium", "timeout_s": 60.0},
}
PRICING_CHECKED_ON = "2026-10-17"
MODEL_PRICES_PER_MTOK = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}

MAX_TOOL_CALLS = 6   # per request, all tools together
MAX_TURNS = 8        # model calls per request
RUN_COST_CAP_USD = 2.00
