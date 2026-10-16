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
EXPLAIN_LOG = VAR_DIR / "explain_log.jsonl"

# Prices per million tokens (input, output), from the official pricing page.
PRICING_URL = "https://platform.claude.com/docs/en/about-claude/pricing"
PRICING_CHECKED_ON = "2026-10-15"
MODEL_PRICES_PER_MTOK = {
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}
