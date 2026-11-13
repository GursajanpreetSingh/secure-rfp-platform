# Secure RFP Compliance Platform

A permission-aware, evidence-grounded RAG system that analyses an RFP, finds supporting evidence in
company documents the user is authorised to see, drafts cited responses, and lets a human review
every answer before export.

> Status: Day 2 of 30 complete (foundation and security core). Synthetic data generation is in
> progress; ingestion, retrieval and the RFP workflow come next. This README describes what exists
> today.

## Design principles

- **Authorisation before retrieval.** Access rules are applied inside the search query, so
  unauthorised text never reaches the language model.
- **Default deny.** A document with no access rules is visible to nobody.
- **Honest compliance.** Missing evidence is reported as `insufficient_evidence`, never as
  non-compliance. Evidence that contradicts a requirement is `non_compliant`.
- **Append-only audit log.** Enforced by database triggers, not only by application code.
- **Everything is measured.** Retrieval accuracy and a security test suite are part of the project.

## What exists today

| Area                                                                                           | State       |
| ---------------------------------------------------------------------------------------------- | ----------- |
| Database: PostgreSQL 16 + pgvector in Docker                                                   | Done        |
| Models and migrations: users, documents, ACLs, chunks (vector + keyword indexes), audit events | Done        |
| Append-only audit log (database triggers)                                                      | Done        |
| FastAPI app with `/health`, `POST /auth/login` and `GET /auth/me`                              | Done        |
| Password hashing (Argon2id) and signed access tokens (JWT)                                     | Done        |
| Policy function: 12 ordered rules, tested against 30,000 random cases                          | Done        |
| Audit helper and login logging (no secrets, no typed emails)                                   | Done        |
| Source-of-truth data file (`data/company_facts.yaml`) and demo users                           | Done        |
| CI: lint, migrations from scratch, tests                                                       | Done        |
| Synthetic documents (14 files, 20+ pages each) and test RFPs                                   | In progress |
| Document ingestion, secure retrieval, RFP workflow, UI, evaluation                             | Planned     |

## Quick start

Prerequisites: Git, Docker Desktop, and [uv](https://docs.astral.sh/uv/) (it installs Python 3.12
for you).

```bash
git clone <this repository>
cd secure-rfp-platform

uv sync
cp .env.example .env
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')|" .env
sed -i "s|^SEED_USER_PASSWORD=.*|SEED_USER_PASSWORD=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(16))')|" .env

docker compose up -d
uv run alembic upgrade head
uv run python -m app.auth.seed
uv run uvicorn app.api.main:app --reload
```

Then open http://127.0.0.1:8000/health (expect `{"status":"ok","db":true}`) and
http://127.0.0.1:8000/docs for the interactive API documentation. The demo accounts are listed in
`data/seed_users.yaml`; their shared password is the `SEED_USER_PASSWORD` value in your `.env`.

## Development

```bash
bash scripts/dev.sh lint    # style and static checks
bash scripts/dev.sh fmt     # auto-format
bash scripts/dev.sh test    # run the tests
bash scripts/dev.sh check   # lint + tests, the same as CI
```

Tests marked `integration` need the database container running. Run only the others with
`uv run pytest -m "not integration"`.

## Project layout

| Path                                                            | Purpose                                                                      |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| `app/core`                                                      | Settings and database connection                                             |
| `app/models`                                                    | Database models                                                              |
| `app/auth`                                                      | Passwords, tokens, login, demo-user seeding, and the policy function         |
| `app/audit`                                                     | Audit event helper                                                           |
| `app/api`                                                       | FastAPI application and routes                                               |
| `app/ingestion`, `app/retrieval`, `app/workflows`, `app/export` | Reserved for upcoming modules                                                |
| `migrations`                                                    | Alembic database migrations                                                  |
| `data`                                                          | Synthetic company facts, demo users and, later, generated documents and RFPs |
| `tests`                                                         | Unit, integration and security tests                                         |
| `docs`                                                          | Architecture decision records and known limitations                          |

## Data

All data is synthetic. The fictional vendor, Meridian Cloud Services, is defined in
`data/company_facts.yaml`, which is the source of truth for every generated document and every
expected test answer. It includes deliberate traps (an expired certificate, a partially met
requirement, contradicted and undocumented capabilities) so that correctness can be measured.

## Documentation

- [ADR 001: PostgreSQL with pgvector as the single data store](docs/decisions/001-postgres-pgvector.md)
- [Known limitations](docs/known-limitations.md)
