import json
from pathlib import Path

from src.rules import NEEDS


def build_report(pack: str, doc: dict | None, decision: dict, review: dict | None = None) -> dict:
    doc = doc or {}
    value = lambda f: (doc.get(f) or {}).get("value")
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