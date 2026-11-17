# Design decisions

Each entry says what was chosen, why, and what it costs. The aim of the whole system is that it
would rather say "I do not know" than say something it cannot back up.

## 1. Permissions are enforced in the database query, not after

Search only ever sees chunks the person may read. The check (role, clearance, department,
purpose, expiry, explicit allow lists) is part of the SQL, so a document a person may not see
never reaches the model, the screen or the audit detail.
*Cost:* the vector index (HNSW) can return fewer results when a filter removes many candidates.

## 2. Twelve explicit rules in one function, `decide()`

Access is decided by a short list of rules in one place, each with a reason code that is written
to the audit log. Deny wins. A purpose (RFP, enterprise Q&A) is part of the question, so a
document can be allowed for one use and not the other.

## 3. Evidence or silence: quotes are verified in code

The model must cite an excerpt and copy a quote from it word for word. Code checks that the quote
really is in the excerpt (only case, spacing and dash differences are forgiven). If the check
fails, the answer is replaced by "insufficient evidence" or "I could not find this".
Missing evidence is never reported as `non_compliant`.
*Cost:* a correct answer is sometimes rejected, for example when a quote crosses table cells.
That is the chosen direction of error.

## 4. A "not compliant" needs a negative signal in the quote

`non_compliant` is only kept if the cited quote contains a negative word or a figure. Otherwise it
becomes `unsupported_negative` and goes to a human. Silence in the documents is not a "no".
*Cost:* a heuristic. A negative stated without those words is downgraded.

## 5. Every figure in a Q&A answer must appear in the cited text

If the answer contains a number that the quoted excerpts do not contain, it is thrown away. When a
question holds a wrong figure, the prompt tells the model to state the documented value instead
of repeating the wrong one. The guard was not loosened to allow the question's own number,
because that would let "Yes, 50%" pass.

## 6. Documents, questions and chat history are data, never instructions

Everything untrusted is wrapped in tags, closing tags inside it are neutralised, and the prompt
says to ignore instructions found there. Suspicious text in an uploaded RFP is audited and kept
out of the run. Output is shown as plain text, so nothing a document says can become HTML or a link.

## 7. A human reviews before anything leaves

The system's answer and the reviewer's decision are stored separately. Approve, edit and reject
are all audited (with only the length of the note). Export is blocked while any answer waits for
review, re-checks that the evidence is still visible to the person at export time, and guards
CSV cells against formula injection.

## 8. The audit log is append-only and holds no content

Events record who, what, the decision and the reason code, never document text, quotes, tokens
or passwords. The database refuses edits and deletes of audit rows. A failed audit write fails
the request.

## 9. Owner-only runs return "not found", not "forbidden"

Someone else's run or chat looks exactly like one that does not exist, and the attempt is audited.

## 10. Low-privilege sign-up, no way to ask for a role

A new account is `external` with `public` clearance. The role cannot be sent in the request. Only
`employee` and `executive` can start RFP runs. Company addresses are reserved.

## 11. Two Q&A modes

Public: no login, a fixed guest identity that can see public documents only, nothing saved except
one metadata audit row, limited in total per hour. Signed in: chats are saved and listed at next
login; evidence is re-checked against current access when a chat is reopened, and a revoked
source replaces the answer with a notice.

## 12. Zero cost, mostly local

Local embeddings (fastembed, 384 dimensions), Postgres with pgvector in Docker, Gemini free tier
for generation, Streamlit for the interface. React was rejected to keep one language and no build
step. The screens only call the API, so they cannot bypass any rule.

## 13. Evaluation honesty

The RFP score was developed against a ground-truth file, so it is a development score. The Q&A
evaluation uses questions the author wrote independently, and security is checked by a script
that attacks the running system.
