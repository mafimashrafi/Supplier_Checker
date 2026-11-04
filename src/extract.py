"""Send one document's raw text to Gemini and get back a SupplierDoc.

The model only reads. It returns JSON that must match the SupplierDoc schema;
anything that does not match raises an error instead of being guessed at.

Usage (one file at a time):
    python -m src.extract data/supplier-pack-01.pdf

The result is printed and saved to outputs/extracted/<pdf name>.json.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.ingest import extract_text
from src.schema import SYSTEM_PROMPT, SupplierDoc

load_dotenv()

# Rename these if your .env uses different variable names.
# API_KEY = os.environ["GEMINI_API_KEY"]
# MODEL = os.environ["GEMINI_MODEL"]
#
# client = genai.Client(api_key=API_KEY)


def extract_fields(text: str) -> SupplierDoc:
    """Raw document text in, validated SupplierDoc out."""
    # Rename these if your .env uses different variable names.
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
    response = client.models.generate_content(
        model=os.environ["GEMINI_MODEL"],
        contents=text,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=SupplierDoc,
            temperature=0,
        ),
    )
    # Validate the raw JSON ourselves so a bad answer fails loudly.
    return SupplierDoc.model_validate_json(response.text)


def save_json(doc: SupplierDoc, pdf_path: str, out_dir: str = "outputs/extracted") -> Path:
    """Write the extracted fields to <out_dir>/<pdf name>.json."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{Path(pdf_path).stem}.json"
    path.write_text(doc.model_dump_json(indent=2), encoding="utf-8")
    return path


if __name__ == "__main__":
    pdf_path = sys.argv[1]
    doc = extract_fields(extract_text(pdf_path))
    print(doc.model_dump_json(indent=2))
    print(f"Saved {save_json(doc, pdf_path)}")