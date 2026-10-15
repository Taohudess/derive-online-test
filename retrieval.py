"""RETRIEVE: BM25 over each document's title + text."""
import math
from collections import Counter

from textproc import tokens


class BM25Index:
    def __init__(self, kb, k1=1.5, b=0.75):
        self.kb = kb
        self.k1, self.b = k1, b
        self.docs = [Counter(tokens(d["title"] + " " + d["text"])) for d in kb]
        self.lens = [sum(c.values()) for c in self.docs]
        self.avg = sum(self.lens) / len(self.lens)
        df = Counter(t for c in self.docs for t in c)
        n = len(kb)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def score(self, i, q_tokens):
        c, s = self.docs[i], 0.0
        for t in set(q_tokens):
            if t in c:
                tf = c[t]
                s += self.idf[t] * tf * (self.k1 + 1) / (
                    tf + self.k1 * (1 - self.b + self.b * self.lens[i] / self.avg))
        return s

    def search(self, question, k=3):
        """Return [(doc, score)] for the top-k docs with score > 0."""
        q = tokens(question)
        scored = [(self.kb[i], self.score(i, q)) for i in range(len(self.kb))]
        scored = [x for x in scored if x[1] > 0]
        scored.sort(key=lambda x: -x[1])
        return scored[:k]
