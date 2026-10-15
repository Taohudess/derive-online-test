"""Grounded support-answer service.

Pipeline (each stage declares what it reads and writes; the runner enforces it):
  LOAD_KB -> RETRIEVE -> CLASSIFY_INTENT -> CHECK_SUPPORT -> ANSWER_OR_ABSTAIN

Usage:
  python app.py "How do I reset my password?"
  python app.py --kb other_kb.json --no-llm "question"
"""
import argparse
import json
import sys
from dataclasses import dataclass
from typing import Callable

import intent as intent_mod
from kb import load_kb
from retrieval import BM25Index
from templates import INSUFFICIENT, REFUSALS, other_template
from textproc import numbers, sentences, tokens

TOP_K = 3
SCORE_CAP = 0.95
ANSWER_THRESHOLD = 0.60   # support_score needed to answer (see README)


# ---- pipeline runner -----------------------------------------------------------

@dataclass
class Stage:
    name: str
    reads: tuple
    writes: tuple
    fn: Callable


def run_pipeline(stages, ctx):
    trace = []
    for st in stages:
        missing = [k for k in st.reads if k not in ctx]
        if missing:
            raise RuntimeError(f"{st.name}: missing inputs {missing}")
        out = st.fn({k: ctx[k] for k in st.reads})
        if set(out) != set(st.writes):
            raise RuntimeError(f"{st.name}: wrote {sorted(out)}, declared {list(st.writes)}")
        ctx.update(out)
        trace.append({"stage": st.name, "reads": list(st.reads), "writes": list(st.writes)})
    ctx["trace"] = trace
    return ctx


# ---- stages ----------------------------------------------------------------------

def load_kb_stage(c):
    kb = load_kb(c["kb_path"])
    return {"kb": kb, "index": BM25Index(kb)}


def retrieve_stage(c):
    hits = c["index"].search(c["question"], k=TOP_K)
    return {"retrieved": [{"doc": d, "bm25": s} for d, s in hits]}


def classify_intent_stage(c):
    r = intent_mod.classify(c["question"], c["kb"], llm=c["llm"])
    return {"intent": {"label": r.label, "source": r.source, "restricted": r.restricted}}


def support_score(question, doc, retrieved):
    """support_score = 0.95 * (0.7*coverage + 0.3*margin) * strength

    coverage  share of the question's content tokens found in the evidence doc
    margin    (best BM25 - second BM25) / best BM25, how clearly retrieval won
              (1.0 when only one doc matched at all)
    strength  b / (b + 1), b = evidence doc's BM25 (0 if not retrieved);
              saturating, so it approaches but never reaches 1
    The 0.95 factor plus strength < 1 keeps the score strictly below 0.95.
    """
    q = set(tokens(question))
    d = set(tokens(doc["title"] + " " + doc["text"]))
    coverage = len(q & d) / len(q) if q else 0.0
    bm = [h["bm25"] for h in retrieved]
    margin = (bm[0] - bm[1]) / bm[0] if len(bm) > 1 and bm[0] else (1.0 if bm else 0.0)
    b = next((h["bm25"] for h in retrieved if h["doc"]["id"] == doc["id"]), 0.0)
    strength = b / (b + 1)
    score = min(SCORE_CAP, SCORE_CAP * (0.7 * coverage + 0.3 * margin) * strength)
    parts = {"coverage": round(coverage, 3), "margin": round(margin, 3),
             "strength": round(strength, 3), "bm25": round(b, 3)}
    return round(score, 3), parts


def check_support_stage(c):
    label, kb, retrieved = c["intent"]["label"], c["kb"], c["retrieved"]
    by_id = {d["id"]: d for d in kb}
    # Evidence doc: the intent's doc if it is one, else the top retrieved doc.
    doc = by_id.get(label) or (retrieved[0]["doc"] if retrieved else None)
    if doc is None:
        return {"support": {"score": 0.0, "parts": {}, "doc": None, "ok": False,
                            "reason": "nothing retrieved"}}
    score, parts = support_score(c["question"], doc, retrieved)

    if c["intent"]["restricted"]:
        ok, reason = False, f"restricted intent: {label}"
    elif label == intent_mod.OTHER:
        ok, reason = False, "intent: other"
    elif label == intent_mod.AMBIGUOUS:
        ok, reason = False, "top documents tied, topic ambiguous"
    elif doc["id"] not in [h["doc"]["id"] for h in retrieved]:
        ok, reason = False, "intent doc not in retrieved passages"
    elif not numbers(c["question"]) <= numbers(doc["text"]):
        ok, reason = False, "question cites numbers not in the evidence"
    elif score < ANSWER_THRESHOLD:
        ok, reason = False, f"support_score below {ANSWER_THRESHOLD}"
    else:
        ok, reason = True, "supported"
    return {"support": {"score": score, "parts": parts, "doc": doc, "ok": ok,
                        "reason": reason}}


def compose(question, doc, max_sentences=3):
    """Extractive answer: the sentences from the evidence doc that best match."""
    q = set(tokens(question))
    sents = sentences(doc["text"])
    ranked = sorted(range(len(sents)), key=lambda i: -len(q & set(tokens(sents[i]))))
    keep = [i for i in ranked[:max_sentences] if q & set(tokens(sents[i]))] or ranked[:1]
    return " ".join(sents[i] for i in sorted(keep))


def answer_or_abstain_stage(c):
    s, label = c["support"], c["intent"]["label"]
    if s["ok"]:
        text = compose(c["question"], s["doc"])
        cites = [{"id": s["doc"]["id"], "title": s["doc"]["title"], "snippet": text}]
        return {"decision": "answer", "answer": text, "citations": cites}
    if label in REFUSALS:
        text = REFUSALS[label]
    elif label == intent_mod.OTHER:
        text = other_template(c["kb"])
    else:
        text = INSUFFICIENT
    return {"decision": "abstain", "answer": text, "citations": []}


STAGES = [
    Stage("LOAD_KB", ("kb_path",), ("kb", "index"), load_kb_stage),
    Stage("RETRIEVE", ("question", "index"), ("retrieved",), retrieve_stage),
    Stage("CLASSIFY_INTENT", ("question", "kb", "llm"), ("intent",),
          classify_intent_stage),
    Stage("CHECK_SUPPORT", ("question", "kb", "retrieved", "intent"), ("support",),
          check_support_stage),
    Stage("ANSWER_OR_ABSTAIN", ("question", "kb", "intent", "support"),
          ("decision", "answer", "citations"), answer_or_abstain_stage),
]


# ---- public API --------------------------------------------------------------------

def ask(question, kb_path=None, use_llm=True):
    llm = intent_mod.gemini_classifier() if use_llm else None
    ctx = run_pipeline(STAGES, {"question": question, "kb_path": kb_path, "llm": llm})
    return {
        "question": question,
        "decision": ctx["decision"],
        "answer": ctx["answer"],
        "citations": ctx["citations"],
        "debug": {
            "retrieved_ids": [h["doc"]["id"] for h in ctx["retrieved"]],
            "support_score": ctx["support"]["score"],
            "score_parts": ctx["support"]["parts"],
            "reason": ctx["support"]["reason"],
            "intent": ctx["intent"],
            "trace": ctx["trace"],
        },
    }


def main(argv=None):
    p = argparse.ArgumentParser(description="Grounded support-answer CLI")
    p.add_argument("question")
    p.add_argument("--kb", default=None, help="path to kb.json (default: KB_PATH or ./kb.json)")
    p.add_argument("--no-llm", action="store_true", help="rules only, never call Gemini")
    a = p.parse_args(argv)
    print(json.dumps(ask(a.question, a.kb, use_llm=not a.no_llm), indent=2))


if __name__ == "__main__":
    sys.exit(main())
