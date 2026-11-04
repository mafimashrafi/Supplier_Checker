import json
from pathlib import Path

import pytest

from src.rules import APPROVE, NEEDS, REJECT, decide, load_purchase_request
from src.schema import SupplierDoc
from src.verify import Issue, check_math

HERE = Path(__file__).parent
EXPECTED = json.loads((HERE / "expected_extraction.json").read_text())["packs"]
VERDICTS = json.loads((HERE / "expected_verdicts.json").read_text())["verdicts"]
PR = load_purchase_request(HERE.parent / "data" / "purchase-request.csv")


def doc(pack="supplier-pack-01", **changes) -> SupplierDoc:
    values = {**EXPECTED[pack], **changes}
    return SupplierDoc.model_validate({f: {"value": v, "quote": None} for f, v in values.items()})


def verdict(**changes) -> str:
    return decide(doc(**changes), PR, []).verdict


# --- the 10 sample packs --------------------------------------------------

@pytest.mark.parametrize("pack", sorted(VERDICTS))
def test_sample_pack_verdict(pack):
    d = doc(pack)
    assert decide(d, PR, check_math(d)).verdict == VERDICTS[pack]


def test_purchase_request_loads():
    assert PR["A"].max_price == 480 and PR["D"].quantity == 50000


# --- boundaries (company-rules.md) ----------------------------------------

@pytest.mark.parametrize("price,expected", [
    (480, APPROVE),  # at the maximum
    (494.40, NEEDS),  # exactly 3% above
    (494.41, REJECT),  # just over 3%
])
def test_price(price, expected):
    assert verdict(unit_price=price) == expected


@pytest.mark.parametrize("advance,expected", [(0, APPROVE), (20, APPROVE), (20.5, REJECT), (None, NEEDS)])
def test_advance(advance, expected):
    assert verdict(advance_pct=advance) == expected


@pytest.mark.parametrize("value,unit,expected", [
    (30, "days", APPROVE), (31, "days", NEEDS), (45, "days", NEEDS), (46, "days", REJECT),
    (4, "weeks", APPROVE), (7, "weeks", REJECT), (2, "months", NEEDS), (None, None, NEEDS),
])
def test_delivery(value, unit, expected):
    assert verdict(delivery_value=value, delivery_unit=unit) == expected


@pytest.mark.parametrize("qty,expected", [(12000, APPROVE), (12600, APPROVE), (12601, NEEDS),
                                          (11400, APPROVE), (11399, NEEDS)])
def test_quantity(qty, expected):
    assert verdict(quantity=qty) == expected


@pytest.mark.parametrize("lo,hi,start,expected", [
    (30, 30, "delivery", APPROVE), (60, 60, "delivery", APPROVE),
    (29, 29, "delivery", NEEDS), (61, 61, "delivery", NEEDS),
    (30, 45, "delivery", NEEDS),  # a range is unclear
    (45, 45, "PO", NEEDS),  # not counted from delivery
    (45, 45, None, NEEDS), (None, None, "delivery", NEEDS),
])
def test_payment(lo, hi, start, expected):
    assert verdict(payment_days_min=lo, payment_days_max=hi, payment_counted_from=start) == expected


@pytest.mark.parametrize("days,expected", [(30, APPROVE), (29, NEEDS), (None, NEEDS)])
def test_validity(days, expected):
    assert verdict(validity_days=days) == expected


@pytest.mark.parametrize("pct,expected", [(0.5, APPROVE), (0.4, NEEDS), (None, REJECT)])
def test_penalty(pct, expected):
    assert verdict(penalty_pct_per_week=pct) == expected


@pytest.mark.parametrize("rate,amount,expected", [(15, 849600, APPROVE), (10, 849600, NEEDS), (None, None, NEEDS)])
def test_vat(rate, amount, expected):
    assert verdict(vat_rate_pct=rate, vat_amount=amount) == expected


@pytest.mark.parametrize("tin,bin_,expected", [("1", "2", APPROVE), (None, "2", REJECT), ("1", None, REJECT)])
def test_registration(tin, bin_, expected):
    assert verdict(tin=tin, bin=bin_) == expected


def test_unknown_item_needs_person():
    assert verdict(item_code="Z") == NEEDS


# --- precedence and safety ------------------------------------------------

def test_reject_beats_needs():
    assert verdict(unit_price=600, quantity=1000) == REJECT


def test_math_issue_needs_person():
    issue = Issue("math", "line_amount", "wrong")
    assert decide(doc(), PR, [issue]).verdict == NEEDS


def test_unverified_value_cannot_cause_reject():
    """Price 9% over would Reject, but if its quote failed verification a person decides."""
    issue = Issue("evidence", "unit_price", "Quote is not in the document.")
    d = decide(doc("supplier-pack-03"), PR, [issue])
    assert d.verdict == NEEDS
    assert any("could not be confirmed" in f.reason for f in d.findings)


def test_every_finding_names_its_rule():
    d = decide(doc("supplier-pack-09"), PR, check_math(doc("supplier-pack-09")))
    assert {f.rule for f in d.findings} == {"Needs 3", "Needs 6"}
