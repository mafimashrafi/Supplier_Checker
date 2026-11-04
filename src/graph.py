import argparse
import sys
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Callable, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

import src.extract as llm
from src.ingest import extract_text
from src.report import build_report, save_report, to_text
from src.rules import APPROVE, NEEDS, REJECT, decide, load_purchase_request
from src.schema import SupplierDoc
from src.verify import Issue, verify

PR_PATH = Path(__file__).resolve().parent.parent / "data" / "purchase-request.csv"
MIN_TEXT_CHARS = 20  # less than this means no text layer (e.g. a scan)
VERDICTS = (APPROVE, REJECT, NEEDS)


class State(TypedDict, total=False):
    pdf_path: str
    ask_human: bool
    text: str
    doc: dict  # SupplierDoc as plain data
    issues: list[dict]
    decision: dict  # {"verdict": ..., "findings": [...]}
    review: dict  # the person's answer, if asked
    report: dict
    error: str


# --- steps -----------------------------------------------------------------

def ingest(state: State) -> State:
    try:
        text = extract_text(state["pdf_path"])
    except Exception as e:
        return {"error": f"Could not open the PDF: {e}"}
    if len(text.strip()) < MIN_TEXT_CHARS:
        return {"error": "The PDF has no readable text (it may be a scan)."}
    return {"text": text}


def extract(state: State) -> State:
    try:
        return {"doc": llm.extract_fields(state["text"]).model_dump()}
    except Exception as e:
        return {"error": f"The document could not be read reliably: {type(e).__name__}: {e}"}


def check(state: State) -> State:
    doc = SupplierDoc.model_validate(state["doc"])
    return {"issues": [asdict(i) for i in verify(doc, state["text"])]}


def apply_rules(state: State) -> State:
    doc = SupplierDoc.model_validate(state["doc"])
    issues = [Issue(**i) for i in state["issues"]]
    d = decide(doc, load_purchase_request(PR_PATH), issues)
    return {"decision": {"verdict": d.verdict, "findings": [asdict(f) for f in d.findings]}}


def fail(state: State) -> State:
    finding = {"rule": "System", "level": NEEDS, "reason": state["error"], "quote": None, "fields": []}
    return {"decision": {"verdict": NEEDS, "findings": [finding]}}


def human_review(state: State) -> State:
    answer = interrupt({
        "pack": Path(state["pdf_path"]).stem,
        "system_verdict": state["decision"]["verdict"],
        "findings": state["decision"]["findings"],
        "question": f"Choose one: {', '.join(VERDICTS)}",
    })
    if answer.get("verdict") not in VERDICTS:
        raise ValueError(f"Reviewer verdict must be one of {VERDICTS}, got {answer.get('verdict')!r}")
    return {"review": answer}


def report(state: State) -> State:
    pack = Path(state["pdf_path"]).stem
    return {"report": build_report(pack, state.get("doc"), state["decision"], state.get("review"))}


# --- routing ---------------------------------------------------------------

def ok_or_fail(next_step: str):
    return lambda state: "fail" if state.get("error") else next_step


def needs_person(state: State) -> str:
    unsure = state["decision"]["verdict"] == NEEDS
    return "human_review" if unsure and state.get("ask_human") else "report"


def build_graph():
    g = StateGraph(State)
    for name, fn in [("ingest", ingest), ("extract", extract), ("verify", check),
                     ("decide", apply_rules), ("fail", fail),
                     ("human_review", human_review), ("report", report)]:
        g.add_node(name, fn)

    g.add_edge(START, "ingest")
    g.add_conditional_edges("ingest", ok_or_fail("extract"), ["extract", "fail"])
    g.add_conditional_edges("extract", ok_or_fail("verify"), ["verify", "fail"])
    g.add_edge("verify", "decide")
    g.add_conditional_edges("decide", needs_person, ["human_review", "report"])
    g.add_conditional_edges("fail", needs_person, ["human_review", "report"])
    g.add_edge("human_review", "report")
    g.add_edge("report", END)
    return g.compile(checkpointer=InMemorySaver())  # the checkpointer lets the graph pause


GRAPH = build_graph()


def start_pack(pdf_path: str, ask_human: bool = False) -> tuple[dict, dict]:
    """Start one pack. Returns (config, state). If the state has "__interrupt__",
    the graph is paused at human_review; continue it with resume_pack()."""
    config = {"configurable": {"thread_id": str(uuid.uuid4())}}
    state = GRAPH.invoke({"pdf_path": str(pdf_path), "ask_human": ask_human}, config)
    return config, state


def resume_pack(config: dict, answer: dict) -> dict:
    """Continue a paused pack with the person's answer. Returns the new state."""
    return GRAPH.invoke(Command(resume=answer), config)


def run_pack(pdf_path: str, reviewer: Callable[[dict], dict] | None = None) -> dict:
    """Run one pack through the graph and return its report.

    reviewer: called with the review question when the system is unsure; must
    return {"verdict": ..., "note": ..., "reviewer": ...}. None = never ask.
    """
    config, state = start_pack(pdf_path, ask_human=reviewer is not None)
    while "__interrupt__" in state:  # paused at human_review
        state = resume_pack(config, reviewer(state["__interrupt__"][0].value))
    return state["report"]


def console_reviewer(question: dict) -> dict:
    """Ask the person at the terminal."""
    print(f"\n{question['pack']} needs a person to check:")
    for f in question["findings"]:
        print(f"  - [{f['rule']}] {f['reason']}")
        if f.get("quote"):
            print(f'      "{f["quote"]}"')
    choices = {"a": APPROVE, "r": REJECT, "n": NEEDS}
    pick = ""
    while pick not in choices:
        pick = input("Your decision: [a]pprove, [r]eject, [n]eeds more checking: ").strip().lower()[:1]
    return {"verdict": choices[pick], "note": input("Note (optional): ").strip(), "reviewer": "console"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check one supplier pack.")
    parser.add_argument("pdf", help="Path to the supplier PDF")
    parser.add_argument("--review", action="store_true", help="Ask a person when the system is unsure")
    args = parser.parse_args(argv)

    rep = run_pack(args.pdf, reviewer=console_reviewer if args.review else None)
    print("\n" + to_text(rep))
    print(f"\nSaved {save_report(rep)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())