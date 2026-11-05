"""Streamlit UI. A thin layer: it calls the same graph as the command line.

    streamlit run app.py
"""

import html
import json
import os
import tempfile
from pathlib import Path

import streamlit as st

from run_eval import DATA, SUMMARY, all_packs, evaluate
from src.graph import resume_pack, start_pack
from src.report import checklist, save_report
from src.rules import APPROVE, NEEDS, REJECT

REPO_URL = "https://github.com/mafimashrafi/Supplier_Checker"

st.set_page_config(page_title="Supplier document checker", page_icon="📄", layout="wide")

# On Streamlit Cloud the key lives in the app's Secrets; locally it comes from .env.
# extract.py reads environment variables, so copy the secrets there if needed.
try:
    for name in ("GEMINI_API_KEY", "GEMINI_MODEL"):
        if name not in os.environ and name in st.secrets:
            os.environ[name] = str(st.secrets[name])
except Exception:
    pass  # no secrets file (e.g. running locally with .env): nothing to copy

esc = html.escape

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,700;9..144,800&family=JetBrains+Mono:wght@500&display=swap');
:root {
  --navy: #1d2a40; --navy-2: #26354d; --navy-line: #3b4a63; --ink: #1b2433; --muted: #5b667a;
  --blue: #2f5d8a; --band: #e8edf4; --card: #f5f7fb; --line: #e3e8ef;
  --serif: 'Fraunces', Georgia, 'Times New Roman', serif;
  --mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, Menlo, monospace;
}
header[data-testid="stHeader"], [data-testid="stToolbar"], footer, #MainMenu { display: none !important; }
[data-testid="stElementContainer"]:has(style) { display: none; }  /* this style block takes no space */
[data-testid="stMain"] { overflow-x: hidden; }
.block-container, [data-testid="stMainBlockContainer"] { max-width: 1110px; padding: 0 1.5rem 0 !important; }

/* full-width bands that line up with the centred content */
.bleed { margin-left: calc(50% - 50vw); margin-right: calc(50% - 50vw);
         padding-left: calc(50vw - 50%); padding-right: calc(50vw - 50%); }

.hero { background: var(--navy); color: #fff; padding-top: 42px; padding-bottom: 40px;
        display: flex; gap: 48px; justify-content: space-between; flex-wrap: wrap; }
.hero-main { flex: 1 1 480px; max-width: 560px; }
.eyebrow { font-size: 0.72rem; font-weight: 700; letter-spacing: 0.14em; text-transform: uppercase; }
.hero .eyebrow { color: #b8c4d6; }
.hero h1 { font-family: var(--serif); font-weight: 800; font-size: clamp(2.4rem, 5vw, 3.3rem); line-height: 1.04;
           color: #fff; margin: 14px 0 16px; padding: 0; letter-spacing: -0.01em; }
.hero p { color: #dce3ee; font-size: 1.02rem; line-height: 1.55; margin: 0; }
.hero-side { flex: 0 1 368px; display: flex; flex-direction: column; gap: 12px; }
.hero-card { background: var(--navy-2); border: 1px solid var(--navy-line); border-radius: 8px; padding: 13px 16px; }
.hero-card .eyebrow { color: #a9b6c9; font-size: 0.66rem; }
.hero-card .val { margin-top: 5px; font-weight: 700; }
.hero-card .mono { font-family: var(--mono); font-weight: 500; font-size: 1rem; }

/* tabs as a full-width band of three equal tabs */
[data-testid="stTabs"] [role="tablist"] { background: var(--band); box-shadow: 0 0 0 100vmax var(--band);
  clip-path: inset(0 -100vmax); gap: 0; border-bottom: 1px solid #d9e0ea; }
[data-testid="stTab"] { flex: 1; display: flex; justify-content: center; align-items: center; height: 46px;
  margin: 0; padding: 0; border-bottom: 3px solid transparent !important; }
[data-testid="stTab"][aria-selected="true"] { border-bottom-color: var(--blue) !important; }
[data-testid="stTab"]::before, [data-testid="stTab"]::after,
[data-testid="stTabs"] [role="tablist"]::before, [data-testid="stTabs"] [role="tablist"]::after { display: none; }
[data-testid="stTab"] p { font-size: 0.95rem; color: #4a5568; }
[data-testid="stTab"][aria-selected="true"] p { color: var(--ink); font-weight: 700; }
[data-testid="stTabPanel"] { padding-top: 34px; min-height: calc(100vh - 470px); }  /* keeps the footer low */
@media (max-width: 640px) {
  [data-testid="stTab"] { height: 54px; padding: 0 6px; }
  [data-testid="stTab"] p { font-size: 0.84rem; line-height: 1.2; text-align: center; white-space: normal; }
}

.section-title { font-family: var(--serif); font-weight: 700; font-size: 1.75rem; color: var(--ink); margin: 0 0 18px; }

/* the quotation form card */
.st-key-quote_card, .st-key-review_card { background: var(--card); border: 1px solid var(--line);
  border-radius: 10px; padding: 20px 21px 21px; }
.card-title { font-weight: 700; font-size: 1.08rem; color: var(--ink); margin-bottom: 4px; }
.st-key-quote_card [data-testid="stBaseButton-primary"] { height: 44px; background: var(--blue);
  border-color: var(--blue); }
.st-key-quote_card [data-testid="stBaseButton-primary"] p { font-weight: 700; }
[data-testid="stSelectbox"] [role="group"] { background: #fff; border: 1px solid #d6dde7; }
[data-testid="stTextInput"] div:has(> input) { background: #fff; border: 1px solid #d6dde7; border-radius: 8px; }
[data-testid="stTextInput"] input { background: #fff; }
/* segmented control: grey track, white selected option */
[data-testid="stButtonGroup"] div:has(> button[data-variant="segmented_control"]) {
  background: #e3e8ef; padding: 4px; border-radius: 8px; gap: 4px; }
button[data-variant="segmented_control"] { flex: 1; border: none !important; background: transparent !important;
  border-radius: 6px !important; min-height: 36px; }
button[data-variant="segmented_control"] p { font-weight: 600; color: #4a5568; }
button[data-variant="segmented_control"][aria-checked="true"] { background: #fff !important;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.12); }
button[data-variant="segmented_control"][aria-checked="true"] p { color: var(--ink); }

/* verdict banner */
.answer { border: 1px solid var(--c-line); background: var(--c-bg); border-radius: 10px; padding: 18px 20px 16px; }
.answer .eyebrow { color: var(--c-ink); font-size: 0.68rem; }
.answer .verdict { font-family: var(--serif); font-weight: 800; font-size: 1.75rem; color: var(--c-ink);
                   margin-top: 4px; line-height: 1.15; }
.answer .sub { color: var(--c-ink); opacity: 0.85; margin-top: 6px; font-size: 0.95rem; }
.v-approve { --c-bg: #e8f5ec; --c-line: #b9dfc6; --c-ink: #14532d; }
.v-reject  { --c-bg: #fbeaea; --c-line: #efc2bf; --c-ink: #7a1712; }
.v-needs   { --c-bg: #fdf3e1; --c-line: #f1d9a8; --c-ink: #4f3204; }

/* rule table */
.rules { width: 100%; border-collapse: separate; border-spacing: 0; border: 1px solid var(--line);
         border-radius: 10px; overflow: hidden; margin-top: 14px; font-size: 0.93rem; }
.rules th { background: var(--card); text-align: left; font-size: 0.68rem; letter-spacing: 0.12em;
            text-transform: uppercase; color: var(--muted); font-weight: 700; padding: 11px 14px; }
.rules th, .rules td { border-left: none !important; border-right: none !important; border-bottom: none !important; }
.rules td { padding: 11px 14px; border-top: 1px solid var(--line) !important; vertical-align: top; color: var(--ink); }
.rules td.rule { font-weight: 700; width: 42%; }
.rules td.rule .why { display: block; font-weight: 400; color: var(--muted); font-size: 0.86rem; margin-top: 3px; }
.rules td.st { width: 92px; }
.rules td.q { font-style: italic; color: #39445a; }
.pill { display: inline-block; font-size: 0.76rem; font-weight: 700; padding: 2px 9px; border-radius: 999px;
        white-space: nowrap; }
.p-pass, .p-approve { background: #e3f3e8; color: #1e6b43; }
.p-unsure, .p-needs { background: #fdf0d5; color: #8a5300; }
.p-fail, .p-reject  { background: #fbe4e2; color: #a3241b; }
.p-none { background: var(--line); color: #44506a; }
.table-scroll { overflow-x: auto; }

/* sample pack grid */
.score { color: var(--muted); margin: -8px 0 18px; }
.score b { color: var(--ink); }
.packs { display: grid; grid-template-columns: repeat(auto-fill, minmax(190px, 1fr)); gap: 12px; }
.pack { background: var(--card); border: 1px solid var(--line); border-radius: 8px; padding: 14px 14px 12px;
        display: flex; flex-direction: column; align-items: flex-start; }
.pack .name { font-family: var(--mono); font-weight: 500; font-size: 0.9rem; color: var(--ink); }
.pack .sup { color: var(--muted); font-size: 0.88rem; margin: 4px 0 9px; flex: 1; }
.pack .match { display: block; font-size: 0.78rem; color: var(--muted); margin-top: 7px; }

/* how it works */
.steps { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 14px; }
.step { background: var(--card); border: 1px solid var(--line); border-radius: 10px; padding: 20px 20px 18px; }
.step .num { font-family: var(--serif); font-weight: 800; font-size: 2rem; color: var(--blue); line-height: 1; }
.step h4 { font-size: 1rem; font-weight: 700; color: var(--ink); margin: 12px 0 6px; padding: 0; }
.step p { color: #3f4a5e; font-size: 0.92rem; line-height: 1.5; margin: 0; }
.note { color: var(--muted); font-size: 0.92rem; padding-top: 18px; }

.footer { background: #2a374d; color: #dce3ee; font-size: 0.86rem; padding-top: 26px; padding-bottom: 26px;
          margin-top: 64px; display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.footer b { color: #fff; }
.footer a { color: #dce3ee; }
</style>""", unsafe_allow_html=True)


VERDICT_CLASS = {APPROVE: "v-approve", REJECT: "v-reject", NEEDS: "v-needs"}
VERDICT_PILL = {APPROVE: "p-approve", REJECT: "p-reject", NEEDS: "p-needs"}
STATUS_PILL = {"Passed": "p-pass", "Unsure": "p-unsure", "Failed": "p-fail"}


def answer_banner(pack: str, verdict: str, sub: str) -> None:
    st.markdown(
        f'<div class="answer {VERDICT_CLASS[verdict]}"><div class="eyebrow">Answer · {esc(pack)}</div>'
        f'<div class="verdict">{esc(verdict)}</div><div class="sub">{esc(sub)}</div></div>',
        unsafe_allow_html=True)


def rules_table(rows: list[dict]) -> None:
    body = "".join(
        f'<tr><td class="rule">{esc(r["label"])}'
        + (f'<span class="why">{esc(r["reason"])}</span>' if r["reason"] else "")
        + f'</td><td class="st"><span class="pill {STATUS_PILL[r["status"]]}">{r["status"]}</span></td>'
        f'<td class="q">{"“" + esc(r["quote"]) + "”" if r["quote"] else ""}</td></tr>'
        for r in rows)
    st.markdown(f'<div class="table-scroll"><table class="rules"><thead><tr><th>Rule</th><th>Status</th>'
                f'<th>Quote</th></tr></thead><tbody>{body}</tbody></table></div>', unsafe_allow_html=True)


def extracted_table(doc: dict | None) -> None:
    if not doc:
        st.write("Nothing was extracted.")
        return

    def show(x) -> str:
        return "" if x is None else (f"{x:g}" if isinstance(x, float) else str(x))

    rows = [{"Field": k, "Value": show(v.get("value")), "Quote from the document": v.get("quote") or ""}
            for k, v in doc.items() if isinstance(v, dict)]
    st.dataframe(rows, hide_index=True, width="stretch")
    for note in doc.get("extraction_notes", []):
        st.info(f"Note from the reader: {note}")


# --- header ---------------------------------------------------------------------
st.markdown(
    '<div class="hero bleed"><div class="hero-main"><div class="eyebrow">Procurement · Demo</div>'
    "<h1>Supplier document checker</h1>"
    "<p>Reads a supplier quotation and compares it with purchase request PR-2026-114 and the company rules. "
    "It answers Approve, Reject or Needs a person to check, and quotes the document for every finding.</p></div>"
    '<div class="hero-side"><div class="hero-card"><div class="eyebrow">Checking against</div>'
    '<div class="val mono">PR-2026-114</div></div>'
    '<div class="hero-card"><div class="eyebrow">Possible answers</div>'
    '<div class="val">Approve · Reject · Needs a person</div></div></div></div>',
    unsafe_allow_html=True)

one, all10, how = st.tabs(["Check a quotation", "All 10 sample packs", "How it works"])

# --- tab 1: one quotation -------------------------------------------------------------
with one:
    left, right = st.columns([1, 2], gap="large")
    with left, st.container(key="quote_card"):
        st.markdown('<div class="card-title">Quotation</div>', unsafe_allow_html=True)
        source = st.segmented_control("Source", ["Sample pack", "Upload a PDF"], default="Sample pack",
                                      label_visibility="collapsed", width="stretch") or "Sample pack"
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
        if st.button("Check quotation", type="primary", disabled=pdf_path is None, width="stretch"):
            with st.spinner("Reading the document and checking the rules…"):
                config, state = start_pack(pdf_path, ask_human=ask)
            st.session_state.run = {"config": config, "state": state}

    with right:
        run = st.session_state.get("run")
        if not run:
            st.markdown('<div class="answer v-none" style="--c-bg:#f5f7fb;--c-line:#e3e8ef;--c-ink:#5b667a">'
                        '<div class="eyebrow">Answer</div><div class="sub">Pick a sample pack or upload a '
                        "quotation, then press Check quotation.</div></div>", unsafe_allow_html=True)
        else:
            state = run["state"]
            pack_name = Path(state["pdf_path"]).stem
            paused = "__interrupt__" in state
            doc = state.get("doc") or {}
            supplier = (doc.get("supplier_name") or {}).get("value") or "Unknown supplier"
            item = (doc.get("item_code") or {}).get("value") or "?"

            if paused:
                answer_banner(pack_name, NEEDS,
                              f"{supplier}, item {item}. The system is not sure, so it stopped to ask you.")
                preview = {"reasons": state["decision"]["findings"],
                           "extracted": {k: v for k, v in doc.items() if isinstance(v, dict)}}
                rules_table(checklist(preview))
                st.write("")
                with st.container(key="review_card"), st.form("review", border=False):
                    st.markdown('<div class="card-title">Your decision</div>', unsafe_allow_html=True)
                    choice = st.radio("Your decision", [APPROVE, REJECT, NEEDS], horizontal=True, index=None,
                                      label_visibility="collapsed",
                                      format_func=lambda v: "Leave for further checking" if v == NEEDS else v)
                    note = st.text_input("Reason for your decision (optional)")
                    submitted = st.form_submit_button("Save decision", type="primary")
                    if submitted and choice is None:
                        st.warning("Choose a decision before saving.")
                    elif submitted:
                        answer = {"verdict": choice, "note": note, "reviewer": "app user"}
                        new_state = resume_pack(run["config"], answer)
                        save_report(new_state["report"])
                        st.session_state.run = {"config": run["config"], "state": new_state}
                        st.rerun()
            else:
                rep = state["report"]
                save_report(rep)
                sub = f"{supplier}, item {item}."
                if rep["decided_by"] == "person":
                    sub += f" Decided by a person (system said: {rep['system_verdict']})."
                    if rep["review"].get("note"):
                        sub += f" Note: {rep['review']['note']}"
                answer_banner(pack_name, rep["final_verdict"], sub)
                rules_table(checklist(rep))

            st.write("")
            with st.expander("What was read from the document"):
                extracted_table(doc)
            with st.expander("Document text"):
                st.text(state.get("text") or "No text could be read.")

# --- tab 2: all 10 ---------------------------------------------------------------------
with all10:
    st.markdown('<div class="section-title">All 10 sample packs</div>', unsafe_allow_html=True)
    summary = json.loads(SUMMARY.read_text()) if SUMMARY.exists() else None
    if summary:
        st.markdown(
            f'<p class="score"><b>{summary["correct"]} of {summary["total"]}</b> match our expected verdicts '
            f"(our own reading of the rules; BIAI gave no answer key). Model {esc(str(summary['model']))}, "
            f"run {esc(summary['run_at'][:16].replace('T', ' '))} UTC.</p>", unsafe_allow_html=True)
    rows = {r["pack"]: r for r in (summary or {}).get("packs", [])}
    cards = []
    for pack in all_packs():
        r = rows.get(pack)
        if r:
            match = "Matches expected" if r["correct"] else f"Expected: {r['expected']}"
            pill = f'<span class="pill {VERDICT_PILL[r["system_verdict"]]}">{esc(r["system_verdict"])}</span>'
            sup, extra = esc(r["supplier"] or ""), f'<span class="match">{esc(match)}</span>'
        else:
            pill, sup, extra = '<span class="pill p-none">Not run yet</span>', "", ""
        cards.append(f'<div class="pack"><div class="name">{esc(pack)}</div><div class="sup">{sup}</div>'
                     f"{pill}{extra}</div>")
    st.markdown(f'<div class="packs">{"".join(cards)}</div>', unsafe_allow_html=True)
    st.write("")
    if st.button("Run all 10 again", help="Makes 10 calls to Gemini"):
        bar = st.progress(0.0, text="Starting…")
        evaluate(all_packs(), progress=lambda i, n, row: bar.progress(i / n, text=f"Checked {row['pack']}"))
        st.rerun()

# --- tab 3: how it works ---------------------------------------------------------------
with how:
    st.markdown(
        '<div class="section-title">How it works</div><div class="steps">'
        '<div class="step"><div class="num">1</div><h4>Read the quotation</h4><p>Text is pulled from the sample '
        "pack or the PDF you upload. AI copies out the facts (price, quantity, payment, delivery and so on), "
        "each with the exact sentence it came from. It never sees the rules.</p></div>"
        '<div class="step"><div class="num">2</div><h4>Check</h4><p>Plain code confirms every quoted sentence is '
        "really in the document, redoes the arithmetic, and checks each detail against PR-2026-114 and the "
        "company rules.</p></div>"
        '<div class="step"><div class="num">3</div><h4>Answer with quotes</h4><p>Any Reject rule wins, then any '
        "Needs-a-person rule, otherwise Approve. When unsure, it stops and asks a person, and every finding "
        "quotes the document.</p></div></div>"
        '<p class="note">If the document cannot be read or the AI service fails, the quotation goes to a person '
        "instead of being guessed.</p>",
        unsafe_allow_html=True)

# --- footer ----------------------------------------------------------------------------
st.markdown(
    '<div class="footer bleed"><div><b>Supplier document checker</b> · Demo build. Checks run on the server '
    f'with the Python pipeline.</div><div><a href="{REPO_URL}" target="_blank">Code on GitHub</a></div></div>',
    unsafe_allow_html=True)