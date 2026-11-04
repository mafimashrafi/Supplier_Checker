"""Send one document's raw text to Gemini and get back a SupplierDoc.

The model only reads. It returns JSON that must match the SupplierDoc schema;
anything that does not match raises an error instead of being guessed at.

Usage (one file at a time):
    python -m src.extract data/supplier-pack-01.pdf
"""

import os
import sys

from dotenv import load_dotenv
from google import genai
from google.genai import types

from src.ingest import extract_text
from src.schema import SYSTEM_PROMPT, SupplierDoc

load_dotenv()

# Rename these if your .env uses different variable names.
API_KEY = os.environ

MODEL = os.environ["GEMINI_MODEL"]

client = genai.Client(api_key=API_KEY)


def extract_fields(text: str) -> SupplierDoc:
    """Raw document text in, validated SupplierDoc out."""
    response = client.models.generate_content(
        model=MODEL,
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


if __name__ == "__main__":
    doc = extract_fields(extract_text(sys.argv[1]))
    print(doc.model_dump_json(indent=2))