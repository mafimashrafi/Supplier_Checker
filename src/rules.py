import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from src.schema import SupplierDoc
from src.verify import D, Issue

APPROVE = "Approve"
REJECT = "Reject"
NEEDS = "Needs a person to check"

# --- thresholds, exactly as written in company-rules.md ---
PRICE_OVER_MAX_REJECT_PCT = Decimal("3")  # Reject 1 / Needs 1
ADVANCE_MAX_PCT = Decimal("20")  # Reject 2
DELIVERY_REJECT_AFTER_DAYS = 45  # Reject 5
DELIVERY_PERSON_FROM_DAYS = 31  # Needs 4
QTY_TOLERANCE_PCT = Decimal("5")  # Needs 2
PAYMENT_MIN_DAYS, PAYMENT_MAX_DAYS = 30, 60  # Needs 3
VAT_RATE_PCT = Decimal("15")  # Needs 5
MIN_VALIDITY_DAYS = 30  # Needs 7
MIN_PENALTY_PCT = Decimal("0.5")  # Other notes


@dataclass(frozen=True)
class Finding:
    rule: str  # e.g. "Reject 1", "Needs 6", "Evidence"
    level: str  # REJECT or NEEDS
    reason: str
    quote: str | None = None
    fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class PRItem:
    item: str
    description: str
    unit: str
    quantity: Decimal
    max_price: Decimal


@dataclass(frozen=True)
class Decision:
    verdict: str
    findings: list[Finding]


def load_purchase_request(path: str | Path = "data/purchase-request.csv") -> dict[str, PRItem]:
    # utf-8-sig: the CSV starts with a byte-order mark that would break the first column name.
    with open(path, encoding="utf-8-sig", newline="") as f:
        return {
            row["Item"].strip(): PRItem(
                item=row["Item"].strip(),
                description=row["Description"],
                unit=row["Unit"],
                quantity=Decimal(row["Quantity requested"]),
                max_price=Decimal(row["Maximum unit price (BDT)"]),
            )
            for row in csv.DictReader(f)
        }


def _num(n: Decimal, commas: bool = False) -> str:
    """Plain number for messages: 40 not 4E+1, 229 not 229.0, 6.65 stays 6.65."""
    return format(n.normalize(), ",f" if commas else "f")


def _pct(n: Decimal) -> str:
    return f"{n.quantize(Decimal('0.01'))}%"


# ---------------------------------------------------------------------------
# One function per rule. Each returns a list of Findings (empty = rule passed).
# ---------------------------------------------------------------------------

def check_price(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    q = doc.unit_price.quote
    if pr is None:
        return [Finding("Purchase request", NEEDS,
                        f"Item {doc.item_code.value!r} is not in the purchase request.",
                        doc.item_code.quote, ("item_code",))]
    if doc.unit_price.value is None:
        return [Finding("Reject 1", NEEDS, "Unit price not found, so it cannot be checked.", None, ("unit_price",))]
    price = D(doc.unit_price.value)
    over = (price - pr.max_price) / pr.max_price * 100
    if over > PRICE_OVER_MAX_REJECT_PCT:
        return [Finding("Reject 1", REJECT,
                        f"Unit price {_num(price)} is {_pct(over)} above the maximum {pr.max_price} (limit 3%).",
                        q, ("unit_price",))]
    if over > 0:
        return [Finding("Needs 1", NEEDS,
                        f"Unit price {_num(price)} is {_pct(over)} above the maximum {pr.max_price} (within 3%).",
                        q, ("unit_price",))]
    return []


def check_advance(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    v = doc.advance_pct.value
    if v is None:
        return [
            Finding("Reject 2", NEEDS, "Advance payment not stated, so it cannot be checked.", None, ("advance_pct",))]
    if D(v) > ADVANCE_MAX_PCT:
        return [Finding("Reject 2", REJECT, f"Advance payment is {_num(D(v))}% (limit 20%).",
                        doc.advance_pct.quote, ("advance_pct",))]
    return []


def check_penalty(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    v = doc.penalty_pct_per_week.value
    if v is None:
        return [Finding("Reject 3", REJECT, "The contract has no late-delivery penalty clause.",
                        doc.penalty_pct_per_week.quote, ("penalty_pct_per_week",))]
    if D(v) < MIN_PENALTY_PCT:
        # The rules say "must be at least 0.5%" but not what happens below it.
        # Our interpretation: not sure -> a person decides.
        return [Finding("Penalty note", NEEDS,
                        f"Late-delivery penalty is {_num(D(v))}% per week (must be at least 0.5%).",
                        doc.penalty_pct_per_week.quote, ("penalty_pct_per_week",))]
    return []


def check_registration(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    missing = [n.upper() for n in ("tin", "bin") if getattr(doc, n).value is None]
    if missing:
        quote = doc.tin.quote or doc.bin.quote
        return [Finding("Reject 4", REJECT, f"Supplier {' and '.join(missing)} missing.", quote, ("tin", "bin"))]
    return []


def delivery_days(doc: SupplierDoc) -> int | None:
    v, unit = doc.delivery_value.value, (doc.delivery_unit.value or "").strip().lower()
    if v is None:
        return None
    if unit in ("day", "days"):
        return int(v)
    if unit in ("week", "weeks"):
        return int(v * 7)
    return None


def check_delivery(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    days, q = delivery_days(doc), doc.delivery_value.quote
    if days is None:
        return [Finding("Reject 5", NEEDS, "Delivery time not found or in an unknown unit.", q,
                        ("delivery_value", "delivery_unit"))]
    if days > DELIVERY_REJECT_AFTER_DAYS:
        return [
            Finding("Reject 5", REJECT, f"Delivery in {days} days (limit 45).", q, ("delivery_value", "delivery_unit"))]
    if days >= DELIVERY_PERSON_FROM_DAYS:
        return [Finding("Needs 4", NEEDS, f"Delivery in {days} days (31 to 45 needs a person).", q,
                        ("delivery_value", "delivery_unit"))]
    return []


def check_quantity(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    if pr is None:
        return []  # already reported by check_price
    if doc.quantity.value is None:
        return [Finding("Needs 2", NEEDS, "Quantity not found.", None, ("quantity",))]
    qty = D(doc.quantity.value)
    diff = abs(qty - pr.quantity) / pr.quantity * 100
    if diff > QTY_TOLERANCE_PCT:
        return [Finding("Needs 2", NEEDS,
                        f"Quantity {_num(qty, commas=True)} differs from the {pr.quantity:,} requested by {_pct(diff)} (limit 5%).",
                        doc.quantity.quote, ("quantity",))]
    return []


def check_payment(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    lo, hi = doc.payment_days_min.value, doc.payment_days_max.value
    start = (doc.payment_counted_from.value or "").strip().lower()
    q = doc.payment_days_min.quote or doc.payment_counted_from.quote
    fields = ("payment_days_min", "payment_days_max", "payment_counted_from")
    problems = []
    if lo is None or hi is None:
        problems.append("payment days are not stated")
    else:
        if lo != hi:
            problems.append(f"payment is a range ({lo:g} to {hi:g} days), so the actual term is unclear")
        if lo < PAYMENT_MIN_DAYS or hi > PAYMENT_MAX_DAYS:
            problems.append("payment is outside 30 to 60 days")
    if start != "delivery":
        problems.append("payment days are not counted from delivery")
    if problems:
        return [Finding("Needs 3", NEEDS, "Payment terms: " + "; ".join(problems) + ".", q, fields)]
    return []


def check_vat(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    rate, amount = doc.vat_rate_pct.value, doc.vat_amount.value
    if rate is None or amount is None:
        return [Finding("Needs 5", NEEDS, "VAT is not shown separately.", doc.vat_rate_pct.quote,
                        ("vat_rate_pct", "vat_amount"))]
    if D(rate) != VAT_RATE_PCT:
        return [Finding("Needs 5", NEEDS, f"VAT is {_num(D(rate))}%, not 15%.", doc.vat_rate_pct.quote,
                        ("vat_rate_pct",))]
    return []


def check_validity(doc: SupplierDoc, pr: PRItem | None) -> list[Finding]:
    v = doc.validity_days.value
    if v is None:
        return [Finding("Needs 7", NEEDS, "Quotation validity not found.", None, ("validity_days",))]
    if v < MIN_VALIDITY_DAYS:
        return [Finding("Needs 7", NEEDS, f"Quotation is valid for {v:g} days (minimum 30).",
                        doc.validity_days.quote, ("validity_days",))]
    return []


RULES = [check_price, check_advance, check_penalty, check_registration, check_delivery,
         check_quantity, check_payment, check_vat, check_validity]


def _from_issue(issue: Issue) -> Finding:
    if issue.kind == "math":
        return Finding("Needs 6", NEEDS, issue.message, issue.quote, (issue.field,))
    return Finding("Evidence", NEEDS, f"{issue.field}: {issue.message}", issue.quote, (issue.field,))


def decide(doc: SupplierDoc, pr_items: dict[str, PRItem], issues: list[Issue]) -> Decision:
    """Apply every rule. Reject beats Needs a person, which beats Approve."""
    pr = pr_items.get((doc.item_code.value or "").strip().upper())
    findings = [f for rule in RULES for f in rule(doc, pr)]

    # Never reject on a value we could not confirm in the document: send it to a person instead.
    unverified = {i.field for i in issues if i.kind == "evidence"}
    findings = [
        Finding(f.rule, NEEDS, f.reason + " (value could not be confirmed in the document)", f.quote, f.fields)
        if f.level == REJECT and unverified & set(f.fields) else f
        for f in findings
    ]
    findings += [_from_issue(i) for i in issues]

    if any(f.level == REJECT for f in findings):
        verdict = REJECT
    elif findings:
        verdict = NEEDS
    else:
        verdict = APPROVE
    findings.sort(key=lambda f: f.level != REJECT)  # Reject reasons first
    return Decision(verdict, findings)
