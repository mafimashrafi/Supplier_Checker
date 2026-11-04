# Supplier document checker

[![tests](https://github.com/mafimashrafi/Supplier_Checker/actions/workflows/tests.yaml/badge.svg)](https://github.com/mafimashrafi/Supplier_Checker/actions/workflows/tests.yaml)

**Live demo:** https://dcvj2ywtveutjxd7nar8wh.streamlit.app/

A garment company receives supplier quotations. This system reads each one, compares it with the company's purchase request, checks it against the company rules, and answers **Approve**, **Reject** or **Needs a person to check**, with the reason and the exact sentence from the document that supports it. When it is not sure, it stops and asks a person instead of guessing.

Built for BIAI AI Engineer Round 2, Task 1. All companies and documents are fictional sample files supplied by BIAI.

## Results

<!-- Fill in from outputs/eval_summary.json after running: python run_eval.py -->
**Score: _ / 10** on the sample packs, using Gemini model `_`.

BIAI did not supply an answer key. The expected verdicts below are our own reading of `data/company-rules.md` and are stored in `tests/expected_verdicts.json`.

| Pack | Expected | Why |
|---|---|---|
| 01 | Approve | Every rule passes |
| 02 | Approve | Boundary cases: no advance, validity exactly 30 days |
| 03 | Reject | Unit price 229 vs maximum 210 (9.05% over, limit 3%) |
| 04 | Needs a person | Unit price 6.65 vs maximum 6.50 (2.31% over, within 3%) |
| 05 | Reject | 40% advance (the sentence is repeated in the document) |
| 06 | Reject | No late-delivery penalty clause |
| 07 | Needs a person | Quantity 16,500 vs 20,000 requested (17.5% short) |
| 08 | Reject | TIN/BIN replaced by "available on request" |
| 09 | Needs a person | Payment "30 to 90 days", not counted from delivery; 50,000 × 6.40 is 320,000 but the document says 322,000 |
| 10 | Reject | Delivery in 60 days (VAT also not shown separately) |

## How it works

The check runs as fixed steps, one after another, built with LangGraph:

```
ingest -> extract -> verify -> decide -> [human review] -> report
   \          \
    +-> fail --+---------------^     (unreadable PDF or AI error: a person checks)
```

1. **Ingest** reads the PDF's text (pdfplumber).
2. **Extract** is the only step that uses AI (Gemini). It returns strict JSON: supplier, item, quantity, price, totals, VAT, TIN/BIN, advance, payment terms, delivery, penalty and validity. It is told to copy what the document says, never to judge it, and every value comes with the exact sentence it was copied from. It never sees the company rules.
3. **Verify** (plain code) checks that every quoted sentence really is in the document and that each value appears in its quote, and recomputes quantity × price, VAT and the total.
4. **Decide** (plain code) applies each company rule as a separate function. Any Reject rule wins; otherwise any Needs-a-person rule; otherwise Approve.
5. **Human review** pauses the graph when the answer is Needs a person and resumes with the person's decision. The system's own verdict is kept alongside it.
6. **Report** gives the decision, every reason, and the supporting quote for each.

Two safety rules are built in: a value that is missing, or that could not be confirmed in the document, never leads to Approve or Reject; and if the PDF cannot be read or the AI service fails, the pack goes to a person instead of crashing.

## Run it locally

You need Python (developed and tested on 3.14) and a Gemini API key from [Google AI Studio](https://aistudio.google.com/).

```bash
git clone https://github.com/mafimashrafi/Supplier_Checker.git
cd Supplier_Checker
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # then put your key and model name in .env
```

`.env` needs two lines:

```
GEMINI_API_KEY=your-key
GEMINI_MODEL=your-model-name
```

Then:

```bash
# Check one quotation
python -m src.graph data/supplier-pack-04.pdf

# Same, but stop and ask you when the system is unsure
python -m src.graph data/supplier-pack-04.pdf --review

# Run all 10 packs and print the score (10 Gemini calls)
python run_eval.py
python run_eval.py --packs 03,09 --delay 5    # chosen packs, wait 5 s between calls

# Open the web app
streamlit run app.py
```

`run_eval.py` saves one report per pack in `outputs/reports/` and the score in `outputs/eval_summary.json`.

## Tests

```bash
pytest                                  # offline tests, no API key needed
pytest -m live                          # also call Gemini on all 10 packs
LIVE_PACKS=01,09,10 pytest -m live      # live tests on chosen packs only
```

The offline tests cover PDF reading, the extraction schema and prompt, the evidence and arithmetic checks, every company rule at its boundaries, the full graph (including human review and failure handling), the evaluation runner and the web app. In them, the AI step is replaced by a stand-in that returns the hand-checked values in `tests/expected_extraction.json`, so they are free and repeatable.

The live tests send each PDF to Gemini and compare every extracted field with `tests/expected_extraction.json`, and check that every quote really appears in the PDF.

GitHub Actions runs the offline tests on every push. The live tests run on demand: **Actions → tests → Run workflow**, tick the live option, and optionally choose packs. They need the repository secrets `GEMINI_API_KEY` and `GEMINI_MODEL`.

## Project structure

```
Supplier_Checker/
├── app.py                    Streamlit web app (calls the same graph as the command line)
├── run_eval.py               Runs all packs, prints and saves the score
├── src/
│   ├── ingest.py             PDF -> raw text
│   ├── schema.py             The extraction fields and the AI's instructions
│   ├── extract.py            Sends the text to Gemini, returns validated JSON
│   ├── verify.py             Checks quotes against the PDF; recomputes the arithmetic
│   ├── rules.py              The company rules as plain functions; the final decision
│   ├── graph.py              LangGraph pipeline with the human-review pause
│   └── report.py             Decision, reasons and quotes for one pack
├── tests/
│   ├── test_ingest.py        PDF reading
│   ├── test_extract.py       Schema, prompt, and live Gemini checks
│   ├── test_verify.py        Quote and arithmetic checks
│   ├── test_rules.py         Every rule, including boundaries
│   ├── test_graph.py         The full pipeline, human review, failures
│   ├── test_app_and_eval.py  Web app and evaluation runner
│   ├── expected_extraction.json   Hand-checked values for each PDF
│   └── expected_verdicts.json     Our expected verdict for each pack
├── data/                     BIAI sample files: 10 PDFs, purchase request, company rules
├── outputs/                  Results from run_eval.py
├── .github/workflows/        GitHub Actions (tests)
├── .streamlit/config.toml    App theme
├── pytest.ini                Test settings (live tests are opt-in)
├── requirements.txt          Pinned dependencies
└── .env.example              Template for your Gemini key and model
```

## How we read the rules

Some rules leave room for interpretation. These are the choices made, all covered by tests in `tests/test_rules.py`:

- **Boundaries count as compliant.** Exactly 3% over the maximum price is Needs a person, not Reject; exactly 20% advance, 30 days' validity, 45 days' delivery and a 5% quantity difference are treated the same way.
- **A penalty below 0.5% per week goes to a person.** The rules say it "must be at least 0.5%" but not what happens otherwise. No sample pack tests this.
- **A payment range is unclear.** "30 to 45 days" goes to a person even though it falls inside 30 to 60 days, because it is not clear who picks the day.
- **Payment must be counted from delivery.** Terms that do not say what the days are counted from go to a person.
- **Notes from the AI do not change the verdict.** Anything odd it notices (such as a repeated sentence) is shown to the reviewer but does not route the pack.

## Known limitations

- The evidence check confirms that a quote exists in the PDF and contains the value, but not that it is the right sentence. A number that appears elsewhere in the document could pass.
- The pipeline expects one item per quotation, as in all sample packs.
- Only text-based PDFs are supported; a scanned PDF is detected and sent to a person, not read.
- The expected verdicts are our own reading of the rules, not an official answer key.
- The Gemini SDK does not send field descriptions to the model, so all field instructions live in the system prompt (`src/schema.py`). This was found by a live test.