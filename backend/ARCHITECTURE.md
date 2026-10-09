# Backend design — Phase 1

One FastAPI service, SQLAlchemy persistence, and replaceable LiteratureProvider and LLMProvider adapters. OpenAlex is primary search; Crossref DOI metadata; Semantic Scholar enrichment; Unpaywall DOI-level OA links with configured contact email. No PDF ingestion is performed. Source-extract briefs work without a model; optional OpenAI-compatible and local Ollama outputs have literal citation checks.

## Schema

projects(id UUID PK, name, question, notes, created_at).
papers(id content digest PK, canonical_id indexed, doi indexed nullable, payload JSON, created_at).
project_papers(project_id FK+PK, paper_id FK+PK, linked_at).
saved_searches(id UUID PK, project_id FK indexed, question, queries JSON, created_at).
settings(key PK, encrypted_value Fernet ciphertext).

Migration 0001 creates all tables. SQLite enables foreign keys; PostgreSQL uses psycopg. Changed imports create new content-addressed revisions. Project links can point to new revisions while original imports remain intact.

## Security and operation

This is a single-user workspace. Production requires APP_ACCESS_TOKEN (at least 24 characters) and HTTPS at the reverse proxy. Development authentication is optional; Compose binds to localhost. Credentials are encrypted with CREDENTIALS_KEY or a generated persisted DATA_DIR/.credentials.key. Back up the key with the database. API responses expose only configured status.

Provider destinations are fixed and redirects are disabled. Model hosts are operator-only environment settings. Input validation, body/rate limits and parameterized SQL apply. Provider failures remain independent with bounded retries and caching. Phase 1 has no upload execution or full-text ingestion.

## Modules

app/schemas.py: API records; db.py: persistence; providers.py: resilient metadata adapters; research.py: DOI normalization, deduplication and strategy; security.py: encryption/auth/limits; llm.py: bounded model adapters and citation verification; main.py: orchestration. migrations/: schema history. tests/: mocked checks.

Official docs and the four-phase implementation plan are recorded in the root [ARCHITECTURE.md](../ARCHITECTURE.md).
