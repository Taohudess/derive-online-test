"""Small evaluation: 8 questions with expected decisions on the sample kb.json.

Run: python eval.py            (rules only, deterministic)
     python eval.py --llm      (Gemini breaks intent ties if GEMINI_API_KEY is set)
"""
import argparse
import sys

from app import ask

# (question, expected decision, expected cited doc id or None)
CASES = [
    ("How do I reset my password?", "answer", "doc_1"),
    ("How long does a withdrawal review take?", "answer", "doc_3"),
    ("What do I need before closing my account?", "answer", "doc_4"),
    ("how to enabel two factr authentcation", "answer", "doc_2"),       # typos
    ("Can you guarantee my withdrawal will finish in 2 hours?", "abstain", None),
    ("What tax advice do you provide for closed accounts?", "abstain", None),
    ("Can support change my email address for me?", "abstain", None),
    ("can i suee you for this", "abstain", None),                       # legal, typo
]


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--llm", action="store_true")
    a = p.parse_args(argv)

    correct = cited_ok = answered = with_citation = 0
    print(f"{'question':58} {'expected':8} {'got':8} {'score':>6}  cited")
    for q, want, want_doc in CASES:
        r = ask(q, use_llm=a.llm)
        got, cites = r["decision"], [c["id"] for c in r["citations"]]
        ok = got == want and (want_doc is None or cites[:1] == [want_doc])
        correct += got == want
        cited_ok += ok
        if got == "answer":
            answered += 1
            with_citation += bool(cites)
        mark = "ok " if ok else "XX "
        print(f"{mark}{q[:55]:55} {want:8} {got:8} {r['debug']['support_score']:>6}  "
              f"{','.join(cites) or '-'}")

    n = len(CASES)
    print(f"\nanswer/abstain accuracy : {correct}/{n} = {correct / n:.0%}")
    print(f"decision + right citation: {cited_ok}/{n} = {cited_ok / n:.0%}")
    rate = with_citation / answered if answered else 0.0
    print(f"citation presence rate  : {with_citation}/{answered} answered = {rate:.0%}")
    return 0 if correct == n else 1


if __name__ == "__main__":
    sys.exit(main())
