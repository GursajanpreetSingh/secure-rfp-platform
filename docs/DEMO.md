# Viva demo script (about 10 minutes)

Before you start: Docker is running, both servers are running, and you have signed out of every
account. Have `docs/DECISIONS.md` and `docs/LIMITATIONS.md` open in tabs.

## 1. The idea in one breath (30 seconds)
"A company assistant that answers only from documents you are allowed to see, shows the exact
quote behind every answer, and says 'I could not find this' instead of guessing. It has two
parts: RFP compliance and question answering."

## 2. Public Q&A, no account (1 minute)
Sidebar: **Public questions**.
- Ask: *What hours is customer support available?* It answers with a source box.
- Ask: *What are the internal salary bands?* It says it could not find it.
Say: "A stranger only ever reaches the public documents, and nothing is saved."

## 3. Sign up (1 minute)
**Create account** with a new email. Point out the `external` chip and the notice that this account
cannot run RFPs. Say: "A new account cannot choose its role, and the server enforces this, not the
screen."

## 4. Staff: RFP compliance (4 minutes)
Sign out, sign in as `eng@meridian.test`. Open **RFP dashboard**.
- Show the four numbers and the status chart.
- Upload an RFP and show the progress bar (stop it early; a full run takes minutes, so also open a
  finished run).
- Open **Review answers**, pick a finished run, open one card: requirement, system answer,
  rationale, the quote.
- Say: "This quote is verified in code. If the model's quote is not really in the document, the
  answer is replaced by 'insufficient evidence'."
- Try **Use another status** with no note: it asks for a reason. Approve one answer.
- Show that **Prepare CSV export** is disabled while answers wait. Say: "Nothing leaves without a
  human."

## 5. Staff: saved chat (1 minute)
**Question answering**: ask *By how much did the Orion retail project reduce auditing time?*, then
sign out, sign in again, and open the chat from the list. Say: "Saved chats come back at the next
login; public ones never do."

## 6. Auditor (1 minute)
Sign in as `auditor@meridian.test`: **Audit log** shows events with who and why, and never the
document text. Say: "The database refuses edits and deletes of these rows."

## 7. The evidence (1 minute)
Show `docs/EVALUATION.md`: 92.8% on 69 requirements with zero wrongly-compliant answers, 25 of 25
attacks refused, 678 tests passing. Then say what is not proven: it is a development score, the
Q&A set is small, and there was no load test.

## Questions to expect, and honest answers

**Why not just ask ChatGPT about the documents?** Because it cannot enforce who may see which
document, it cannot prove its quote is real, and it does not keep an audit log.

**How do you stop it leaking a confidential document?** The permission check is part of the search
query. A document the person cannot see never reaches the model. The attack script confirms this.

**What if the model lies?** It must give a quote; code checks the quote is in the document and that
every number in the answer appears in the quote. Failing either check turns the answer into
"could not find". A human reviews RFP answers anyway.

**How accurate is it?** 92.8% on the 69 development requirements, with zero answers marked
compliant wrongly. That score was tuned on those same requirements, so I do not claim it
generalises; the independent Q&A set is the fair test, and it is small.

**Did you use reranking?** No, and I did not evaluate it. The failures I traced were query wording
and strict quote checking, and the model reads 8 excerpts. Testing a reranker is future work.

**What is the biggest weakness?** It sometimes declines a correct answer because the quote check is
strict (for example a quote across table cells). I chose that direction on purpose. Also: no email
verification, a free model tier, and synthetic data only.

**Why Streamlit, not React?** One language, no build step, and the screens only call the API, so a
screen bug cannot bypass a rule.
