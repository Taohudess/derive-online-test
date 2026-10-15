"""NORMALIZE: expand chat shorthand and fix typos against a known vocabulary.

The vocabulary is built from kb.json (plus policy keywords and stopwords), so a
misspelling can only be corrected towards a word the system already knows.
"""
import difflib

from textproc import STOPWORDS, stem, words

SHORTHAND = {"pls": "please", "plz": "please", "u": "you", "ur": "your", "r": "are",
             "hr": "hour", "hrs": "hours", "min": "minute", "mins": "minutes",
             "thx": "thanks", "acc": "account", "acct": "account",
             "pw": "password", "pwd": "password"}
MIN_LEN = 4       # shorter words are too ambiguous to correct
CUTOFF = 0.8      # difflib similarity needed to accept a correction


def build_vocab(kb, extra=()):
    vocab = set(STOPWORDS) | set(SHORTHAND.values()) | set(extra)
    for d in kb:
        vocab.update(words(d["title"] + " " + d["text"]))
    return sorted(vocab)


def normalize(text, vocab):
    """Return (normalized_text, corrections). corrections maps typo -> fix and
    excludes shorthand, which is an expansion rather than a guess."""
    known = set(vocab)
    known_stems = {stem(v) for v in vocab}   # "long" is fine if "longer" is known
    out, corrections = [], {}
    for w in words(text):
        if w in SHORTHAND:
            w = SHORTHAND[w]
        elif (w not in known and stem(w) not in known_stems
              and len(w) >= MIN_LEN and not w.isdigit()):
            match = difflib.get_close_matches(w, vocab, n=1, cutoff=CUTOFF)
            if match:
                corrections[w] = match[0]
                w = match[0]
        out.append(w)
    return " ".join(out), corrections
