"""Find the knowledge passages for a failed payment: filter by code and rail, then rank (D7, D8)."""

import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from functools import cache
from pathlib import Path
from typing import Sequence

import numpy as np

from explainer import config, knowledge
from explainer.codes import FAILURE_STAGES, Rail, Stage, lookup
from explainer.embed import Embedder, FastEmbedEmbedder, passage_vectors
from explainer.knowledge import KbRail, Passage, Topic, all_passages, family_of


class Mode(StrEnum):
    FILTER_RANK = "filter_rank"
    # No embeddings at all: the simple baseline the day-3 evals compare against (D8).
    FILTER_ONLY = "filter_only"


@dataclass(frozen=True)
class Retrieved:
    passage: Passage
    score: float | None  # cosine similarity; None in filter_only mode


@dataclass(frozen=True)
class RetrievalResult:
    ranked: tuple[Retrieved, ...]
    # Guardrails for this code, returned regardless of score: safety is never left to ranking (D8).
    mandatory: tuple[Retrieved, ...]
    # True when no ranked passage qualified: the caller skips the AI call and shows the baseline (D7).
    gap: bool

    def all(self) -> tuple[Retrieved, ...]:
        return self.mandatory + self.ranked


RAIL_LABELS = {
    Rail.RTP: "RTP (US real-time payments)",
    Rail.SEPA_INSTANT: "SEPA Instant Credit Transfer",
    Rail.SEPA_DD: "SEPA Direct Debit",
    Rail.UNKNOWN: "unknown payment rail",
}

# filter_only has no scores, so it orders by what operations usually need first.
_TOPIC_ORDER = [Topic.NEXT_STEP, Topic.MEANING, Topic.WHO_ACTS, Topic.CUSTOMER_MESSAGE,
                Topic.TIME_LIMIT, Topic.RECALL_RETURN]

_SAFE_CODE = re.compile(r"[A-Z0-9]{1,35}")


def safe_code(code: str) -> str:
    """Codes go into logs; proprietary codes can hold up to 35 characters, anything else is not logged as-is."""
    return code if _SAFE_CODE.fullmatch(code or "") else "INVALID"


def matches(passage: Passage, code: str, rail: Rail) -> bool:
    """Same rail (or ALL), and either about this code or a general passage that names no code."""
    rail_ok = passage.rail is KbRail.ALL or passage.rail.value == rail.value
    # Family passages (D18) serve only codes outside the table, via family_passages().
    return rail_ok and not passage.families and (code in passage.codes or not passage.codes)


def stage_matches(passage: Passage, stage: Stage) -> bool:
    # Unknown stage: we don't know whether money moved, so only advice true at every stage can't mislead.
    if stage is Stage.UNKNOWN:
        return set(passage.stages) == set(FAILURE_STAGES)
    return stage in passage.stages


def general_passages(rail: Rail | str, stage: Stage | str) -> list[Retrieved]:
    """Passages that name no code, for this rail and stage: all a code outside our table can draw on (D17)."""
    rail, stage = Rail(rail), Stage(stage)
    found = [p for p in all_passages()
             if not p.codes and not p.mandatory and matches(p, "", rail) and stage_matches(p, stage)]
    return [Retrieved(p, None) for p in sorted(found, key=lambda p: (_TOPIC_ORDER.index(p.topic), p.id))]


def family_passages(code: str, stage: Stage | str) -> list[Retrieved]:
    """The team runbook passage(s) for the family of a code outside our table (D18)."""
    family, stage = family_of(code), Stage(stage)
    return [Retrieved(p, None) for p in all_passages()
            if family and family in p.families and stage_matches(p, stage)]


def build_query(code: str, rail: Rail) -> str:
    entry = lookup(code)
    return (f"{code} {entry.name}: {entry.meaning} Payment rail: {RAIL_LABELS[rail]}. "
            f"What does this mean and what should operations do next?")


@cache
def _default_embedder() -> Embedder:
    # Loaded once per process: model start-up takes far longer than a single query.
    return FastEmbedEmbedder()


def retrieve(code: str, rail: Rail | str, stage: Stage | str, mode: Mode | str = Mode.FILTER_RANK,
             k: int = config.RETRIEVAL_K, threshold: float = config.RETRIEVAL_THRESHOLD, *,
             embedder: Embedder | None = None,
             passages: Sequence[Passage] | None = None,
             passages_path: Path = knowledge.DEFAULT_PATH,
             cache_path: Path = config.EMBEDDINGS_CACHE,
             gaps_path: Path = config.GAPS_FILE) -> RetrievalResult:
    """stage is required on purpose: a default would quietly bring back recall advice for rejects (D10)."""
    code = (code or "").strip().upper()
    rail, stage, mode = Rail(rail), Stage(stage), Mode(mode)
    if stage in (Stage.NOT_A_FAILURE, Stage.PENDING):
        # The caller must stop before retrieval; reaching here is a bug, not a knowledge gap.
        raise ValueError(f"nothing to explain at stage {stage.value}; stop before retrieval")

    # Unknown codes escalate (D3); general rail passages would look like guidance they are not.
    if lookup(code) is None:
        _record_gap(gaps_path, code, rail, stage, mode, threshold, "unknown_code")
        return RetrievalResult(ranked=(), mandatory=(), gap=True)

    pool = list(passages) if passages is not None else list(all_passages())
    candidates = [p for p in pool if matches(p, code, rail)]
    # Guardrails apply at every stage, enforced here rather than trusted to their tags (D8).
    guardrails = [p for p in candidates if p.mandatory]
    rankable = [p for p in candidates if not p.mandatory and stage_matches(p, stage)]

    if mode is Mode.FILTER_ONLY:
        ordered = sorted(rankable, key=lambda p: (not p.codes, _TOPIC_ORDER.index(p.topic), p.id))
        ranked = tuple(Retrieved(p, None) for p in ordered[:k])
        mandatory = tuple(Retrieved(p, None) for p in guardrails)
    else:
        embedder = embedder or _default_embedder()
        scores = _scores(code, rail, pool, embedder, passages_path, cache_path)
        above = sorted((p for p in rankable if scores[p.id] >= threshold),
                       key=lambda p: (-scores[p.id], p.id))
        ranked = tuple(Retrieved(p, scores[p.id]) for p in above[:k])
        mandatory = tuple(Retrieved(p, scores[p.id]) for p in guardrails)

    if not ranked:
        reason = "no_passage_matches_filter" if not rankable else "none_above_threshold"
        _record_gap(gaps_path, code, rail, stage, mode, threshold, reason)
    return RetrievalResult(ranked=ranked, mandatory=mandatory, gap=not ranked)


def _scores(code: str, rail: Rail, pool: list[Passage], embedder: Embedder,
            passages_path: Path, cache_path: Path) -> dict[str, float]:
    # The whole pool is embedded (and cached) once, not just the candidates, so the cache fits every query.
    vectors = passage_vectors([p.id for p in pool], [p.text for p in pool], embedder, passages_path, cache_path)
    query = embedder.embed_query(build_query(code, rail))
    similarities = np.asarray(vectors) @ query
    return {p.id: float(s) for p, s in zip(pool, similarities)}


def _record_gap(path: Path, code: str, rail: Rail, stage: Stage, mode: Mode, threshold: float,
                reason: str) -> None:
    """Append-only log of missing guidance. Only code and rail: never amounts, IDs, names or free text."""
    record = {
        "timestamp": datetime.now(UTC).isoformat(timespec="seconds"),
        "code": safe_code(code),
        "rail": rail.value,
        "stage": stage.value,
        "mode": mode.value,
        "threshold": threshold,
        "reason": reason,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")
