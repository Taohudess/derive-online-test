"""Tests at the agreed seams: ask() end to end, and intent.classify().

Run: python -m unittest -v
"""
import json
import os
import tempfile
import unittest

from app import ask
from intent import classify

HERE = os.path.dirname(os.path.abspath(__file__))
REQUIRED_KEYS = {"question", "decision", "answer", "citations", "debug"}


def ask_rules(question, kb_path=None):
    """Gemini off so results are deterministic and need no API key."""
    return ask(question, kb_path=kb_path, use_llm=False)


class AskAnswers(unittest.TestCase):
    def test_how_long_question_is_answered_from_the_kb(self):
        r = ask_rules("How long is the password reset link valid?")
        self.assertEqual(r["decision"], "answer")
        self.assertEqual([c["id"] for c in r["citations"]], ["doc_1"])
        self.assertIn("30 minutes", r["answer"])

    def test_answerable_questions_answer_with_grounded_citations(self):
        with open(os.path.join(HERE, "kb.json")) as f:
            texts = {d["id"]: d["text"] for d in json.load(f)}
        for q, doc_id in [("How do I reset my password?", "doc_1"),
                          ("How do I enable two-factor authentication?", "doc_2"),
                          ("What do I need before closing my account?", "doc_4")]:
            with self.subTest(q=q):
                r = ask_rules(q)
                self.assertEqual(r["decision"], "answer")
                self.assertEqual(r["citations"][0]["id"], doc_id)
                # every answer sentence is verbatim from the cited article
                self.assertEqual(r["answer"], r["citations"][0]["snippet"])
                for sent in r["answer"].split(". "):
                    self.assertIn(sent.rstrip("."), texts[doc_id])

    def test_response_has_required_shape(self):
        for q in ["How do I reset my password?", "What is the weather today?"]:
            with self.subTest(q=q):
                r = ask_rules(q)
                self.assertTrue(REQUIRED_KEYS <= set(r))
                self.assertIn(r["decision"], ("answer", "abstain"))
                self.assertIsInstance(r["debug"]["retrieved_ids"], list)
                self.assertIsInstance(r["debug"]["support_score"], float)
                for c in r["citations"]:
                    self.assertEqual(set(c), {"id", "title", "snippet"})

    def test_support_score_varies_and_stays_below_cap(self):
        scores = [ask_rules(q)["debug"]["support_score"] for q in [
            "How do I reset my password?",
            "How do I enable two-factor authentication?",
            "What do I need before closing my account?",
            "How can I update my address?"]]
        self.assertTrue(all(0.0 < s < 0.95 for s in scores), scores)
        self.assertEqual(len(set(scores)), len(scores), scores)


class AskAbstains(unittest.TestCase):
    def test_brief_examples_abstain_without_citations(self):
        for q in ["Can you guarantee my withdrawal will finish in 2 hours?",
                  "What tax advice do you provide for closed accounts?",
                  "Can support change my email address for me?"]:
            with self.subTest(q=q):
                r = ask_rules(q)
                self.assertEqual(r["decision"], "abstain")
                self.assertEqual(r["citations"], [])
                self.assertIn("support", r["answer"].lower())

    def test_legal_question_gets_fixed_refusal(self):
        r = ask_rules("Can I sue you for a delayed withdrawal?")
        self.assertEqual(r["decision"], "abstain")
        self.assertIn("not able to give legal advice", r["answer"])

    def test_off_topic_question_gets_other_template(self):
        r = ask_rules("What is the weather today?")
        self.assertEqual(r["decision"], "abstain")
        self.assertEqual(r["debug"]["intent"]["label"], "other")
        self.assertIn("our products and your account", r["answer"])


class AskReadsKbFromDisk(unittest.TestCase):
    def test_replacement_kb_is_used(self):
        kb = [{"id": "x1", "title": "Deposit limits",
               "text": "The daily deposit limit is 5000 USD. Limits reset at midnight UTC."},
              {"id": "x2", "title": "Trading hours",
               "text": "Forex markets are open from Monday to Friday."}]
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "kb.json")
            with open(path, "w") as f:
                json.dump(kb, f)
            r = ask_rules("What is the daily deposit limit?", kb_path=path)
            self.assertEqual(r["decision"], "answer")
            self.assertEqual(r["citations"][0]["id"], "x1")
            self.assertIn("5000 USD", r["answer"])
            # a sample-KB question has no support in the replacement KB
            r = ask_rules("How do I enable two-factor authentication?", kb_path=path)
            self.assertEqual(r["decision"], "abstain")


KB = [{"id": "a", "title": "Password reset", "text": "Reset your password from the login page."},
      {"id": "b", "title": "Email change", "text": "Update your email from profile settings."},
      {"id": "c", "title": "Address change", "text": "Update your address from profile settings."}]


class FakeGemini:
    """Stands in for the external Gemini API; records every call."""
    def __init__(self, reply="other", error=None):
        self.reply, self.error, self.calls = reply, error, []

    def __call__(self, question, kb, labels):
        self.calls.append({"question": question, "labels": labels})
        if self.error:
            raise self.error
        return self.reply


class ClassifyIntent(unittest.TestCase):
    def test_restricted_questions_never_reach_gemini(self):
        for q, label in [("Can I sue you over this?", "legal_advice"),
                         ("Is my lawyer allowed to see my password reset?", "legal_advice"),
                         ("Do I pay tax on withdrawals?", "tax_advice"),
                         ("Should I buy gold now?", "trading_advice"),
                         ("Can you guarantee my reset will finish in 5 minutes?",
                          "processing_guarantee")]:
            with self.subTest(q=q):
                g = FakeGemini(reply="a")
                r = classify(q, KB, llm=g)
                self.assertEqual((r.label, r.source, r.restricted), (label, "rule", True))
                self.assertEqual(g.calls, [])

    def test_clear_keyword_match_skips_gemini(self):
        g = FakeGemini(reply="b")
        r = classify("How do I reset my password?", KB, llm=g)
        self.assertEqual((r.label, r.source), ("a", "rule"))
        self.assertEqual(g.calls, [])

    def test_no_match_asks_gemini_with_allowed_labels_only(self):
        g = FakeGemini(reply="other")
        r = classify("What is the weather like?", KB, llm=g)
        self.assertEqual((r.label, r.source), ("other", "gemini"))
        self.assertEqual(len(g.calls), 1)
        self.assertEqual(g.calls[0]["labels"],
                         ["a", "b", "c", "trading_advice", "legal_advice",
                          "tax_advice", "processing_guarantee", "other"])

    def test_tie_asks_gemini(self):
        g = FakeGemini(reply="b")
        r = classify("Can I update it from profile settings?", KB, llm=g)  # b and c tie
        self.assertEqual((r.label, r.source), ("b", "gemini"))
        self.assertEqual(len(g.calls), 1)

    def test_gemini_failure_or_bad_label_falls_back(self):
        cases = [("What is the weather like?", FakeGemini(reply="refund_policy"), "other"),
                 ("What is the weather like?", FakeGemini(error=TimeoutError()), "other"),
                 ("Can I update it from profile settings?", FakeGemini(reply="??"), "ambiguous"),
                 ("Can I update it from profile settings?", None, "ambiguous")]
        for q, g, label in cases:
            with self.subTest(q=q, label=label):
                r = classify(q, KB, llm=g)
                self.assertEqual((r.label, r.source), (label, "fallback"))


if __name__ == "__main__":
    unittest.main()
