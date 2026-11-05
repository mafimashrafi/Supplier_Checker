"""Build the final result for one supplier pack: decision, reasons, quotes.

Plain code, no LLM. The report keeps two verdicts apart:
  system_verdict  what the rules decided
  final_verdict   the same, unless a person reviewed it and decided otherwise
so the evaluation can score the system on its own.
"""

import json
from pathlib import Path

from src.rules import NEEDS


def build_report(pack: str, doc: dict | None, decision: dict, review: dict | None = None) -> dict:
    doc = doc or {}

    def value(field: str):
        return (doc.get(field) or {}).get("value")

    return {
        "pack": pack,
        "supplier": value("supplier_name"),
        "item": value("item_code"),
        "system_verdict": decision["verdict"],
        "final_verdict": review["verdict"] if review else decision["verdict"],
        "decided_by": "person" if review else "system",
        "reasons": decision["findings"],
        "review": review,
        "extraction_notes": doc.get("extraction_notes", []),
        "extracted": {f: v for f, v in doc.items() if isinstance(v, dict)},  # value + quote
    }


def to_text(report: dict) -> str:
    """Short, plain-language summary for the terminal or a reviewer."""
    lines = [
        f"{report['pack']}: {report['supplier'] or 'unknown supplier'} (item {report['item'] or '?'})",
        f"Decision: {report['final_verdict']}"
        + (f"  [system said: {report['system_verdict']}]" if report["decided_by"] == "person" else ""),
    ]
    if not report["reasons"]:
        lines.append("  All company rules passed.")
    for r in report["reasons"]:
        lines.append(f"  - [{r['rule']}] {r['reason']}")
        if r.get("quote"):
            lines.append(f'      "{r["quote"]}"')
    if report["review"]:
        rv = report["review"]
        lines.append(f"  Reviewed by {rv.get('reviewer') or 'a person'}: {rv['verdict']}"
                     + (f" ({rv['note']})" if rv.get("note") else ""))
    elif report["final_verdict"] == NEEDS:
        lines.append("  Waiting for a person to check.")
    for n in report["extraction_notes"]:
        lines.append(f"  Note from reader: {n}")
    return "\n".join(lines)


def save_report(report: dict, out_dir: str | Path = "outputs/reports") -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{report['pack']}.json"
    path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


# One row per company rule, for the results table: (label, rules that report on it,
# field whose quote supports the rule when it passes).
CHECKS = [
    ("Unit price within the maximum", ("Reject 1", "Needs 1", "Purchase request"), "unit_price"),
    ("Quantity within 5% of the request", ("Needs 2",), "quantity"),
    ("Advance payment at most 20%", ("Reject 2",), "advance_pct"),
    ("Late-delivery penalty of at least 0.5% a week", ("Reject 3", "Penalty note"), "penalty_pct_per_week"),
    ("Supplier TIN and BIN given", ("Reject 4",), "tin"),
    ("Delivery within 30 days", ("Reject 5", "Needs 4"), "delivery_value"),
    ("Payment 30 to 60 days after delivery", ("Needs 3",), "payment_days_min"),
    ("VAT at 15% shown separately", ("Needs 5",), "vat_rate_pct"),
    ("The numbers add up", ("Needs 6",), "total"),
    ("Quotation valid for at least 30 days", ("Needs 7",), "validity_days"),
    ("Every quote found in the document", ("Evidence",), None),
]


def checklist(report: dict) -> list[dict]:
    """Every company rule with status Passed, Unsure or Failed, a reason and a quote."""
    system = [r for r in report["reasons"] if r["rule"] == "System"]
    if system:  # the document could not be read, so no rule could be checked
        return [{"label": "Document could be read", "status": "Unsure",
                 "reason": system[0]["reason"], "quote": None}]
    rows = []
    for label, rules, field in CHECKS:
        found = [r for r in report["reasons"] if r["rule"] in rules]
        if any(r["level"] != NEEDS for r in found):
            status = "Failed"
        elif found:
            status = "Unsure"
        else:
            status = "Passed"
        evidence = (report["extracted"].get(field) or {}).get("quote") if field else None
        rows.append({
            "label": label,
            "status": status,
            "reason": " ".join(r["reason"] for r in found),
            "quote": next((r["quote"] for r in found if r.get("quote")), None) or (evidence if not found else None),
        })
    return rows