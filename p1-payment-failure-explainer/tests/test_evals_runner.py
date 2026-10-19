"""Eval runner tests with fake models: no network, $0."""

import json
import re

import pytest

from evals import run_eval
from evals.make_cases import case_path, load_golden
from evals.run_eval import CostGuard, Options, run
from explainer.embed import FakeEmbedder
from explainer.llm import LLMResponse
from explainer.parse import parse_file

SUBSET = ["sct-ac04", "sct-rr04", "rtp-am04", "sdd-am04", "sct-frad-reject", "sct-cnor", "sct-zz99-invalid",
          "sct-acsc-settled", "sct-pdng-pending", "sct-ac04-injection"]


class FakeSystem:
    """Answers like a well-behaved model: cites the first passage it was given; on COMPLIANCE follows rule 9."""

    def __init__(self, model):
        self.model = model
        self.calls = []

    def complete(self, system, user, schema):
        self.calls.append(user)
        # The first passage: a KB passage, or the ISO definition for a code outside the table (D17).
        ids = re.findall(r"^\[((?:KB|ISO)-[A-Z0-9-]+)\]", user, re.MULTILINE)
        first = ids[0]
        family = [i for i in ids if "-FAM-" in i]  # D18: the family runbook must be cited too
        compliance = "Route (fixed by the routing table): COMPLIANCE" in user
        policy = "Customer message: set by bank policy." in user
        answer = {"what_happened": "The payment was stopped for the reason in the code table.",
                  "next_step": "" if compliance else "Ask the customer to check the details with the other party.",
                  "customer_message": None if compliance or policy else "Your payment could not be completed.",
                  "citations": [first] + family}
        return LLMResponse(json.dumps(answer), 1500, 150, "end_turn")


class FakeJudge:
    def __init__(self, model):
        self.model = model
        self.calls = []

    def complete(self, system, user, schema):
        self.calls.append(user)
        grade = {"pass": True, "reason": "Fine."}
        return LLMResponse(json.dumps({"accurate": grade, "actionable": grade, "safe": grade}), 2000, 300, "end_turn")


def _never(model):
    raise AssertionError("no model client may be created without --yes")


@pytest.fixture
def options(tmp_path):
    return Options(retrieve={"embedder": FakeEmbedder(), "cache_path": tmp_path / "e.npz",
                             "gaps_path": tmp_path / "gaps.jsonl"}, log_path=tmp_path / "log.jsonl")


@pytest.fixture
def made(monkeypatch):
    """Records which fake clients the runner created."""
    created = {}

    def system_factory(model):
        created["system"] = FakeSystem(model)
        return created["system"]

    def judge_factory(model):
        created["judge"] = FakeJudge(model)
        return created["judge"]

    return created, system_factory, judge_factory


def _read(run_dir, name):
    return [json.loads(line) for line in (run_dir / name).read_text().splitlines()]


def test_without_yes_it_only_estimates_and_creates_no_client(options, tmp_path):
    out = []
    result = run("haiku45_rank", yes=False, system_factory=_never, judge_factory=_never, options=options,
                 case_ids=SUBSET, out_dir=tmp_path / "run", echo=out.append)
    assert result is None
    assert "Estimated cost" in out[0] and "Nothing spent" in out[1]
    assert not (tmp_path / "run").exists()


def test_ai_run_grades_and_writes_results(options, made, tmp_path):
    created, system_factory, judge_factory = made
    run_dir = run("haiku45_rank", yes=True, system_factory=system_factory, judge_factory=judge_factory,
                  options=options, case_ids=SUBSET, out_dir=tmp_path / "run", echo=lambda _: None)
    records = {r["id"]: r for r in _read(run_dir, "cases.jsonl")}
    assert set(records) == set(SUBSET)
    for r in records.values():
        for check in ("outcome", "route", "stage", "compliance", "promises", "injection"):
            assert r["grades"][check]["result"] != "fail", (r["id"], check, r["grades"][check])
    assert records["sct-ac04"]["outcome"] == "ai_ok"
    assert records["sct-rr04"]["customer_message"] is None
    assert records["sct-ac04-injection"]["grades"]["injection"]["result"] == "pass"
    assert records["sct-ac04"]["retrieval_candidates"], "rank mode records all candidate scores"
    # The judge grades explanations, not fixed stop messages or unknown codes.
    judged = {j["id"] for j in _read(run_dir, "judge.jsonl")}
    # sct-cnor is now explained beyond the table (D17), so it is judged; ZZ99 (not an ISO code) is not.
    assert judged == {"sct-ac04", "sct-rr04", "rtp-am04", "sdd-am04", "sct-frad-reject", "sct-ac04-injection",
                      "sct-cnor"}


def test_judge_is_blind_to_the_system(options, made, tmp_path):
    created, system_factory, judge_factory = made
    run("haiku45_rank", yes=True, system_factory=system_factory, judge_factory=judge_factory,
        options=options, case_ids=SUBSET, out_dir=tmp_path / "run", echo=lambda _: None)
    for prompt in created["judge"].calls:
        # System identifiers only: "Baseline meaning" is a case fact (the code table's definition), not a system.
        assert not re.search(r"haiku|sonnet|claude-|_rank|_filter|baseline (run|system|config)", prompt, re.IGNORECASE)


def test_summary_shows_code_graders_only(options, made, tmp_path):
    _, system_factory, judge_factory = made
    run_dir = run("haiku45_rank", yes=True, system_factory=system_factory, judge_factory=judge_factory,
                  options=options, case_ids=SUBSET, out_dir=tmp_path / "run", echo=lambda _: None)
    summary = (run_dir / "summary.md").read_text()
    assert "Code graders" in summary
    # Judge grades stay out of summary.md until the blind hand grades are in (D13).
    assert "actionable" not in summary and "accurate" not in summary
    assert "Ship rule" in (run_dir / "judge_summary.md").read_text()


def test_baseline_run_creates_no_system_client(options, made, tmp_path):
    created, _, judge_factory = made
    run_dir = run("baseline", yes=True, system_factory=_never, judge_factory=judge_factory,
                  options=options, case_ids=SUBSET, out_dir=tmp_path / "run", echo=lambda _: None)
    records = {r["id"]: r for r in _read(run_dir, "cases.jsonl")}
    assert records["sct-ac04"]["outcome"] == "baseline"
    assert records["sct-ac04"]["grades"]["outcome"]["result"] == "pass"
    assert records["sct-ac04"]["grades"]["must_cite"]["result"] == "n/a"
    assert records["sct-rr04"]["grades"]["compliance"]["result"] == "pass"
    assert records["sct-ac04"]["cost_usd"] == 0
    assert "system" not in created


def test_cost_cap_stops_the_run_before_overspending(options, made, tmp_path):
    _, system_factory, judge_factory = made
    out = []
    run_dir = run("haiku45_rank", yes=True, system_factory=system_factory, judge_factory=judge_factory,
                  options=options, case_ids=SUBSET, out_dir=tmp_path / "run", echo=out.append, cap_usd=0.005)
    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["stopped"] and meta["cases_run"] < meta["cases_planned"]
    assert meta["spent_usd"] <= 0.005
    assert any("STOPPED" in line for line in out)


def test_cost_guard_checks_worst_case_before_the_call():
    guard = CostGuard(cap_usd=0.01)
    guard.check("claude-haiku-4-5-20251001", 3000)  # ~1000 in + 1024 out at Haiku 4.5 prices: ~$0.006
    guard.spent_usd = 0.006
    with pytest.raises(run_eval.BudgetExceeded):
        guard.check("claude-haiku-4-5-20251001", 3000)


def test_every_config_is_known_and_priced():
    from explainer import config
    for model, _ in run_eval.CONFIGS.values():
        if model:
            assert model in config.MODEL_SETTINGS and model in config.MODEL_PRICES_PER_MTOK
    assert config.JUDGE_MODEL in config.MODEL_SETTINGS and config.JUDGE_MODEL in config.MODEL_PRICES_PER_MTOK


# --- golden file --------------------------------------------------------------------

def test_golden_cases_parse_to_their_declared_rail_stage_and_code():
    cases = load_golden()
    assert len({c["id"] for c in cases}) == len(cases) >= 30
    for c in cases:
        status = parse_file(case_path(c))
        assert (status.rail.value, status.stage.value, status.reason_code) == (c["rail"], c["expect"]["stage"], c["code"])


def test_golden_expectations_are_well_formed():
    from evals.graders import OUTCOMES
    routes = {"FIRST_LINE", "DEVELOPER", "FRAUD", "COMPLIANCE", "TREASURY", None}
    for c in load_golden():
        e = c["expect"]
        assert e["outcome"] in OUTCOMES["ai"], c["id"]
        assert e["route"] in routes, c["id"]
        assert set(e["must_not_contain"]) <= {"any", "customer_message"}, c["id"]
        if e["outcome"] not in ("explained", "explained_beyond"):
            assert e["must_cite"] == [], c["id"]


def test_golden_covers_what_d13_asks_for():
    cases = load_golden()
    assert {c["rail"] for c in cases if c["code"] == "RR04"} == {"SEPA_INSTANT", "SEPA_DD", "RTP"}
    assert {c["expect"]["outcome"] for c in cases} == {"explained", "no_guidance", "escalated", "not_a_failure",
                                                       "pending", "explained_beyond"}
    assert {c["expect"]["route"] for c in cases} >= {"FIRST_LINE", "DEVELOPER", "COMPLIANCE", "TREASURY", "FRAUD"}
    assert any(c.get("injection") for c in cases)


# --- rejudge -----------------------------------------------------------------------

def test_rejudge_regrades_stored_answers_and_keeps_the_old_grades(options, made, tmp_path):
    from evals.rejudge import rejudge
    created, system_factory, judge_factory = made
    run_dir = run("haiku45_rank", yes=True, system_factory=system_factory, judge_factory=judge_factory,
                  options=options, case_ids=SUBSET, out_dir=tmp_path / "run", echo=lambda _: None)
    answers_before = (run_dir / "cases.jsonl").read_text()
    first = (run_dir / "judge.jsonl").read_text()

    assert rejudge(run_dir, yes=False, judge_factory=_never, options=options, echo=lambda _: None) is False
    assert rejudge(run_dir, yes=True, judge_factory=judge_factory, options=options, echo=lambda _: None)
    assert (run_dir / "judge_v1.jsonl").read_text() == first
    assert (run_dir / "judge_summary_v1.md").exists() and (run_dir / "judge_summary.md").exists()
    assert (run_dir / "cases.jsonl").read_text() == answers_before  # no new AI answers
    assert len(_read(run_dir, "judge.jsonl")) == len(first.splitlines())


# --- D17: beyond-the-table slice --------------------------------------------------------

def test_beyond_cases_use_real_iso_codes_outside_our_table_with_verbatim_definitions():
    from explainer.codes import lookup
    from explainer.iso_codes import lookup_iso
    beyond = [c for c in load_golden() if c.get("slice") == "beyond"]
    assert len(beyond) >= 12
    for c in beyond:
        assert lookup(c["code"]) is None, c["id"]
        iso = lookup_iso(c["code"], "PACS_004" if c["message"] == "pacs.004" else "PACS_002")
        if c["expect"]["outcome"] == "explained_beyond":
            # The hand-written definition must match the official list word for word (no circular answer key).
            assert iso is not None and iso.definition == c["iso_definition"], c["id"]
            assert c["expect"]["must_cite"] == [f"ISO-{c['code']}"] and c["expect"]["route"] is None
        else:
            assert iso is None, c["id"]


def test_slice_option_runs_only_that_slice(options, made, tmp_path):
    _, system_factory, judge_factory = made
    run_dir = run("haiku45_rank", yes=True, system_factory=system_factory, judge_factory=judge_factory,
                  options=options, slice_="beyond", out_dir=tmp_path / "run", echo=lambda _: None)
    ids = {r["id"] for r in _read(run_dir, "cases.jsonl")}
    assert ids == {c["id"] for c in load_golden() if c.get("slice") == "beyond"}
    outcomes = {r["id"]: r["outcome"] for r in _read(run_dir, "cases.jsonl")}
    assert outcomes["sct-ab06"] == "ai_beyond_table" and outcomes["sct-zz99-invalid"] == "escalated"


def test_judge_reference_never_contains_the_code_table_text(options):
    from evals.run_eval import _reference
    for c in load_golden():
        refs = _reference(parse_file(case_path(c)), options.retrieve)
        assert all(r["id"] != "CODE-TABLE" for r in refs), c["id"]
    beyond = _reference(parse_file(case_path(next(c for c in load_golden() if c["id"] == "sct-ab06"))),
                        options.retrieve)
    assert beyond[0]["id"] == "ISO-AB06" and beyond[0]["label"] == "ISO 20022 code list"
