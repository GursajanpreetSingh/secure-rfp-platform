# ADR 001: Use PostgreSQL with pgvector as the single data store

- Status: Accepted
- Date: 2026-11-08

## Context

The platform must retrieve evidence from company documents, and it must never return a chunk the
requesting user is not allowed to see. The first design used four stores: PostgreSQL (users, ACLs,
metadata), Qdrant (vectors), a separate BM25 keyword index, and Neo4j (knowledge graph).

With several stores, every permission change has to be applied to each of them, and a missed update
silently becomes a data leak. The project also has a fixed 30-day schedule.

## Decision

Use PostgreSQL 16 with the pgvector extension and built-in full-text search as the only data store
for the first version.

- Vector search: a pgvector `vector(1536)` column with an HNSW index (cosine distance).
- Keyword search: a generated `tsvector` column with a GIN index.
- Permissions: copied onto every chunk, and applied as one SQL `WHERE` clause in the same query as
  the search, so authorization and retrieval cannot drift apart.

## Alternatives considered

| Option | Why not (for now) |
|---|---|
| Qdrant + PostgreSQL | Permissions must be synchronised into Qdrant payloads. Another service to run and secure |
| Separate BM25 service (Elasticsearch, OpenSearch) | Heavy to operate. PostgreSQL full-text search is enough at this scale |
| Neo4j knowledge graph | Needs reliable entity extraction first. Traversal must enforce the same permissions. Deferred as an experiment |
| SQLite or Chroma | No row-level security, weaker concurrency, harder to demonstrate access control |

## Consequences

Positive:
- One transaction can write a document, its chunks and its audit event together.
- One ACL filter protects vector search, keyword search and metadata alike.
- One container to run locally and in CI.

Negative:
- pgvector is slower than a dedicated vector database at very large scale.
- Full-text ranking (`ts_rank`) is not true BM25.
- Graph queries are limited to joins and recursive queries.

## When to revisit

- Retrieval latency becomes a problem at more than about 1 million chunks.
- Experiments show graph-aware retrieval clearly beats hybrid retrieval. A graph can then be added
  as a derived index that is rebuilt from PostgreSQL, never as the source of truth.
