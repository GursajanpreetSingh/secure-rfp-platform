# Known limitations

An honest list of what this project does not do yet. Items marked "planned" have a place in the
roadmap; the others are accepted for a capstone-scale system.

## Security

| Limitation                                         | Why it matters                                                                                                                                      | Status               |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- |
| No rate limiting or lockout on login               | Anyone can try many passwords, and every failed attempt adds a permanent audit row                                                                  | Planned              |
| The database owner can drop the audit triggers     | The append-only guarantee holds for the application and ordinary SQL, not for the database owner. Production would run the app as a restricted role | Documented hardening |
| Access tokens cannot be revoked individually       | A token stays valid until it expires. Disabling the account does stop it immediately, because the user is loaded from the database on every request | Accepted             |
| No registration, password reset or password change | Accounts exist only through the seed script                                                                                                         | Accepted             |
| One shared password for all demo accounts          | Acceptable for synthetic demo data, never for real accounts                                                                                         | Accepted             |
| HTTP only in development                           | Production would terminate TLS at a reverse proxy                                                                                                   | Documented hardening |
| `/health` is unauthenticated                       | Intended for monitoring. It reveals only up or down                                                                                                 | Accepted             |

## Correctness

| Limitation                                                         | Why it matters                                                   | Status                         |
| ------------------------------------------------------------------ | ---------------------------------------------------------------- | ------------------------------ |
| The access policy will exist twice (Python now, SQL for retrieval) | If the two ever disagree, there is a security bug                | A differential test is planned |
| Department matching is exact and case-sensitive                    | `Sales` and `sales` are different departments. This fails closed | Accepted                       |
| Only confidential documents check the department                   | Follows the classification table in the design                   | Accepted                       |

## Scope

| Limitation                                              | Status                                        |
| ------------------------------------------------------- | --------------------------------------------- |
| All data is synthetic, and the company is fictional     | By design                                     |
| Audit Intelligence and Contract Intelligence modules    | Future work                                   |
| Knowledge graph (Neo4j) and a dedicated vector database | Future work, only if experiments justify them |
| Scanned (image-only) documents and OCR                  | Later                                         |
