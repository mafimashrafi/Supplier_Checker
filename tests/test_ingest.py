"""Tests for src/ingest.py. Run with: pytest tests/test_ingest.py -v"""

from pathlib import Path

import pytest

from src.ingest import extract_text

DATA = Path(__file__).resolve().parent.parent / "data"
PACKS = [DATA / f"supplier-pack-{i:02d}.pdf" for i in range(1, 11)]


@pytest.mark.parametrize("pdf", PACKS, ids=lambda p: p.stem)
def test_every_pack_has_text(pdf):
    text = extract_text(str(pdf))
    assert "QUOTATION" in text
    assert "TERMS AND CONDITIONS" in text


def test_table_row_stays_on_one_line():
    # The LLM needs qty, unit and price together on one line.
    text = extract_text(str(DATA / "supplier-pack-01.pdf"))
    assert "A Cotton twill fabric, 280 gsm 12,000 metre 472.00 5,664,000.00" in text


def test_tin_bin_present_in_normal_pack():
    text = extract_text(str(DATA / "supplier-pack-01.pdf"))
    assert "TIN: 101458013391" in text


def test_tin_bin_missing_in_pack_08():
    text = extract_text(str(DATA / "supplier-pack-08.pdf"))
    assert "TIN" not in text
    assert "available on request" in text


def test_printed_amount_kept_as_is_in_pack_09():
    # The PDF prints 322,000.00 (50,000 x 6.40 is really 320,000).
    # Extraction must keep the printed value, not "fix" it.
    text = extract_text(str(DATA / "supplier-pack-09.pdf"))
    assert "50,000 piece 6.40 322,000.00" in text


def test_missing_file_raises():
    with pytest.raises(FileNotFoundError):
        extract_text(str(DATA / "does-not-exist.pdf"))