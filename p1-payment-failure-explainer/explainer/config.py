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
