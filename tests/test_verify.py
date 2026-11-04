import json
from pathlib import Path

import pytest

from src.ingest import extract_text
from src.schema import SupplierDoc
from src.verify import check_evidence, check_math

ROOT = Path(__file__).resolve().parent.parent
EXPECTED = json.loads((Path(__file__).parent / "expected_extraction.json").read_text())["packs"]


def doc(pack: str, **quotes) -> SupplierDoc:
    """Answer-key values for a pack; quotes None unless given."""
    return SupplierDoc.model_validate(
        {f: {"value": v, "quote": quotes.get(f)} for f, v in EXPECTED[pack].items()}
    )


def text(pack: str) -> str:
    return extract_text(str(ROOT / "data" / f"{pack}.pdf"))


# --- arithmetic -----------------------------------------------------------

@pytest.mark.parametrize("pack", sorted(EXPECTED))
def test_math_only_pack_09_is_wrong(pack):
    issues = check_math(doc(pack))
    if pack == "supplier-pack-09":
        assert [i.field for i in issues] == ["line_amount"]
        assert "320,000.00" in issues[0].message
    else:
        assert issues == []


def test_math_catches_wrong_vat_and_total():
    d = doc("supplier-pack-01")
    d.vat_amount.value = 800000
    fields = {i.field for i in check_math(d)}
    assert {"vat_amount", "total"} <= fields


def test_math_missing_total_cannot_be_checked():
    d = doc("supplier-pack-01")
    d.total.value = None
    assert any("Cannot check the total" in i.message for i in check_math(d))


# --- evidence -------------------------------------------------------------

def test_correct_quotes_pass():
    d = SupplierDoc.model_validate({f: {"value": None, "quote": None} for f in EXPECTED["supplier-pack-01"]})
    d.unit_price.value, d.unit_price.quote = 472.0, "472.00"
    d.supplier_name.value = d.supplier_name.quote = "Padma Textile Mills Ltd"
    assert check_evidence(d, text("supplier-pack-01")) == []


def test_value_without_quote_is_flagged():
    issues = check_evidence(doc("supplier-pack-01"), text("supplier-pack-01"))
    assert any(i.field == "unit_price" and "no supporting quote" in i.message for i in issues)


def test_invented_quote_is_flagged():
    d = doc("supplier-pack-01", unit_price="Unit price 450.00")
    issues = check_evidence(d, text("supplier-pack-01"))
    assert any(i.field == "unit_price" and "not in the document" in i.message for i in issues)


def test_value_not_in_its_quote_is_flagged():
    d = doc("supplier-pack-01", unit_price="472.00")
    d.unit_price.value = 480
    issues = check_evidence(d, text("supplier-pack-01"))
    assert any(i.field == "unit_price" and "does not appear" in i.message for i in issues)


def test_quote_across_line_break_passes():
    d = doc("supplier-pack-01", payment_days_min=(
        "Balance payable within 45 days after delivery and acceptance of goods."))
    issues = check_evidence(d, text("supplier-pack-01"))
    assert not any(i.field == "payment_days_min" for i in issues)


def test_null_with_explaining_quote_passes():
    d = doc("supplier-pack-08", tin="Supplier registration details available on request.")
    issues = check_evidence(d, text("supplier-pack-08"))
    assert not any(i.field == "tin" for i in issues)
