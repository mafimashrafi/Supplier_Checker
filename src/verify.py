from dataclasses import dataclass
from decimal import Decimal

from src.schema import SupplierDoc

CENT = Decimal("0.01")


@dataclass(frozen=True)
class Issue:
    kind: str  # "evidence" or "math"
    field: str
    message: str
    quote: str | None = None


def squash(s: str) -> str:
    """Collapse whitespace, so a quote that spans a line break still matches."""
    return " ".join(s.split())


def D(x: float) -> Decimal:
    """Float from the LLM -> exact Decimal (6.65 stays 6.65, not 6.6500000001)."""
    return Decimal(str(x))


def _as_text(value) -> str:
    """How a value should look inside its quote: 5664000.0 -> '5664000', 6.4 -> '6.4'."""
    if isinstance(value, (int, float)):
        return format(D(value).normalize(), "f")
    return str(value)


def check_evidence(doc: SupplierDoc, text: str) -> list[Issue]:
    issues = []
    page = squash(text)
    for name in SupplierDoc.model_fields:
        if name == "extraction_notes":
            continue
        f = getattr(doc, name)
        if f.quote is not None and squash(f.quote) not in page:
            issues.append(Issue("evidence", name, "Quote is not in the document.", f.quote))
            continue
        if f.value is None:
            continue  # a null with or without an explaining quote is fine
        if f.quote is None:
            issues.append(Issue("evidence", name, f"Value {f.value!r} has no supporting quote."))
            continue
        if f.value == 0:
            continue  # e.g. advance 0 from "No advance payment required"
        quote_clean = squash(f.quote).replace(",", "").lower()
        if _as_text(f.value).lower() not in quote_clean:
            issues.append(Issue("evidence", name, f"Value {f.value!r} does not appear in its quote.", f.quote))
    return issues


def _differs(a: Decimal, b: Decimal) -> bool:
    return abs(a - b) > CENT


def check_math(doc: SupplierDoc) -> list[Issue]:
    issues = []
    qty, price = doc.quantity.value, doc.unit_price.value
    line, sub = doc.line_amount.value, doc.subtotal.value
    rate, vat, total = doc.vat_rate_pct.value, doc.vat_amount.value, doc.total.value

    if None in (qty, price, line):
        issues.append(
            Issue("math", "line_amount", "Cannot check the line amount: quantity, unit price or amount is missing."))
    else:
        expected = (D(qty) * D(price)).quantize(CENT)
        if _differs(expected, D(line)):
            issues.append(Issue("math", "line_amount",
                                f"Quantity x unit price = {expected:,} but the document says {D(line):,.2f}.",
                                doc.line_amount.quote))

    if sub is not None and line is not None and _differs(D(sub), D(line)):
        issues.append(Issue("math", "subtotal",
                            f"Subtotal {D(sub):,.2f} does not equal the line amount {D(line):,.2f}.",
                            doc.subtotal.quote))

    base = sub if sub is not None else line  # VAT-included quotes have no subtotal
    if base is None or total is None:
        issues.append(Issue("math", "total", "Cannot check the total: subtotal/amount or total is missing."))
        return issues

    if vat is not None:
        if rate is not None:
            expected_vat = (D(base) * D(rate) / 100).quantize(CENT)
            if _differs(expected_vat, D(vat)):
                issues.append(Issue("math", "vat_amount",
                                    f"{D(rate).normalize()}% of {D(base):,.2f} = {expected_vat:,} but the document says {D(vat):,.2f}.",
                                    doc.vat_amount.quote))
        expected_total = D(base) + D(vat)
    else:
        expected_total = D(base)

    if _differs(expected_total, D(total)):
        issues.append(Issue("math", "total",
                            f"The total should be {expected_total:,.2f} but the document says {D(total):,.2f}.",
                            doc.total.quote))
    return issues


def verify(doc: SupplierDoc, text: str) -> list[Issue]:
    """All problems found in one extraction. Empty list = trustworthy."""
    return check_evidence(doc, text) + check_math(doc)
