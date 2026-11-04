import json
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

import src.extract as llm
import src.report as report
from tests.test_graph import EXPECTED, stand_in_llm

ROOT = Path(__file__).resolve().parent.parent
BY_SUPPLIER = {vals["supplier_name"]: pack for pack, vals in EXPECTED.items()}


def any_pack_llm(text: str):
    """Stand-in for extract_fields() that works for every sample pack."""
    return stand_in_llm(BY_SUPPLIER[text.splitlines()[0].strip()])(text)


@pytest.fixture
def offline(monkeypatch, tmp_path):
    """No Gemini, and nothing written to the real outputs/ folder."""
    monkeypatch.setattr(llm, "extract_fields", any_pack_llm)
    real_save = report.save_report
    monkeypatch.setattr(report, "save_report",
                        lambda rep, out_dir=None: real_save(rep, out_dir or tmp_path / "reports"))
    return tmp_path


# --- run_eval.py ----------------------------------------------------------

def test_eval_scores_all_ten(offline):
    from run_eval import all_packs, evaluate

    summary = evaluate(all_packs(), out_dir=offline)
    assert (summary["correct"], summary["total"]) == (10, 10)
    assert json.loads((offline / "eval_summary.json").read_text())["correct"] == 10
    assert len(list((offline / "reports").glob("*.json"))) == 10


def test_eval_cli_chosen_packs(offline, monkeypatch, capsys):
    import run_eval

    monkeypatch.setattr(run_eval, "OUT", offline)
    monkeypatch.setattr(run_eval, "SUMMARY", offline / "eval_summary.json")
    real = run_eval.evaluate
    monkeypatch.setattr(run_eval, "evaluate", lambda packs, delay, progress: real(packs, delay, progress, offline))
    assert run_eval.main(["--packs", "03,09"]) == 0
    assert "Score: 2/2 correct" in capsys.readouterr().out


# --- app.py ---------------------------------------------------------------

def app() -> AppTest:
    return AppTest.from_file(str(ROOT / "app.py"), default_timeout=30).run()


def check(at: AppTest, pack: str) -> AppTest:
    at.selectbox[0].select(pack).run()
    return [b for b in at.button if b.label == "Check quotation"][0].click().run()


def page(at: AppTest) -> str:
    return " ".join(m.value for m in at.markdown)


def test_app_loads(offline):
    at = app()
    assert not at.exception
    assert [t.label for t in at.tabs] == ["Check a quotation", "All 10 sample packs", "How it works"]


def test_app_shows_reject_with_quote(offline):
    at = check(app(), "supplier-pack-03")
    assert not at.exception
    assert "Reject" in page(at) and "229.00" in page(at)


def test_app_review_needs_a_choice_then_records_person(offline):
    at = check(app(), "supplier-pack-04")
    save = lambda: [b for b in at.button if b.label == "Save decision"][0]
    save().click().run()
    assert [w.value for w in at.warning] == ["Choose a decision before saving."]

    [r for r in at.radio if r.label == "Your decision"][0].set_value("Reject")
    save().click().run()
    assert not at.exception
    assert "Decided by a person" in page(at) and "Needs a person to check" in page(at)