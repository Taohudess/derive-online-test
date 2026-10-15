"""Intent classification: keyword rules first, Gemini only on no match or a tie.

Labels:
  - one per KB document id (built from kb.json, so a replacement KB works)
  - restricted: trading_advice, legal_advice, tax_advice, processing_guarantee
  - other (not related to any KB topic)
Restricted rules always win: if one matches, Gemini is never called.
"""
import json
import os
import urllib.request
from dataclasses import dataclass, field

from normalize import build_vocab, normalize
from textproc import stem, tokens, words

RESTRICTED = ("trading_advice", "legal_advice", "tax_advice", "processing_guarantee")
OTHER = "other"
AMBIGUOUS = "ambiguous"   # internal only, never offered to Gemini

# Restricted-topic policy keywords (raw lowercase words and phrases).
_TAX_WORDS = {"tax", "taxes", "taxed", "taxable", "taxation", "irs", "vat"}
_LEGAL_WORDS = {"legal", "legally", "illegal", "lawyer", "attorney", "lawsuit",
                "sue", "sued", "suing", "law", "laws", "lawful", "unlawful", "liable",
                "liability", "court", "solicitor", "litigation", "legislation",
                "jurisdiction", "contract", "contracts"}
_TRADING_WORDS = {"invest", "investing", "investment", "investments", "forecast",
                  "predict", "prediction", "profitable", "profit", "profits"}
_TRADING_PHRASES = ("should i buy", "should i sell", "should i trade",
                    "should i invest", "what should i trade", "which asset",
                    "trading advice", "trading strategy", "trading tips",
                    "financial advice", "investment advice", "price target")
_GUARANTEE_WORDS = {"guarantee", "guaranteed", "guarantees", "promise", "promised",
                    "assure", "ensure", "certain", "definitely"}
_TIME_WORDS = {"hour", "hours", "minute", "minutes", "day", "days", "week", "weeks",
               "time", "times", "when", "soon", "fast", "quickly", "finish",
               "finished", "complete", "completed", "processed", "processing",
               "today", "tomorrow", "by"}

# Every policy word, so NORMALIZE can correct "suee" -> "sue", "guarentee" -> "guarantee".
POLICY_WORDS = (_TAX_WORDS | _LEGAL_WORDS | _TRADING_WORDS | _GUARANTEE_WORDS
                | _TIME_WORDS | {w for p in _TRADING_PHRASES for w in p.split()})


@dataclass
class IntentResult:
    label: str
    source: str                      # "rule" | "gemini" | "fallback"
    restricted: bool
    scores: dict = field(default_factory=dict)


def _stems(ws):
    return {stem(w) for w in ws}


def restricted_label(question):
    """Return a restricted label if a policy keyword matches, else None.
    Matches raw words or stems, so "taxs", "suee" and "lawyers" still hit."""
    text = " ".join(words(question))
    ws = set(text.split())
    st = _stems(ws)

    def hit(vocab):
        return bool(ws & vocab or st & _stems(vocab))

    if hit(_LEGAL_WORDS):
        return "legal_advice"
    if hit(_TAX_WORDS):
        return "tax_advice"
    if hit(_TRADING_WORDS) or any(p in text for p in _TRADING_PHRASES):
        return "trading_advice"
    if hit(_GUARANTEE_WORDS) and (hit(_TIME_WORDS) or any(w.isdigit() for w in ws)):
        return "processing_guarantee"
    return None


def doc_scores(question, kb):
    """Keyword rule: count distinct question tokens found in each doc's title+text."""
    q = set(tokens(question))
    return {d["id"]: len(q & set(tokens(d["title"] + " " + d["text"]))) for d in kb}


def allowed_labels(kb):
    return [d["id"] for d in kb] + list(RESTRICTED) + [OTHER]


def classify(question, kb, llm=None):
    """Keyword rules first. Gemini only on no match or a tie.

    llm: callable(question, kb, labels) -> label, or None to skip Gemini.
    """
    norm, _ = normalize(question, build_vocab(kb, POLICY_WORDS))
    r = restricted_label(question) or restricted_label(norm)
    if r:  # rule wins, even when misspelled; never reaches Gemini
        return IntentResult(r, "rule", True)

    scores = doc_scores(norm, kb)
    top = max(scores.values())
    tied = [i for i, v in scores.items() if v == top and top > 0]
    if len(tied) == 1:
        return IntentResult(tied[0], "rule", False, scores)

    labels = allowed_labels(kb)
    label = None
    if llm is not None:
        try:
            label = llm(question, kb, labels)
        except Exception:
            label = None
    if label in labels:
        return IntentResult(label, "gemini", label in RESTRICTED, scores)

    # Gemini unavailable or invalid: tie -> ambiguous (abstain), no match -> other.
    # Picking one tied doc blindly could answer from the wrong article.
    if tied:
        return IntentResult(AMBIGUOUS, "fallback", False, scores)
    return IntentResult(OTHER, "fallback", False, scores)


# ---- Gemini (optional) -------------------------------------------------------

def _load_dotenv(path=".env"):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def gemini_classifier():
    """Return a Gemini-backed classifier, or None if no API key is configured."""
    _load_dotenv()
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    model = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
           f"{model}:generateContent")

    def call(question, kb, labels):
        topics = "\n".join(f"- {d['id']}: {d['title']}" for d in kb)
        prompt = (
            "Classify the user's support question into exactly one label.\n"
            f"Knowledge base topics:\n{topics}\n"
            "Restricted labels: trading_advice, legal_advice, tax_advice, "
            "processing_guarantee (asks for a guarantee about timing).\n"
            "Use 'other' if the question is not related to any topic.\n"
            f"Question: {question}"
        )
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "text/x.enum",
                "responseSchema": {"type": "STRING", "enum": labels},
            },
        }
        req = urllib.request.Request(
            url, data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json", "x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=10) as resp:
            out = json.load(resp)
        return out["candidates"][0]["content"]["parts"][0]["text"].strip()

    return call
