# SPEC: Grounded Support-Answer Service

Implementation spec for `BRIEF.md`. Goal: answer questions only from `kb.json`, cite the evidence, and abstain when the evidence does not support an answer.

## Scope and principles

- **Grounded by construction:** every answer sentence is copied verbatim from the cited passage.
- **Abstain over guess:** a false refusal is safer than a false answer for a support bot.
- **KB-agnostic:** no logic, thresholds or answers tied to the sample documents. A replacement `kb.json` with the same schema must work.
- **Zero-setup core:** Python 3.12 standard library only. Gemini is optional; with no key, the rule path runs alone.
- **Policy rules win:** legal, tax, trading and processing-guarantee questions get a fixed refusal and are never sent to Gemini.

## Interfaces

| Command | Purpose |
|---|---|
| `python app.py "question"` | CLI, prints response JSON (uses Gemini for intent if `GEMINI_API_KEY` is set) |
| `python app.py --no-llm "question"` | Rules only, never calls Gemini |
| `python -m unittest -v` | Tests (validation command) |
| `python eval.py` | Evaluation metrics (planned) |

KB path: `--kb PATH`, else `KB_PATH` env var, else `./kb.json`.

## Pipeline stages

Each stage declares what it reads and writes; the runner rejects undeclared reads or writes and records them in `debug.trace`.

| Stage | Reads | Writes |
|---|---|---|
| LOAD_KB | `kb_path` | `kb`, `index` (BM25) |
| NORMALIZE *(planned)* | `question`, `kb` | `normalized`, `corrections` |
| RETRIEVE | `question`, `index` | `retrieved` (top 3 docs + BM25) |
| CLASSIFY_INTENT | `question`, `kb`, `llm` | `intent` (label, source, restricted) |
| CHECK_SUPPORT | `question`, `kb`, `retrieved`, `intent` | `support` (score, parts, doc, ok, reason) |
| ANSWER_OR_ABSTAIN | `question`, `kb`, `intent`, `support` | `decision`, `answer`, `citations` |

**Intent:** labels are each KB doc id, `trading_advice`, `legal_advice`, `tax_advice`, `processing_guarantee`, `other`. Restricted keyword rules run first and win. Then a keyword-overlap rule picks the doc. Gemini is called only on no match or a tie, with output forced to the allowed labels. Without Gemini (or on an error or invalid label): no match gives `other`, a tie gives `ambiguous` (internal, abstains).

**Support check:** answer only if the intent is a doc that is in the retrieved set, every number in the question appears in that doc, and `support_score >= 0.60`.

```
support_score = 0.95 * (0.7 * coverage + 0.3 * margin) * strength
  coverage = share of question content tokens found in the evidence doc
  margin   = (best BM25 - second BM25) / best BM25   (1.0 if only one doc matched)
  strength = b / (b + 1), b = evidence doc's BM25    (always < 1, so score < 0.95)
```

**Answer:** up to 3 sentences from the evidence doc with the most question-token overlap, in article order. Citation snippet equals the answer.

**Abstain templates (fixed, never LLM-written):** a per-label refusal for the 4 restricted labels; `other` gets a friendly "I can help with questions about our products and your account, for example: <KB titles>" message; everything else gets "not enough information in our knowledge base, please contact support". `citations` is always empty.

## Typo handling (planned)

Measured on the current build: every typo question abstains (safe), but (1) real questions with typos are wrongly refused ("rest my pasword"), and (2) misspelled policy words ("suee", "guarentee", "taxs") skip the restricted rules and reach Gemini, breaking the policy rule.

**NORMALIZE stage**, before RETRIEVE, standard library only:
1. **Chat shorthand map:** `pls/plz -> please`, `u -> you`, `hrs -> hours`, `r -> are`, `thx -> thanks`.
2. **Fuzzy correction:** each word of 4+ letters not in the vocabulary is replaced by its closest vocabulary word (`difflib.get_close_matches`, cutoff 0.8). Vocabulary = all words in `kb.json` + restricted keyword lists + stopwords, so it follows a replacement KB.
3. **Restricted rules check the raw and the normalized question**, so a misspelled legal, tax, trading or guarantee question is still caught by the rule and never reaches Gemini.
4. **Confidence penalty:** `support_score *= (1 - 0.1 * corrected_share)`, so a guessed spelling lowers confidence.
5. The response keeps the original `question`; `debug.normalized` and `debug.corrections` show what changed.

Gibberish ("pls help sugagest what soc?") stays unmatched, so it gets the `other` template or a Gemini label, and abstains either way. Risks: a correct but unusual word can be "corrected" into a KB word; the evidence check still has to pass, so this can cause a refusal but not an ungrounded answer.

## Chunking

None. Each document is a short 3 to 4 sentence article, and splitting would separate a policy from its conditions. Sentences are used only to select answer snippets. Trade-off: long articles in a replacement KB would dilute retrieval scores.

## Acceptance criteria

| Case | Expected |
|---|---|
| "How do I reset my password?" | `answer`, cites doc_1 |
| The 3 brief examples (guarantee, tax, email) | `abstain`, no citations |
| "Can I sue you...?" | `abstain`, fixed legal refusal, Gemini not called |
| Off-topic ("weather") | `abstain`, `other` template |
| "How do I rest my pasword?" *(after NORMALIZE)* | `answer`, cites doc_1 |
| "can i suee you" *(after NORMALIZE)* | `legal_advice` by rule, Gemini not called |
| Every response | required keys; score in [0, 0.95); answers have at least 1 citation |
| Temporary replacement KB | answers from the new file's content |

## Known risks

Keyword coverage can refuse paraphrases that use synonyms not in the KB (for example "valid" vs "expires"). Accepted as the safer failure. With more time: embedding-based coverage, a Gemini answer mode restricted to the evidence passage.
