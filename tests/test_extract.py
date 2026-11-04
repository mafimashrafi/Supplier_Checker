import json
from functools import cache
from pathlib import Path

import pytest
from pydantic import ValidationError

from src.extract import SYSTEM_PROMPT
from src.ingest import extract_text
from src.schema import SupplierDoc

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
EXPECTED = json.loads((Path(__file__).parent / "expected_extraction.json").read_text())["packs"]
PACKS = sorted(EXPECTED)
FIELDS = list(EXPECTED[PACKS[0]])

# Fields compared without caring about upper/lower case.
CASE_INSENSITIVE = {"payment_counted_from", "delivery_unit"}


def pdf_text(pack: str) -> str:
    return extract_text(str(DATA / f"{pack}.pdf"))


def squash(s: str) -> str:
    """Collapse all whitespace, so a quote that spans a line break still matches."""
    return " ".join(s.split())


def as_printed(n: float) -> str:
    """5664000.0 -> '5664000', 6.4 -> '6.4' (to search in comma-free text)."""
    return str(int(n)) if float(n).is_integer() else repr(float(n))


def doc_from_expected(pack: str) -> SupplierDoc:
    """Build a SupplierDoc holding the expected values (quotes left empty)."""
    return SupplierDoc.model_validate(
        {f: {"value": v, "quote": None} for f, v in EXPECTED[pack].items()}
    )


# ---------------------------------------------------------------------------
# Offline: the answer key itself
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pack", PACKS)
def test_answer_key_values_appear_in_pdf(pack):
    """Every non-null expected value must be visible in the PDF text."""
    text = pdf_text(pack).replace(",", "")
    for field, value in EXPECTED[pack].items():
        if value is None:
            continue
        if field == "advance_pct" and value == 0:
            assert "No advance" in text, f"{pack}: advance 0 but no 'No advance' text"
        elif isinstance(value, (int, float)):
            assert as_printed(value) in text, f"{pack}.{field}={value} not in PDF"
        else:
            assert str(value) in text, f"{pack}.{field}={value!r} not in PDF"


def test_answer_key_nulls_are_really_missing():
    """The expected nulls must match text that is really absent from the PDF."""
    assert "TIN" not in pdf_text("supplier-pack-08")
    assert "penalty" not in pdf_text("supplier-pack-06").lower()
    pack10 = pdf_text("supplier-pack-10")
    assert "Subtotal" not in pack10 and "VAT 15%" not in pack10
    assert "delivery" not in pdf_text("supplier-pack-09").split("1. Payment.")[1].split("2. Delivery.")[0]


# ---------------------------------------------------------------------------
# Offline: the schema and prompt
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("pack", PACKS)
def test_schema_can_hold_every_expected_answer(pack):
    doc_from_expected(pack)


def test_schema_fields_match_answer_key():
    assert set(SupplierDoc.model_fields) - {"extraction_notes"} == set(FIELDS)


def test_schema_rejects_number_with_commas():
    data = doc_from_expected("supplier-pack-01").model_dump()
    data["quantity"]["value"] = "12,000"
    with pytest.raises(ValidationError):
        SupplierDoc.model_validate(data)


def test_schema_rejects_missing_field():
    data = doc_from_expected("supplier-pack-01").model_dump()
    del data["tin"]
    with pytest.raises(ValidationError):
        SupplierDoc.model_validate(data)


def test_prompt_contains_no_company_rules():
    """The LLM must never see the rules or be asked for a verdict."""
    for word in ["Approve", "Reject", "Needs a person", "maximum unit price", "purchase request"]:
        assert word.lower() not in SYSTEM_PROMPT.lower(), f"prompt mentions {word!r}"


def test_prompt_explains_every_field():
    """Gemini never sees Field descriptions, so the prompt must name every field."""
    missing = [f for f in SupplierDoc.model_fields if f not in SYSTEM_PROMPT]
    assert not missing, f"fields not explained in SYSTEM_PROMPT: {missing}"


def test_save_json_round_trip(tmp_path):
    from src.extract import save_json

    doc = doc_from_expected("supplier-pack-09")
    path = save_json(doc, "data/supplier-pack-09.pdf", out_dir=str(tmp_path))
    assert path.name == "supplier-pack-09.json"
    assert SupplierDoc.model_validate_json(path.read_text()) == doc


# ---------------------------------------------------------------------------
# Live: Gemini output vs the answer key (run with -m live)
# ---------------------------------------------------------------------------

@cache
def live_extract(pack: str) -> SupplierDoc:
    """One Gemini call per pack, reused by every live test for that pack."""
    from src.extract import extract_fields

    return extract_fields(pdf_text(pack))


@pytest.mark.live
@pytest.mark.parametrize("pack,field", [(p, f) for p in PACKS for f in FIELDS])
def test_live_value_matches_answer_key(pack, field):
    got = getattr(live_extract(pack), field).value
    want = EXPECTED[pack][field]
    if want is None:
        assert got is None, f"expected null, got {got!r}"
    elif isinstance(want, (int, float)):
        assert got == pytest.approx(want), f"expected {want}, got {got!r}"
    elif field in CASE_INSENSITIVE:
        assert got is not None and got.strip().lower() == want.lower()
    else:
        assert got == want


@pytest.mark.live
@pytest.mark.parametrize("pack", PACKS)
def test_live_quotes_are_copied_from_pdf(pack):
    """Every quote the model gives must really be in the PDF (ignoring line breaks)."""
    text = squash(pdf_text(pack))
    doc = live_extract(pack)
    bad = [
        f"{f}: {getattr(doc, f).quote!r}"
        for f in FIELDS
        if getattr(doc, f).quote and squash(getattr(doc, f).quote) not in text
    ]
    assert not bad, "quotes not found in PDF:\n" + "\n".join(bad)


@pytest.mark.live
def test_live_pack_05_repeated_sentence_is_noted():
    assert live_extract("supplier-pack-05").extraction_notes, "repeated advance sentence not noted"


@pytest.mark.live
def test_live_pack_08_missing_tin_has_evidence_quote():
    assert "available on request" in (live_extract("supplier-pack-08").tin.quote or "")
