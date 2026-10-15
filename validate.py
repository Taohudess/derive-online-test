"""Validation: runs the real CLI in a fresh process and checks the brief's requirements.

Run: python validate.py
Uses --no-llm, so it needs no API key or network.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
TOP_KEYS = {"question", "decision", "answer", "citations", "debug"}
DEBUG_KEYS = {"retrieved_ids", "support_score"}
CITATION_KEYS = {"id", "title", "snippet"}

ANSWERABLE = ["How do I reset my password?",
              "How do I enable two-factor authentication?"]
UNSUPPORTED = ["Can you guarantee my withdrawal will finish in 2 hours?",
               "What tax advice do you provide for closed accounts?",
               "Can support change my email address for me?"]

results = []


def check(name, ok, detail=""):
    results.append(ok)
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))


def run_cli(question):
    out = subprocess.run([sys.executable, "app.py", "--no-llm", question],
                         cwd=HERE, capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def has_required_keys(r):
    return (TOP_KEYS <= set(r) and DEBUG_KEYS <= set(r["debug"])
            and r["decision"] in ("answer", "abstain")
            and all(CITATION_KEYS == set(c) for c in r["citations"]))


def main():
    with open(os.path.join(HERE, "kb.json"), encoding="utf-8") as f:
        kb = json.load(f)
    texts = {d["id"]: d["text"] for d in kb}

    r = run_cli(ANSWERABLE[0])
    stages = [t["stage"] for t in r["debug"]["trace"]]
    check("knowledge base loads", stages[0] == "LOAD_KB" and len(kb) > 0,
          f"{len(kb)} records from kb.json")

    for q in ANSWERABLE:
        r = run_cli(q)
        cited = r["citations"][0]["id"] if r["citations"] else None
        grounded = cited in texts and all(
            s.rstrip(".") in texts[cited] for s in r["answer"].split(". "))
        check(f"answerable returns citations: {q!r}",
              r["decision"] == "answer" and cited is not None and grounded,
              f"cites {cited}, score {r['debug']['support_score']}")

    for q in UNSUPPORTED:
        r = run_cli(q)
        check(f"unsupported abstains: {q!r}",
              r["decision"] == "abstain" and r["citations"] == [],
              r["debug"]["reason"])

    for q in ANSWERABLE[:1] + UNSUPPORTED[:1]:
        check(f"output JSON has required keys: {q!r}", has_required_keys(run_cli(q)))

    passed = sum(results)
    print(f"\n{passed}/{len(results)} checks passed")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
