## BUILD

Build a small, runnable AI support-answer service that answers user questions from a local knowledge base and refuses to answer when it cannot support the answer with retrieved evidence.

This is a practical implementation task, not a slide deck. The evaluator will run your project from a clean checkout, may replace the input knowledge base with a different file using the same schema, and will check that answers are grounded in retrieved passages rather than generated freely.

Your system must:

- ingest a local FAQ-style knowledge base from disk
- retrieve relevant passages for a user question
- generate an answer only from retrieved context
- return citations to the supporting passages
- abstain with a clear fallback response when support is insufficient
- expose the functionality through a simple API or CLI

You may use any language or framework.

---

## INPUT FILE

Your app must read `kb.json` from disk.

Use this sample for local testing. The evaluator may replace it with equivalent data using the same schema.

### SAMPLE `kb.json`

```json
[
  {
    "id": "doc_1",
    "title": "Password reset",
    "text": "Users can reset their password from the login page by clicking 'Forgot password'. A reset link is sent to the registered email address. The link expires in 30 minutes. Support agents cannot manually view or send existing passwords."
  },
  {
    "id": "doc_2",
    "title": "Two-factor authentication",
    "text": "Two-factor authentication can be enabled from Security Settings. Supported methods are authenticator app and SMS. If a user loses access to their second factor, they must complete identity verification before 2FA can be removed."
  },
  {
    "id": "doc_3",
    "title": "Withdrawals review",
    "text": "Withdrawals may be placed into manual review for risk checks. Reviews usually complete within 24 hours but can take longer on weekends or holidays. Users should not submit duplicate withdrawal requests during review."
  },
  {
    "id": "doc_4",
    "title": "Account closure",
    "text": "Users can request account closure through support. Before closure, the account balance must be zero and all open positions must be closed. Closed accounts may be subject to record-retention requirements."
  },
  {
    "id": "doc_5",
    "title": "Address changes",
    "text": "Users can update their residential address from profile settings in supported regions. If the change affects verification status, the platform may request a new proof of address document."
  },
  {
    "id": "doc_6",
    "title": "Unsupported request types",
    "text": "Support answers should not provide legal advice, tax advice, or guarantees about processing times beyond what is stated in the knowledge base. When information is missing, the assistant should say it does not have enough information and direct the user to human support."
  }
]
```

---

## REQUIRED BEHAVIOUR

Implement a query flow with these stages:

```text
LOAD_KB
 -> RETRIEVE
 -> CHECK_SUPPORT
 -> ANSWER or ABSTAIN
```

The app must not generate a normal answer before retrieval has completed.

If retrieved evidence is weak or missing, the app must abstain instead of guessing.

---

## MUST COMPLETE

### 1. Knowledge Base Loading

Load `kb.json` from disk and prepare it for retrieval.

You may use:

- simple keyword matching
- embeddings
- TF-IDF / BM25
- any lightweight retrieval method

Your solution must work with replacement `kb.json` content using the same schema.

Do not hardcode answers to the sample questions.

---

### 2. Query Endpoint or CLI

Provide one runnable interface:

- an HTTP endpoint such as `POST /ask`
- or a CLI command such as `python app.py "question here"`

Input:

```json
{ "question": "string" }
```

Output must be structured JSON with this shape:

```json
{
  "question": "string",
  "decision": "answer | abstain",
  "answer": "string",
  "citations": [
    {
      "id": "string",
      "title": "string",
      "snippet": "string"
    }
  ],
  "debug": {
    "retrieved_ids": ["string"],
    "support_score": 0.0
  }
}
```

If the system abstains, `answer` should explain that there is not enough support in the knowledge base and suggest contacting support.

---

### 3. Citation-Grounded Answering

For answerable questions, return:

- a concise answer
- at least 1 citation
- citations that actually support the answer text

The answer must stay within the information in the retrieved passages.

Do not invent steps, timings, policies, or product behavior not found in the knowledge base.

---

### 4. Support Check and Abstention

Implement a support check in code before returning a final answer.

Your code must use a clear rule for deciding whether to answer or abstain.

Examples:

- minimum retrieval score threshold
- keyword overlap threshold
- answer must be supported by at least 1 retrieved passage
- top passages must agree on the same topic

Document your rule in `README.md`.

The evaluator will test both answerable and unanswerable questions.

Examples of questions that should likely abstain on the sample KB:

- "Can you guarantee my withdrawal will finish in 2 hours?"
- "What tax advice do you provide for closed accounts?"
- "Can support change my email address for me?"

---

### 5. Basic Tests

Include a small test file or validation script that checks at least these cases:

- an answerable question returns `decision: answer`
- an unsupported question returns `decision: abstain`
- citations are present for answered questions
- the app loads `kb.json` rather than embedded constants only

The test setup should be simple to run.

---

## SHOULD ATTEMPT

### 6. Swappable Answering Layer

Separate retrieval logic from answer generation so that the project can run in either of these modes:

- rule-based answer composition only
- LLM-backed answer composition

If you use an LLM, the system should still be able to run in a fallback non-LLM mode.

---

### 7. Chunking / Preprocessing Choice

If you split documents into chunks, explain the chunking choice and any tradeoff you made for short support articles.

---

## STRETCH

### 8. Small Evaluation Script

Add a script with 5 to 8 sample questions and expected decisions.

Report simple metrics such as:

- answer / abstain accuracy
- citation presence rate

This does not need to be fancy, but it should be runnable.

---

## REQUIRED ARTIFACTS

Your repository must contain:

- `kb.json`
- source code
- `README.md`
- tests or validation script

If your app writes generated files, include instructions for reproducing them.

---

## VALIDATION REQUIREMENTS

Include a run command and a validation command.

Examples:

```bash
python app.py "How do I reset my password?"
python validate.py
```

or

```bash
uvicorn app:app --reload
pytest
```

Your validation must check that:

- the knowledge base loads successfully
- at least one answerable query returns citations
- at least one unsupported query abstains
- output JSON follows the required keys

---

## EXECUTION REQUIREMENTS

The evaluator will run the project from a clean checkout.

The evaluator may replace `kb.json` with another file using the same schema.

Precomputed outputs alone are not sufficient.

The solution must actually read the file, perform retrieval, apply the support check, and produce grounded outputs.

---

## DELIVERABLE FORMAT

Submit a GitHub repository containing:

- source code
- setup instructions
- run command
- validation command
- sample `kb.json`
- any tests or evaluation scripts

Keep the implementation small, clear, and runnable within the time limit.

---

## TOOLS

Any programming language may be used.

Any open-source library may be used.

If you use a hosted LLM API, your project must also provide a non-API fallback path so the evaluator can still run the core retrieval and abstention flow without secrets.

---

## TECHNICAL CONSTRAINTS

- The system must read `kb.json` from disk.
- Retrieval must happen before answer generation.
- Answers must include citations.
- Unsupported questions must abstain.
- The implementation must work with replacement knowledge base files using the same schema.
- Hardcoded answers to sample questions are not acceptable.
