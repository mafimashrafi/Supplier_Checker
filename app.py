import html
import json
import tempfile
from pathlib import Path

import streamlit as st

from run_eval import DATA, SUMMARY, all_packs, evaluate
from src.graph import resume_pack, start_pack
from src.report import save_report
from src.rules import APPROVE, NEEDS, REJECT

st.set_page_config(page_title="Supplier document checker", page_icon="📄", layout="wide")

COLOURS = {APPROVE: "#1e7a4c", REJECT: "#b42318", NEEDS: "#b25e09"}

st.markdown("""
<style>
.verdict {border-left: 6px solid var(--c); background: color-mix(in srgb, var(--c) 12%, transparent);
          padding: 0.9rem 1.2rem; border-radius: 4px; margin: 0.5rem 0 1.2rem;}
.verdict b {font-size: 1.6rem; color: var(--c);}
.verdict span {display: block; opacity: 0.8; margin-top: 0.2rem;}
.reason {margin: 0.9rem 0 0.2rem;}
.rule {font-weight: 600;}
.quote {font-family: Georgia, "Times New Roman", serif; font-size: 1.02rem; line-height: 1.55;
        border-left: 2px solid rgba(128,128,128,0.45); padding: 0.1rem 0 0.1rem 0.9rem;
        margin: 0.35rem 0 1rem 0.2rem; opacity: 0.9;}
</style>
""", unsafe_allow_html=True)


def verdict_block(verdict: str, subtitle: str) -> None:
    st.markdown(f'<div class="verdict" style="--c:{COLOURS[verdict]}"><b>{html.escape(verdict)}</b>'
                f"<span>{html.escape(subtitle)}</span></div>", unsafe_allow_html=True)


def reasons(findings: list[dict]) -> None:
    if not findings:
        st.write("Every company rule passed.")
    for f in findings:
        quote = f'<div class="quote">“{html.escape(f["quote"])}”</div>' if f.get("quote") else ""
        st.markdown(f'<div class="reason"><span class="rule">{html.escape(f["rule"])}</span>&ensp;'
                    f'{html.escape(f["reason"])}</div>{quote}', unsafe_allow_html=True)


def extracted_table(doc: dict | None) -> None:
    if not doc:
        st.write("Nothing was extracted.")
        return
    show = lambda x: "" if x is None else (f"{x:g}" if isinstance(x, float) else str(x))
    rows = [{"Field": k, "Value": show(v.get("value")), "Quote from the document": v.get("quote") or ""}
            for k, v in doc.items() if isinstance(v, dict)]
    st.dataframe(rows, hide_index=True, width="stretch")
    for note in doc.get("extraction_notes", []):
        st.info(f"Note from the reader: {note}")


st.title("Supplier document checker")
st.write("Reads a supplier quotation, compares it with purchase request PR-2026-114 and the company rules, "
         "and answers Approve, Reject or Needs a person to check, quoting the document.")

one, all10, how = st.tabs(["Check a quotation", "All 10 sample packs", "How it works"])

# --- tab 1: one quotation ---------------------------------------------------
with one:
    left, right = st.columns([1, 2], gap="large")
    with left:
        source = st.radio("Quotation", ["Sample pack", "Upload a PDF"], horizontal=True)
        if source == "Sample pack":
            pack = st.selectbox("Sample pack", all_packs())
            pdf_path = str(DATA / f"{pack}.pdf")
        else:
            upload = st.file_uploader("Supplier PDF", type="pdf")
            pdf_path = None
            if upload:
                tmp = Path(tempfile.gettempdir()) / upload.name
                tmp.write_bytes(upload.getvalue())
                pdf_path = str(tmp)
        ask = st.toggle("Ask me when the system is unsure", value=True)
        if st.button("Check quotation", type="primary", disabled=pdf_path is None):
            with st.spinner("Reading the document and checking the rules…"):
                config, state = start_pack(pdf_path, ask_human=ask)
            st.session_state.run = {"config": config, "state": state}

    with right:
        run = st.session_state.get("run")
        if not run:
            st.write("Pick a sample pack or upload a quotation, then press Check quotation.")
        else:
            state = run["state"]
            paused = "__interrupt__" in state
            doc = state.get("doc") or {}
            supplier = (doc.get("supplier_name") or {}).get("value") or Path(state["pdf_path"]).stem
            item = (doc.get("item_code") or {}).get("value") or "?"

            if paused:
                verdict_block(NEEDS, f"{supplier}, item {item}. The system is not sure, so it stopped to ask you.")
                reasons(state["decision"]["findings"])
                with st.form("review"):
                    choice = st.radio("Your decision", [APPROVE, REJECT, NEEDS], horizontal=True, index=None,
                                      format_func=lambda v: "Leave for further checking" if v == NEEDS else v)
                    note = st.text_input("Reason for your decision (optional)")
                    submitted = st.form_submit_button("Save decision", type="primary")
                    if submitted and choice is None:
                        st.warning("Choose a decision before saving.")
                    elif submitted:
                        new_state = resume_pack(run["config"],
                                                {"verdict": choice, "note": note, "reviewer": "app user"})
                        save_report(new_state["report"])
                        st.session_state.run = {"config": run["config"], "state": new_state}
                        st.rerun()
            else:
                rep = state["report"]
                save_report(rep)
                sub = f"{supplier}, item {item}."
                if rep["decided_by"] == "person":
                    rv = rep["review"]
                    sub += f" Decided by a person (system said: {rep['system_verdict']})."
                    if rv.get("note"):
                        sub += f" Note: {rv['note']}"
                verdict_block(rep["final_verdict"], sub)
                reasons(rep["reasons"])

            with st.expander("What was read from the document"):
                extracted_table(doc)
            with st.expander("Document text"):
                st.text(state.get("text") or "No text could be read.")

# --- tab 2: all 10 ------------------------------------------------------------
with all10:
    st.write("The system's own verdict for each sample pack (no person involved), compared with our reading "
             "of the company rules. BIAI did not supply an answer key.")
    if st.button("Run all 10 again", help="Makes 10 calls to Gemini"):
        bar = st.progress(0.0, text="Starting…")
        evaluate(all_packs(), progress=lambda i, n, row: bar.progress(i / n, text=f"Checked {row['pack']}"))
        bar.empty()

    if SUMMARY.exists():
        summary = json.loads(SUMMARY.read_text())
        st.metric("Correct", f"{summary['correct']} of {summary['total']}")
        st.caption(f"Run at {summary['run_at']} with model {summary['model']}.")
        st.dataframe(
            [{"Pack": r["pack"], "Supplier": r["supplier"], "Expected": r["expected"],
              "System said": r["system_verdict"], "Match": "Yes" if r["correct"] else "No",
              "Rules that fired": ", ".join(r["rules"]) or "None", "Seconds": r["seconds"]}
             for r in summary["packs"]],
            hide_index=True, width="stretch",
        )
    else:
        st.write("No results yet. Run `python run_eval.py` or press Run all 10 again.")

# --- tab 3: how it works ------------------------------------------------------
with how:
    st.markdown("""
The check runs as fixed steps, one after another:

1. **Read the PDF** and take out its text.
2. **Extract the facts** (supplier, item, quantity, price, VAT, payment, delivery, penalty, validity).
   This is the only step that uses AI, and it is told to copy what the document says, never to judge it.
   Every value comes with the exact sentence it was copied from.
3. **Verify** in plain code that each quoted sentence is really in the document, and redo the arithmetic.
4. **Apply the company rules** in plain code: any Reject rule wins, then any Needs-a-person rule, otherwise Approve.
5. **Ask a person** when the answer is Needs a person to check, and record their decision.
6. **Report** the decision with every reason and the supporting quote.

If the document cannot be read or the AI service fails, the quotation goes to a person instead of being guessed.
""")