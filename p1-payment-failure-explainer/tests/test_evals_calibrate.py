import csv
import json

import pytest

from evals.calibrate import calibrate, read_human, read_judge
from evals.make_grading_sheet import COLUMNS, N_AI, N_BASELINE, pick, write_sheet


def _grade(accurate, actionable, safe, reason="r"):
    return {"accurate": {"pass": accurate, "reason": reason}, "actionable": {"pass": actionable, "reason": reason},
            "safe": {"pass": safe, "reason": reason}}


def _sheet(tmp_path, rows):
    path = tmp_path / "grades.csv"
    with path.open("w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(COLUMNS)
        writer.writerows(rows)
    return path


def test_read_human_accepts_pass_fail_spellings(tmp_path):
    sheet = _sheet(tmp_path, [["a", "...", "pass", "FAIL", "y", "ok"], ["b", "...", "n", "1", "no", ""]])
    human = read_human(sheet)
    assert human["a"] == {"accurate": True, "actionable": False, "safe": True, "note": "ok"}
    assert human["b"] == {"accurate": False, "actionable": True, "safe": False, "note": ""}


def test_read_human_refuses_blank_or_unclear_cells(tmp_path):
    sheet = _sheet(tmp_path, [["a", "...", "pass", "", "maybe", ""]])
    with pytest.raises(ValueError, match="a.actionable.*a.safe"):
        read_human(sheet)


def test_calibration_counts_agreement_and_direction_of_disagreement():
    human = {"a": {"accurate": True, "actionable": True, "safe": False, "note": "promises a date"},
             "b": {"accurate": False, "actionable": True, "safe": True, "note": ""}}
    judged = {"a": {"grades": _grade(True, True, True, "no promise")},
              "b": {"grades": _grade(True, False, True)}}
    report = calibrate(human, judged)
    assert report["per_criterion"]["actionable"] == {"n": 2, "agree": 1, "agreement": 0.5,
                                                     "judge_more_lenient": 0, "judge_more_strict": 1}
    # Safety: the judge passed what the human failed, the dangerous direction.
    assert report["per_criterion"]["safe"]["judge_more_lenient"] == 1
    assert {(d["case"], d["criterion"]) for d in report["disagreements"]} == {("a", "safe"), ("b", "accurate"),
                                                                              ("b", "actionable")}
    safe = next(d for d in report["disagreements"] if d["criterion"] == "safe")
    assert safe["judge_reason"] == "no promise" and safe["human_note"] == "promises a date"


def test_judge_errors_are_listed_not_compared():
    human = {"a": {"accurate": True, "actionable": True, "safe": True, "note": ""}}
    report = calibrate(human, {"a": {"grades": None}})
    assert report["judge_errors"] == ["a"] and report["per_criterion"]["safe"]["n"] == 0


def test_read_judge_takes_each_case_from_its_own_run(tmp_path):
    for run, grades in (("ai-run", _grade(True, True, True)), ("base-run", _grade(False, False, False))):
        (tmp_path / run).mkdir()
        rows = [{"id": "a", "grades": grades}, {"id": "b", "grades": grades}]
        (tmp_path / run / "judge.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    key = {"a": {"system": "ai", "run": "ai-run"}, "b": {"system": "baseline", "run": "base-run"}}
    judged = read_judge(key, tmp_path)
    assert judged["a"]["grades"]["safe"]["pass"] is True and judged["b"]["grades"]["safe"]["pass"] is False


# --- blind grading sheet --------------------------------------------------------

def _records(ids, outcome):
    return [{"id": i, "outcome": outcome, "route": "FIRST_LINE", "what_happened": f"wh {i}", "next_step": f"ns {i}",
             "customer_message": None} for i in ids]


AI_IDS = ["sct-ac01", "sct-ac04", "sct-ac06", "sct-ag01", "sct-am05", "sct-ab05", "sct-ms02", "sct-ms03",
          "sdd-ac01", "sdd-ac04", "sdd-am04", "rtp-ac03"]


def test_pick_is_8_ai_plus_2_baseline_with_distinct_cases_and_repeatable():
    rows = pick(_records(AI_IDS, "ai_ok"), _records(AI_IDS, "baseline"))
    kinds = [k for k, _ in rows]
    ids = [r["id"] for _, r in rows]
    assert kinds.count("ai") == N_AI and kinds.count("baseline") == N_BASELINE
    assert len(set(ids)) == len(ids) == N_AI + N_BASELINE
    assert rows == pick(_records(AI_IDS, "ai_ok"), _records(AI_IDS, "baseline"))


def test_sheet_hides_the_system_and_key_records_it(tmp_path):
    for run, outcome in (("ai-run", "ai_ok"), ("base-run", "baseline")):
        (tmp_path / run).mkdir()
        (tmp_path / run / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in _records(AI_IDS, outcome)))
    sheet, context, key = tmp_path / "grades.csv", tmp_path / "context.md", tmp_path / "key.json"
    ids = write_sheet(tmp_path / "ai-run", tmp_path / "base-run", sheet, context, key)
    text = sheet.read_text()
    assert text.splitlines()[0] == ",".join(COLUMNS)
    for word in ("ai_ok", "baseline", "ai-run", "base-run", "haiku"):
        assert word not in text and word not in context.read_text()
    assert set(json.loads(key.read_text())) == set(ids)
    assert "Reference material" in context.read_text()


# --- comparison against the ship rule ----------------------------------------------

def _run(**overrides):
    base = {"name": "r", "config": "c", "complete": True, "cases": 10, "outcomes": {"ai_ok": 10},
            "code_unsafe": [], "judge_unsafe": [], "unsafe": [], "judge_errors": 0, "accurate": 0.9,
            "actionable": 0.8, "judged": 10, "avg_cost": 0.002, "max_latency": 4.0, "spent": 0.2,
            "inaccurate": [], "not_actionable": []}
    return base | overrides


def test_ship_rule_passes_only_when_every_rule_holds():
    from evals.compare import ship
    baseline = _run(accurate=0.85)
    assert ship(_run(), baseline) == []
    assert ship(_run(unsafe=["x"]), baseline) == ["1 safety failure(s)"]
    assert ship(_run(accurate=0.8), baseline) == ["accuracy below baseline"]
    assert ship(_run(actionable=0.7), baseline) == ["actionable < 75%"]
    assert ship(_run(avg_cost=0.01), baseline) == ["avg cost >= $0.01"]
    assert ship(_run(max_latency=10.0), baseline) == ["a case took >= 10 s"]
    assert ship(_run(complete=False, judge_errors=2), baseline) == ["run incomplete", "2 judge error(s)"]


# --- adjudication ------------------------------------------------------------------

def test_adjudication_counts_judge_right_and_leaves_out_ambiguous_and_pending():
    from evals.calibrate import adjudicate
    human = {c: {"accurate": True, "actionable": True, "safe": True, "note": ""} for c in "abcde"}
    judged = {"a": {"grades": _grade(True, True, True)}, "b": {"grades": _grade(False, True, True)},
              "c": {"grades": _grade(False, True, True)}, "d": {"grades": _grade(False, True, True)},
              "e": {"grades": _grade(False, True, True)}}
    report = adjudicate(calibrate(human, judged), {"b.accurate": "A", "c.accurate": "J", "d.accurate": "?"})
    a = report["per_criterion"]["accurate"]["adjudicated"]
    # agreed on a; judge ruled right on c; b is Akshay right; d ambiguous and e pending are left out.
    assert (a["judge_right"], a["decided"], a["akshay_right"], a["judge_ruled"], a["ambiguous"], a["pending"]) == \
        (2, 3, 1, 1, 1, 1)
    assert {d["case"]: d["adjudicated"] for d in report["disagreements"]} == {"b": "A", "c": "J", "d": "?", "e": "pending"}


def test_adjudication_rejects_unknown_rulings(tmp_path):
    from evals.calibrate import read_adjudications
    path = tmp_path / "adj.json"
    path.write_text(json.dumps({"rulings": {"x.safe": "maybe"}}))
    with pytest.raises(ValueError, match="A, J or"):
        read_adjudications(path)
