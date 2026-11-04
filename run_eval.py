import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from src.graph import run_pack
from src.report import save_report

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
OUT = ROOT / "outputs"
EXPECTED = ROOT / "tests" / "expected_verdicts.json"
SUMMARY = OUT / "eval_summary.json"


def all_packs() -> list[str]:
    return sorted(p.stem for p in DATA.glob("supplier-pack-*.pdf"))


def evaluate(packs: list[str], delay: float = 0,
             progress: Callable[[int, int, dict], None] | None = None,
             out_dir: Path = OUT) -> dict:
    expected = json.loads(EXPECTED.read_text())["verdicts"]
    rows = []
    for i, pack in enumerate(packs):
        if i and delay:
            time.sleep(delay)
        start = time.perf_counter()
        report = run_pack(str(DATA / f"{pack}.pdf"))
        save_report(report, out_dir / "reports")
        want = expected.get(pack)
        rows.append({
            "pack": pack,
            "supplier": report["supplier"],
            "expected": want,
            "system_verdict": report["system_verdict"],
            "correct": want is not None and report["system_verdict"] == want,
            "rules": [r["rule"] for r in report["reasons"]],
            "failed_to_run": any(r["rule"] == "System" for r in report["reasons"]),
            "seconds": round(time.perf_counter() - start, 1),
        })
        if progress:
            progress(i + 1, len(packs), rows[-1])

    summary = {
        "run_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "model": os.environ.get("GEMINI_MODEL"),
        "correct": sum(r["correct"] for r in rows),
        "total": sum(r["expected"] is not None for r in rows),
        "packs": rows,
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / SUMMARY.name).write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    return summary


def print_row(done: int, total: int, row: dict) -> None:
    mark = "OK  " if row["correct"] else "MISS"
    rules = ", ".join(row["rules"]) or "all rules passed"
    print(f"[{done:>2}/{total}] {mark} {row['pack']}  expected {row['expected']!s:<24} "
          f"got {row['system_verdict']:<24} ({rules}; {row['seconds']} s)")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run all supplier packs and print the score.")
    parser.add_argument("--packs", default="", help="Comma-separated pack numbers, e.g. 01,09 (default: all)")
    parser.add_argument("--delay", type=float, default=0, help="Seconds to wait between packs")
    args = parser.parse_args(argv)

    chosen = [p.strip().zfill(2) for p in args.packs.split(",") if p.strip()]
    packs = [f"supplier-pack-{p}" for p in chosen] if chosen else all_packs()

    print(f"Model: {os.environ.get('GEMINI_MODEL')}  |  packs: {len(packs)}\n")
    summary = evaluate(packs, args.delay, progress=print_row)
    failed = sum(r["failed_to_run"] for r in summary["packs"])
    print(f"\nScore: {summary['correct']}/{summary['total']} correct"
          + (f"  ({failed} could not be processed; see reports)" if failed else ""))
    print(f"Saved {os.path.relpath(SUMMARY, ROOT)} and {len(packs)} reports in "
          f"{os.path.relpath(SUMMARY.parent / 'reports', ROOT)}/")
    return 0 if summary["correct"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())
