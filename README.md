# Grounded Support-Answer Service

A small support bot that answers questions **only** from a local `kb.json`, cites the passage it used, and **abstains** when the knowledge base does not support an answer. The brief is in `BRIEF.md` and the design spec is in `SPEC.md`.

## Setup

Requires Python 3.10+ (tested on 3.12) and nothing else. The core uses only the standard library, so there is no `pip install` step.

```bash
git clone https://github.com/Taohudess/derive-online-test.git
cd derive-online-test
```

Optional: put `GEMINI_API_KEY=...` in a `.env` file (gitignored) to let Gemini break intent ties. Without it, everything runs on rules alone. `GEMINI_MODEL` overrides the default model (`gemini-3.8-flash`).

## Run

```bash
python app.py "How do I reset my password?"            # uses Gemini for intent ties if a key is set
python app.py --no-llm "How do I reset my password?"   # rules only, no network
python app.py --kb path/to/other_kb.json "question"    # or set KB_PATH
```

The KB path defaults to `./kb.json`. Any file with the same schema (a list of `{id, title, text}`) works.

## Validate

```bash
python validate.py        # runs the real CLI in a fresh process: 8 checks
python -m unittest -v     # 13 tests: ask() end to end + intent classification
```

Both need no API key or network. `validate.py` checks that the KB loads, answerable questions return grounded citations, the brief's three unsupported questions abstain, and the output JSON has the required keys. The unit tests also prove a **replacement `kb.json`** is read from disk and used.

## Example output

```json
{
  "question": "How do I reset my password?",
  "decision": "answer",
  "answer": "Users can reset their password from the login page by clicking 'Forgot password'. A reset link is sent to the registered email address. Support agents cannot manually view or send existing passwords.",
  "citations": [{ "id": "doc_1", "title": "Password reset", "snippet": "Users can reset their password ..." }],
  "debug": {
    "retrieved_ids": ["doc_1"],
    "support_score": 0.797,
    "score_parts": { "coverage": 1.0, "margin": 1.0, "strength": 0.839, "bm25": 5.2 },
    "reason": "supported",
    "intent": { "label": "doc_1", "source": "rule", "restricted": false },
    "trace": ["... one entry per stage: name, reads, writes ..."]
  }
}
```

## How it works

```
LOAD_KB -> RETRIEVE -> CLASSIFY_INTENT -> CHECK_SUPPORT -> ANSWER_OR_ABSTAIN
```

Each stage declares what it reads and writes. The runner (`run_pipeline` in `app.py`) rejects a stage that reads a missing key or writes an undeclared one, and records every stage in `debug.trace`. No answer text is produced before RETRIEVE and CHECK_SUPPORT have run.

| Stage | Reads | Writes | File |
|---|---|---|---|
| LOAD_KB | `kb_path` | `kb`, `index` | `kb.py`, `retrieval.py` |
| RETRIEVE | `question`, `index` | `retrieved` (top 3 + BM25) | `retrieval.py` |
| CLASSIFY_INTENT | `question`, `kb`, `llm` | `intent` | `intent.py` |
| CHECK_SUPPORT | `question`, `kb`, `retrieved`, `intent` | `support` | `app.py` |
| ANSWER_OR_ABSTAIN | `question`, `kb`, `intent`, `support` | `decision`, `answer`, `citations` | `app.py`, `templates.py` |

**Retrieval:** BM25 over each article's title and text, with stopword removal and light suffix stemming (`closing`, `closure` and `closed` all match).

**Intent classification:** labels are one per KB doc id (built from `kb.json`), plus `legal_advice`, `tax_advice`, `trading_advice`, `processing_guarantee` and `other`.
1. **Restricted keyword rules run first and always win.** These questions get a fixed refusal and are never sent to Gemini.
2. A keyword-overlap rule picks the doc with the most matching question words.
3. **Gemini is called only when no doc matches or the top docs tie.** Its output is forced to the allowed labels (enum response schema).
4. Without Gemini, or on an error or an invalid label: no match gives `other`, a tie gives `ambiguous`. Both abstain.

## Support rule (answer vs abstain)

The service answers **only if all of these hold**, otherwise it abstains:

1. The intent is a KB document (not restricted, `other` or `ambiguous`).
2. That document is in the retrieved top 3 (intent and retrieval agree).
3. Every number in the question appears in that document. This blocks "guarantee it in **2** hours" when the KB says "24 hours".
4. `support_score >= 0.60`, where

```
support_score = 0.95 * (0.7 * coverage + 0.3 * margin) * strength
  coverage = share of the question's content words found in the evidence doc
  margin   = (best BM25 - second BM25) / best BM25   (1.0 if only one doc matched)
  strength = b / (b + 1), b = the evidence doc's BM25
```

`strength` is always below 1, so the score always stays below 0.95, and it differs by question (0.649 to 0.85 on the sample answerable questions). Coverage is measured against **one** document, so an answer can never be stitched together from two unrelated articles.

**Answers** are extractive: up to 3 sentences from the evidence document with the most question-word overlap, kept in article order. Every answer sentence is copied word for word, so the citation supports the answer by construction.

**Abstentions** use fixed templates (`templates.py`), never LLM text: a polite refusal for each restricted topic, a friendly "here's what I can help with" message for off-topic questions (topics listed from `kb.json`), and "not enough information, please contact our support team" for everything else.

## Chunking choice

No chunking. Each sample article is 3 to 4 sentences, and splitting would separate a policy from its conditions (for example "the link expires in 30 minutes" from the reset article). Sentences are used only to pick the answer snippet. Trade-off: very long articles in a replacement KB would dilute BM25 scores and coverage. Paragraph-level chunks would be the next step for those.

## Trade-offs and limitations

- **False refusals over false answers.** Keyword coverage can refuse a paraphrase that uses words not in the KB (for example "valid" vs "expires"). For a support bot that is the safer failure.
- **Typos.** Misspelled questions currently abstain, which is safe but unhelpful, and a misspelled policy word ("suee", "guarentee") can skip the restricted rules and reach Gemini. `SPEC.md` describes the planned fix: a NORMALIZE stage with fuzzy correction against the KB vocabulary, with restricted rules checking both the raw and corrected text.
- **Restricted keyword lists** are hand-written policy, not learned. They are deliberately broad, since a wrong refusal is cheap.
- **Gemini is used only for intent.** It never writes answer text and never makes the final answer/abstain decision.

## Project layout

| File | Purpose |
|---|---|
| `kb.json` | Sample knowledge base from the brief |
| `app.py` | Pipeline runner, stages, support check, CLI |
| `kb.py` | Loads and validates `kb.json` |
| `retrieval.py` | BM25 index |
| `intent.py` | Intent rules and the optional Gemini classifier |
| `templates.py` | Fixed refusal and abstain messages |
| `textproc.py` | Tokenising, stemming, sentence splitting |
| `validate.py` | Validation script (CLI, fresh process) |
| `test_app.py` | Unit tests |
