# Supplier document checker: one-page note

**Live demo:** https://dcvj2ywtveutjxd7nar8wh.streamlit.app/ · **Code:** https://github.com/mafimashrafi/Supplier_Checker

## What I built

A system that reads a supplier quotation and answers Approve, Reject or Needs a person to check, with each reason and the supporting sentence from the document. It runs as fixed LangGraph steps: read the PDF, extract facts with Gemini, verify them, apply the rules, pause for a person when unsure, report. The key design choice: **the AI only reads; plain code decides**. Gemini never sees the rules; every value it returns carries a quote, and code checks each quote is really in the PDF and redoes the arithmetic. A missing or unconfirmed value never causes Approve or Reject, and an unreadable PDF or Gemini failure goes to a person instead of crashing.

**How I worked:** I used Claude (Anthropic) for brainstorming, tooling guidance and generating the code and tests. I reviewed all of it, changed several design decisions (such as limiting extraction to the fields the rules need) and edited code to make it clearer to me. I kept the tests as generated: AI writes test boilerplate and finds edge cases far faster than I could, and that time went into reviewing the logic.

## How I tested it

- **141 offline tests**, run by GitHub Actions on every push: PDF reading, schema and prompt, quote and arithmetic checks, every rule at its boundaries, the full graph including human review and failures, and the web app. The AI step is replaced by hand-checked values, so they are free and repeatable.
- **Live tests** compare Gemini's 19 extracted fields per pack with a hand-checked answer key and check every quote exists in the PDF.

## Results

**10 / 10 correct** with `gemini-3.5-flash-lite`, about 3 seconds per pack (2 Approve, 5 Reject, 3 Needs a person). Reports are in `outputs/`. The expected verdicts are my own reading of the rules, since BIAI gave no answer key.

## What does not work well

- **Model choice.** My first Gemini model kept failing with "high demand" errors. I switched to a lighter model rather than investing in prompt and context engineering, which would make the system less dependent on one model.
- **Silently lost instructions.** The Gemini SDK drops schema field descriptions; a live test caught the missing item code. Instructions now live in the prompt, guarded by a test.
- **10/10 on 10 known samples is not proof.** The prompt was refined on these same packs and may be tuned to them.
- **The evidence check is shallow.** It confirms a quote exists and contains the value, not that it is the right sentence.
- **Narrow input.** One item per quotation, text PDFs only (scans go to a person); review decisions in the demo are not stored permanently.

## What I would do next

- **More prompt and context engineering, and a bigger test set** with new suppliers and tricky wording, to measure generalisation.
- **Verify TIN/BIN against government records:** check the format, then confirm with the National Board of Revenue's e-TIN/BIN verification (API availability to be checked), so a made-up number is caught, not just a missing one.
- **Fine-tune a small extraction model** once a few hundred labelled quotations exist: cheaper per document, and it can run in-house so supplier data never leaves. With 10 samples, fine-tuning or training a new model is not yet justified.
- **Rules in a config file** (YAML) so procurement staff can change thresholds without editing code.
- **Stronger checks:** tie quotes to the right clause, extract twice and send disagreements to a person, OCR for scans, multi-item quotes.