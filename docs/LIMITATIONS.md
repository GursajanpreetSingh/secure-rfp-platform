# Known limitations

Written down on purpose. None of these is hidden in the code.

## Data and privacy

- All documents are synthetic. The Gemini free tier may use prompts to improve its models, so
  real or confidential documents must not be used with it.
- No email verification at sign-up. Anyone can create an `external` account with any address.
  The account can only read public documents.
- Saved Q&A answers keep their quotes in the database. They are re-checked when a chat is
  reopened and at export, but the stored text itself is not erased when access is revoked.

## Answer quality

- A correct answer is sometimes rejected: a quote that spans table cells fails strict
  verification (requirement B-006), and the answer becomes "insufficient evidence".
- The negative-signal rule is a heuristic (a list of negative words, or a figure).
- The ground-truth label for B-039 is debatable.
- The RFP score was developed against the ground truth, so it is a development score and not an
  independent test. The Q&A questions were written separately.
- The model can still be wrong in ways code cannot check, for example a true quote that does not
  really answer the requirement. That is the reason for the human review step.
- Questions that contain a wrong figure depend on the model following one prompt rule. If it
  does not, the answer is withheld rather than shown wrong.

## Search

- The HNSW vector index can return fewer results when a permission filter removes many
  candidates (filtered approximate search).
- Scanned documents depend on OCR (Tesseract) quality.

## Operations

- The free model tier is rate limited and sometimes busy. Runs stop after three consecutive model
  failures and the remaining answers are marked "not judged".
- Background runs use the API process. A restart during a run leaves it marked as running until it
  is considered stale.
- Integration tests are slow because they use a real database.
- Public Q&A has one shared hourly limit, so a single visitor can use it up.
- Single server, no load testing, no backups, no HTTPS configuration. This is a prototype.

## Carried over from the early design

- No rate limiting or lockout on sign-in. Every failed attempt adds a permanent audit row.
- The database owner can drop the audit triggers. The append-only guarantee holds for the
  application and ordinary SQL; production would run the app as a restricted role.
- Access tokens cannot be revoked one by one. They expire on their own, but switching an account
  off stops it at once, because the user is loaded from the database on every request.
- There is no password reset or password change. All demo accounts share one password.
- HTTP only in development. Production would terminate TLS at a reverse proxy.
- `/health` is unauthenticated, by design. It reveals only up or down.
- The access policy exists twice (Python for decisions, SQL for search). If the two ever
  disagreed it would be a security bug.
- Department matching is exact and case-sensitive. This fails closed.
- Audit Intelligence and Contract Intelligence modules, a knowledge graph and a dedicated vector
  database are future work.
