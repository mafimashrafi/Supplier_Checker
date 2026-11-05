"""Tests for src/graph.py and src/report.py (offline, no API calls).

The LLM step is replaced by a stand-in that returns the answer-key values,
each with a quote copied from a real line of the PDF. Everything else
(ingest, verify, rules, human review, report) runs for real.
"""

import json
from pathlib import Path

import pytest

import src.extract as llm
import src.graph as graph
from src.graph import run_pack
from src.report import checklist, save_report, to_text
from src.rules import APPROVE, NEEDS, REJECT
from src.schema import SupplierDoc
from src.verify import _as_text

HERE = Path(__file__).parent
DATA = HERE.parent / "data"
EXPECTED = json.loads((HERE / "expected_extraction.json").read_text())["packs"]
VERDICTS = json.loads((HERE / "expected_verdicts.json").read_text())["verdicts"]


def stand_in_llm(pack: str):
    """An extract_fields() that returns the answer key with real quotes."""
    def extract_fields(text: str) -> SupplierDoc:
        lines = text.splitlines()
        data = {}
        for field, value in EXPECTED[pack].items():
            quote = None
            if value == 0:
                quote = next(line for line in lines if "No advance" in line)
            elif value is not None:
                needle = _as_text(value).lower()
                quote = next(line for line in lines if needle in line.replace(",", "").lower())
            data[field] = {"value": value, "quote": quote}
        return SupplierDoc.model_validate(data)
    return extract_fields


def run(monkeypatch, pack: str, reviewer=None) -> dict:
    monkeypatch.setattr(llm, "extract_fields", stand_in_llm(pack))
    return run_pack(str(DATA / f"{pack}.pdf"), reviewer=reviewer)


def never_called(question):
    raise AssertionError("the reviewer should not have been asked")


# --- the full pipeline on the 10 sample packs ------------------------------

@pytest.mark.parametrize("pack", sorted(VERDICTS))
def test_pipeline_verdict(monkeypatch, pack):
    rep = run(monkeypatch, pack)
    assert rep["system_verdict"] == VERDICTS[pack]
    assert rep["final_verdict"] == VERDICTS[pack]
    assert rep["decided_by"] == "system"


@pytest.mark.parametrize("pack", ["supplier-pack-01", "supplier-pack-03"])
def test_sure_answers_never_ask_a_person(monkeypatch, pack):
    rep = run(monkeypatch, pack, reviewer=never_called)
    assert rep["final_verdict"] in (APPROVE, REJECT)


# --- human review -----------------------------------------------------------

def test_unsure_pack_pauses_and_person_decides(monkeypatch):
    asked = []

    def reviewer(question):
        asked.append(question)
        return {"verdict": APPROVE, "note": "2% over is acceptable", "reviewer": "test"}

    rep = run(monkeypatch, "supplier-pack-04", reviewer=reviewer)
    assert len(asked) == 1 and asked[0]["findings"][0]["rule"] == "Needs 1"
    assert rep["system_verdict"] == NEEDS        # the system's own answer is kept for scoring
    assert rep["final_verdict"] == APPROVE
    assert rep["decided_by"] == "person"


def test_reviewer_must_give_a_real_verdict(monkeypatch):
    with pytest.raises(ValueError):
        run(monkeypatch, "supplier-pack-04", reviewer=lambda q: {"verdict": "Maybe"})


# --- mistakes are handled, not crashed on -----------------------------------

def test_llm_failure_goes_to_a_person(monkeypatch):
    def broken(text):
        raise RuntimeError("503 UNAVAILABLE")

    monkeypatch.setattr(llm, "extract_fields", broken)
    rep = run_pack(str(DATA / "supplier-pack-01.pdf"))
    assert rep["system_verdict"] == NEEDS
    assert rep["reasons"][0]["rule"] == "System" and "503" in rep["reasons"][0]["reason"]


def test_unreadable_pdf_goes_to_a_person(monkeypatch):
    monkeypatch.setattr(graph, "extract_text", lambda path: "")
    monkeypatch.setattr(llm, "extract_fields", never_called)  # must not reach the LLM
    rep = run_pack(str(DATA / "supplier-pack-01.pdf"))
    assert rep["system_verdict"] == NEEDS
    assert "no readable text" in rep["reasons"][0]["reason"]


def test_missing_file_goes_to_a_person(monkeypatch):
    monkeypatch.setattr(llm, "extract_fields", never_called)
    rep = run_pack(str(DATA / "does-not-exist.pdf"))
    assert rep["system_verdict"] == NEEDS and rep["reasons"][0]["rule"] == "System"


def test_failure_can_still_be_reviewed(monkeypatch):
    monkeypatch.setattr(graph, "extract_text", lambda path: "")
    rep = run_pack(str(DATA / "supplier-pack-01.pdf"),
                   reviewer=lambda q: {"verdict": REJECT, "note": "unreadable", "reviewer": "test"})
    assert rep["final_verdict"] == REJECT and rep["system_verdict"] == NEEDS


# --- report -----------------------------------------------------------------

def test_report_text_and_save(monkeypatch, tmp_path):
    rep = run(monkeypatch, "supplier-pack-09")
    text = to_text(rep)
    assert "Dhaleshwari Poly Pack" in text and "[Needs 6]" in text and "322,000.00" in text
    path = save_report(rep, tmp_path)
    assert json.loads(path.read_text())["system_verdict"] == NEEDS


def test_approve_report_says_rules_passed(monkeypatch):
    assert "All company rules passed." in to_text(run(monkeypatch, "supplier-pack-01"))


# --- checklist (the rule table in the app) ------------------------------------

def statuses(rep: dict) -> dict:
    return {row["label"]: row["status"] for row in checklist(rep)}


def test_checklist_all_passed_with_quotes(monkeypatch):
    rows = checklist(run(monkeypatch, "supplier-pack-01"))
    assert {r["status"] for r in rows} == {"Passed"}
    assert all(r["quote"] for r in rows if r["label"] != "Every quote found in the document")


def test_checklist_marks_reject_as_failed(monkeypatch):
    s = statuses(run(monkeypatch, "supplier-pack-03"))
    assert s["Unit price within the maximum"] == "Failed"
    assert [k for k, v in s.items() if v != "Passed"] == ["Unit price within the maximum"]


def test_checklist_marks_needs_as_unsure_with_reason(monkeypatch):
    rows = checklist(run(monkeypatch, "supplier-pack-09"))
    unsure = {r["label"]: r for r in rows if r["status"] == "Unsure"}
    assert set(unsure) == {"Payment 30 to 60 days after delivery", "The numbers add up"}
    assert "322,000.00" in unsure["The numbers add up"]["reason"]


def test_checklist_when_document_unreadable(monkeypatch):
    monkeypatch.setattr(graph, "extract_text", lambda path: "")
    rows = checklist(run_pack(str(DATA / "supplier-pack-01.pdf")))
    assert len(rows) == 1 and rows[0]["status"] == "Unsure"