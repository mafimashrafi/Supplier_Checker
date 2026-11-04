import sys

import pdfplumber


def extract_text(pdf_path: str) -> str:
    """Return the raw text of every page, joined by newlines."""
    with pdfplumber.open(pdf_path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


if __name__ == "__main__":
    print(extract_text(sys.argv[1]))