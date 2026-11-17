# Secure Enterprise Agentic RAG Platform

A permission-aware, evidence-grounded RAG system for company documents. It has two modules:

1. **RFP compliance.** Upload an RFP, and the system finds evidence in the company's own
   documents (only those the user may see), judges each requirement, and lets a human review every
   answer before a compliance matrix is exported.
2. **Question answering.** A chat (and a public, no-login page) that answers only from permitted
   documents and shows the exact quote behind every answer.

> Final-year B.Tech CSE capstone. All data is synthetic. Built at zero cost: local embeddings,
> Postgres in Docker, and the Gemini free tier.

## Design principles

- **Authorisation before retrieval.** Access rules run inside the search query, so unauthorised
  text never reaches the language model.
- **Default deny.** A document with no access rules is visible to nobody.
- **Evidence or silence.** The model must cite a quote, and code checks the quote really is in the
  excerpt. If it is not, the answer becomes "insufficient evidence" or "I could not find this".
  Missing evidence is never reported as non-compliance.
- **Human review before export.** The system's answer and the reviewer's decision are stored
  separately, and nothing is exported while any answer is waiting.
- **Append-only audit log** enforced by database triggers. It records who did what and why, and
  never any document text.

The reasons behind each choice, and their costs, are in [docs/DECISIONS.md](docs/DECISIONS.md).
What the system does not do is in [docs/LIMITATIONS.md](docs/LIMITATIONS.md).

## How it fits together

```
Streamlit screens ──HTTP──▶ FastAPI ──▶ policy + SQL permission filter ──▶ PostgreSQL + pgvector
 (ui/)                      (app/api)         (app/auth, app/retrieval)
                               │
                               ├─ RFP: parse → search per requirement → judge → verify → review → export
                               └─ Q&A: search → answer → verify quote and figures → save chat
                                          │
                                          └─ language model (Gemini free tier) and local embeddings
```

The screens only call the API. They never read the database or the documents, so a bug on a screen
cannot bypass a rule.

## Quick start

Prerequisites: Git, Docker Desktop, [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for
you). Optional: Tesseract, only for scanned documents.

```bash
git clone <this repository>
cd secure-rfp-platform

uv sync
cp .env.example .env
# Fill in .env: JWT_SECRET, SEED_USER_PASSWORD, and the LLM_* and EMBEDDING_MODEL values.

docker compose up -d
uv run alembic upgrade head
uv run python -m app.auth.seed                 # demo accounts (data/seed_users.yaml)
uv run python -m app.ingestion.load            # read the synthetic documents, chunk and store them with their access rules
uv run python -m app.retrieval.embed_chunks    # compute the embeddings
```

Run the API and the interface in two terminals:

```bash
uv run uvicorn app.api.main:app --reload
uv run streamlit run ui/app.py
```

Open http://localhost:8501. The API's own documentation is at http://127.0.0.1:8000/docs.

Demo accounts are listed in `data/seed_users.yaml`; they share the `SEED_USER_PASSWORD` from your
`.env`. Try `eng@meridian.test` (staff, can run RFPs), `auditor@meridian.test` (sees the audit
log) and `client@client.example` (outside person, public documents only). Anyone can also create
an account on the sign-in page; it starts with the lowest access.

## Using it

| You are                     | You can                                                                                                                                                           |
| --------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Staff (employee, executive) | Upload an RFP, watch progress, review each answer (approve, use another status, reject), export the CSV when nothing is waiting. Ask questions in the saved chat. |
| Any signed-in person        | Ask questions in the chat. Chats are saved and reloaded at your next sign-in.                                                                                     |
| Anyone, no account          | Ask the public page about public documents. Nothing is saved.                                                                                                     |
| Auditor                     | Read the audit log.                                                                                                                                               |

## Command-line tools

| Command                                                        | Purpose                                                          |
| -------------------------------------------------------------- | ---------------------------------------------------------------- |
| `python -m scripts.run_rfp --file F --as EMAIL`                | Run the judge over an RFP as one user and print the results.     |
| `python -m scripts.compare_run`                                | Score a saved run against the ground truth.                      |
| `python -m scripts.review_run`                                 | List, summarise, approve, edit, reject and export a run.         |
| `python -m scripts.eval_qa --file data/eval/qa_questions.yaml` | Score Q&A on independently written questions.                    |
| `python -m scripts.security_check --password PW`               | Attack the running API and print PASS or FAIL for each attack.   |
| `python -m scripts.find_chunks`, `check_corpus`, `check_llm`   | Inspect chunks, check the documents, check the model connection. |

## Tests and quality

```bash
bash scripts/dev.sh lint    # ruff style and static checks
bash scripts/dev.sh fmt     # auto-format
bash scripts/dev.sh test    # all tests
bash scripts/dev.sh check   # lint + format check + tests, the same as CI
```

Tests marked `integration` need the database container running. To run only the others:
`uv run pytest -m "not integration"`. CI builds the database from the migrations, then runs lint,
the format check and the tests.

## Results

| Measure                                           | Result                                                                                                     |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Automated tests (rebuilt from an empty database)  | 678 passed, 1 skipped                                                                                      |
| RFP-B (40 requirements), against the ground truth | 38 of 40 correct (95%), zero security violations. This is a development score: the rules were tuned on it. |
| RFP-A (29 requirements)                           | FILL IN from the final run                                                                                 |
| Q&A, independently written questions              | FILL IN from `scripts.eval_qa` (correct / total, security violations)                                      |
| Live attack check (`scripts.security_check`)      | All checks passed (FILL IN the count)                                                                      |

## Project layout

| Path                             | Purpose                                                                      |
| -------------------------------- | ---------------------------------------------------------------------------- |
| `app/auth`, `app/audit`          | Passwords, tokens, sign-up, the 12-rule policy, the audit log                |
| `app/models`, `migrations`       | Database models and Alembic migrations                                       |
| `app/ingestion`, `app/retrieval` | Reading and chunking documents, embeddings, permission-filtered search       |
| `app/rfp`                        | Parsing, judging, quote verification, run storage, review and export         |
| `app/qa`                         | Grounded answers, saved chats, public mode                                   |
| `app/llm`                        | The language model client                                                    |
| `app/api`                        | FastAPI app and routes                                                       |
| `ui`                             | Streamlit screens, the API client and helpers                                |
| `scripts`                        | Command-line tools listed above                                              |
| `data`                           | Synthetic company facts, demo users, manifest, RFPs and the Q&A question set |
| `tests`                          | Unit, integration and security tests                                         |
| `docs`                           | Decisions, limitations and the ground-truth notes                            |

## Data

All data is synthetic. The fictional vendor, Meridian Cloud Services, is defined in
`data/company_facts.yaml`, the source of truth for every document and every expected test answer.
It includes deliberate traps (an expired certificate, a partially met requirement, contradicted
and undocumented capabilities) so that correctness can be measured.

Do not load real or confidential documents: the free language-model tier may use prompts to
improve its models.

## Documentation

- [Design decisions](docs/DECISIONS.md)
- [Known limitations](docs/LIMITATIONS.md)
- [ADR 001: PostgreSQL with pgvector as the single data store](docs/decisions/001-postgres-pgvector.md)
- [Ground truth notes](docs/ground_truth.md)
