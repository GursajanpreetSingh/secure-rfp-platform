# Secure RFP Compliance Platform

A permission-aware, evidence-grounded RAG system that analyses an RFP, finds supporting evidence in
company documents the user is authorised to see, drafts cited responses, and lets a human review
every answer before export.

> Status: Day 1 of 30 complete (foundation). The ingestion, retrieval and RFP workflow are being
> built next. This README describes what exists today.

## Design principles

- **Authorisation before retrieval.** Access rules are applied inside the search query, so
  unauthorised text never reaches the language model.
- **Default deny.** A document with no access rules is visible to nobody.
- **Honest compliance.** Missing evidence is reported as `insufficient_evidence`, never as
  non-compliance. Evidence that contradicts a requirement is `non_compliant`.
- **Append-only audit log.** Enforced by database triggers, not only by application code.
- **Everything is measured.** Retrieval accuracy and a security test suite are part of the project.

## What exists today

| Area | State |
|---|---|
| Database: PostgreSQL 16 + pgvector in Docker | Done |
| Models and migrations: users, documents, ACLs, chunks (vector + keyword indexes), audit events | Done |
| Append-only audit log (database triggers) | Done |
| FastAPI app with `/health` endpoint | Done |
| Source-of-truth data file (`data/company_facts.yaml`) and its validation tests | Done |
| CI: lint, migrations from scratch, tests | Done |
| Authentication and policy function | Next (Day 2) |
| Document ingestion, secure retrieval, RFP workflow, UI, evaluation | Planned |

## Quick start

Prerequisites: Git, Docker Desktop, and [uv](https://docs.astral.sh/uv/) (it installs Python 3.12
for you).

```bash
git clone <this repository>
cd secure-rfp-platform

uv sync
cp .env.example .env
sed -i "s|^JWT_SECRET=.*|JWT_SECRET=$(uv run python -c 'import secrets; print(secrets.token_urlsafe(48))')|" .env

docker compose up -d
uv run alembic upgrade head
uv run uvicorn app.api.main:app --reload
```

Then open http://127.0.0.1:8000/health (expect `{"status":"ok","db":true}`) and
http://127.0.0.1:8000/docs for the interactive API documentation.

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

| Path | Purpose |
|---|---|
| `app/core` | Settings and database connection |
| `app/models` | Database models |
| `app/api` | FastAPI application |
| `app/auth`, `app/ingestion`, `app/retrieval`, `app/workflows`, `app/audit`, `app/export` | Reserved for upcoming modules |
| `migrations` | Alembic database migrations |
| `data` | Synthetic company facts and, later, generated documents and RFPs |
| `tests` | Unit, integration and security tests |
| `docs/decisions` | Architecture decision records |

## Data

All data is synthetic. The fictional vendor, Meridian Cloud Services, is defined in
`data/company_facts.yaml`, which is the source of truth for every generated document and every
expected test answer. It includes deliberate traps (an expired certificate, a partially met
requirement, contradicted and undocumented capabilities) so that correctness can be measured.

## Documentation

- [ADR 001: PostgreSQL with pgvector as the single data store](docs/decisions/001-postgres-pgvector.md)
