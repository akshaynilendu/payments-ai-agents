"""Tunable values in one place, so evals can change them without touching logic."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Small model by default (CLAUDE.md); evals compare it with a larger one by changing this value only.
CLAUDE_MODEL = "claude-haiku-4-5-20251001"

# Retrieval (D7, D8).
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"  # open-weight, MIT, 384 dimensions, ~67 MB ONNX
RETRIEVAL_K = 3
# Placeholder: 0.0 never drops a passage for its score. The day-3 evals set the real value (D7).
RETRIEVAL_THRESHOLD = 0.0

# Official ISO 20022 external code sets (D17), downloaded by hand from https://www.iso20022.org/
# (the site blocks automated downloads). Gitignored: only a small attributed extract is committed.
ISO_CODE_SETS_FILE = PROJECT_ROOT / "data" / "external" / "2Q2026_externalcodesets_v3.json"
ISO_CODE_SETS_RELEASE = "2Q2026 v3"

# Local runtime files: all under gitignored folders, never committed.
VAR_DIR = PROJECT_ROOT / "var"
EMBEDDINGS_CACHE = VAR_DIR / "embeddings.npz"
GAPS_FILE = VAR_DIR / "knowledge_gaps.jsonl"
MODEL_CACHE_DIR = PROJECT_ROOT / ".cache" / "fastembed"

# AI explanation (piece 3, D11).
ENV_FILE = PROJECT_ROOT / ".env.server"  # gitignored; holds ANTHROPIC_API_KEY, never committed
LLM_TEMPERATURE = 0  # D5: repeatable answers, so evals compare like with like
LLM_MAX_OUTPUT_TOKENS = 1024  # four short fields; a hard cap on cost per call
LLM_TIMEOUT_SECONDS = 10.0  # D4: at most 10 seconds per case
LLM_SDK_RETRIES = 1  # network/5xx/429 retries inside the SDK; check-failure retries are separate (D3)

# Per-model request settings. Capabilities checked with the Models API and the Claude API docs on 2026-10-17.
# A model missing here is an error, so no model runs with settings meant for another.
MODEL_SETTINGS = {
    # No effort or adaptive thinking on Haiku 4.5; temperature 0 for repeatable answers (D5).
    "claude-haiku-4-5-20251001": {"max_tokens": LLM_MAX_OUTPUT_TOKENS, "temperature": LLM_TEMPERATURE},
    # Haiku 5.5 rejects any temperature but 1, so it is omitted. Thinking is on by default and counts toward
    # max_tokens, and its tokenizer uses ~30% more tokens, hence the higher cap. Effort defaults to medium;
    # low is the documented way to think less, and this is a short, tightly constrained task.
    "claude-haiku-5-5": {"max_tokens": 4096, "effort": "low"},
    # LLM judge (D13). Non-default temperature is rejected; effort defaults to high, medium is enough for
    # three pass/fail grades. Thinking makes it slower than the 10 s case budget, which doesn't apply to grading.
    "claude-sonnet-5-5": {"max_tokens": 3000, "effort": "medium", "timeout_s": 60.0},
}
JUDGE_MODEL = "claude-sonnet-5-5"
EXPLAIN_LOG = VAR_DIR / "explain_log.jsonl"

# Prices per million tokens (input, output), from the official pricing page.
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICING_CHECKED_ON = "2026-10-17"
MODEL_PRICES_PER_MTOK = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
    "claude-haiku-5-5": (0.10, 0.50),  # prompts up to 100K tokens; ours are ~2K
    "claude-sonnet-5-5": (2.00, 10.00),
}
