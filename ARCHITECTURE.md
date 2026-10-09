# Open Materials Research Copilot — architecture

## Scope and scientific contract

Phase 1 only: responsive installable Next.js/React/TypeScript PWA, projects, editable seven-query strategy, OpenAlex search, Crossref DOI import, optional Semantic Scholar and Unpaywall enrichment, deduplication, paper saving, provenance, notes and citation-checked abstract/metadata synthesis. No extraction of full-text evidence, PDF ingestion, materials federation or property comparison is claimed in this phase.

A paper having an OA URL does not mean the text was downloaded or analysed. Every source has a provider record ID, retrieval timestamp, DOI, source URL, OA status and supplied license. Missing data remains null. Provider citation counts remain separate. Article metadata does not verify peer review; the interface does not label articles peer-reviewed without verification.

Source content is immutable within synthesis: generated statements are separate objects. SUPPORTED requires a source citation and exact available-text quote; other scientific interpretations are INFERRED or SPECULATIVE. Insufficient evidence is UNKNOWN. Quote and citation validation checks traceability, not a guarantee that the inference is scientifically valid. No model is required for search, projects or an explicitly labelled source-extract brief.

## Runtime topology

- web/: Next.js static export, React, TypeScript, Tailwind. The same UI runs on phone, tablet and desktop, and can later be packaged using Capacitor or Tauri.
- backend/: FastAPI/Pydantic, SQLAlchemy, Alembic, SQLite development database; PostgreSQL URL supported for a production installation.
- Docker Compose: FastAPI service with durable data volume + web nginx service proxying /api to FastAPI. No secrets are built into frontend bundles.
- Hosted browser mode: when no backend is configured, the PWA queries public OpenAlex and Crossref endpoints and stores projects in IndexedDB on that device. This fallback is visibly labelled. It has no server AI, credential storage, Semantic Scholar enrichment or Unpaywall credential handling. No synchronization is promised.
- Optional backend mode: same frontend can connect to a trusted HTTPS backend. Bearer access token is held only in session memory. Provider and LLM secrets live exclusively on that server. Core functionality remains useful when providers fail.
- GitHub Pages is an optional frontend-only hosting target. It cannot host Python or SQLite. Publishing requires the repository owner to enable Pages if it has not previously been enabled.

## Database schema

Backend schema is versioned by Alembic. Projects store identifier, name, question, notes, created/updated timestamps. Papers store normalized bibliographic payload and original provider provenance. A project-paper join prevents duplicate saves; saved searches store question, actual queries and timestamps. Provider configuration stores encrypted secrets separately from safe public settings. HTTP response cache is bounded and time-limited; secrets must never become cache keys exposed in logs. See backend/ARCHITECTURE.md for exact tables.

Browser IndexedDB schema version 1 has a projects store keyed by ID. Each project contains notes, papers with provenance and saved strategies. Persist failures are surfaced. It is local to the browser/origin and should be backed up by JSON export. The service worker caches versioned application assets only; it never caches API credentials or authenticated API traffic.

## Interfaces

Paper = id, title, authors[], year?, journal?, doi?, publication_type, citations{provider:count}, is_oa?, oa_url?, pdf_url?, abstract?, provenance[], source_basis.
Provenance = provider, record_id, retrieved_at, source_url, doi?, oa_status?, license?.
Strategy = {kind, query, enabled}.
Synthesis = {mode, basis, provider, statements:[{classification,text,citations:[{paper_id,quote,basis}]}], limitations[]}.

LiteratureProvider adapters normalize external responses into Paper; failures normalize to {provider,code,message}. DOI normalization strips DOI URL/prefix and lowercases the identifier. Deduplication uses DOI, then normalized title/year/author where compatible; it never merges known conflicting DOIs. Duplicate provider provenance is preserved.

LLMProvider adapters support OpenAI-compatible chat completions and local Ollama. Prompt input is bounded selected abstracts and metadata, never hundreds of papers. Source text is untrusted data, not instructions. Responses must obey the scientific contract and cite only supplied IDs and exact available quotes.

## API

/api/health; /api/strategy; /api/search; /api/doi; /api/enrich; /api/synthesize; /api/settings; /api/projects; /api/projects/{id}; /api/projects/{id}/papers; /api/projects/{id}/notes; /api/projects/{id}/searches. Pydantic validates bounded inputs. Search, enrichment and synthesis have independent error states. Rate limits and timeouts protect providers and the API.

## Security and resilience

No paywall bypass, ResearchGate scraping, arbitrary uploaded-code execution, HTML rendering from providers or client-side API keys. Safe links allow HTTPS/HTTP only. Provider adapters use timeouts, bounded exponential backoff, Retry-After handling and TTL cache. Browser network errors do not erase saved work. Backend access token is required for non-local exposure. CORS origins are explicit; configurable model hosts are operator-controlled. PDF/upload processing is deferred to Phase 2, so Phase 1 exposes no upload execution surface.

## Official documentation inspected

- OpenAlex: https://help.openalex.org/api/authentication/ and https://help.openalex.org/api/ — current August 2026 docs allow basic anonymous queries; optional free key increases budget.
- Crossref: https://www.crossref.org/documentation/retrieve-metadata/rest-api/access-and-authentication/ — public metadata, optional mailto identification; honor response rate headers.
- Semantic Scholar: https://api.semanticscholar.org/api-docs/graph — enrichment is optional and may be throttled independently.
- Unpaywall: https://unpaywall.org/products/api — DOI lookup requires email; retired search endpoint is not used.
- GitHub Pages: https://github.com/actions/configure-pages/blob/main/action.yml — automatic initial enablement needs permission beyond GITHUB_TOKEN.

## Phased plan and acceptance

1. Write architecture/interfaces/schema; implement and run Phase 1 with mock provider tests, build/type checks, API smoke and mobile/offline browser tests.
2. Lawful PDF parsing with page mapping, structured evidence, condition-aware comparison, Europe PMC/arXiv/Zenodo and richer exports.
3. OPTIMADE registry federation, NOMAD/Materials Project/AFLOW/COD, scientific structure tools.
4. Semantic retrieval, contradiction/evidence graph, hypothesis workflow, stronger offline and multi-device sync.

The eventual tellurite acceptance query requires Phases 2–4. Phase 1 generates editable searches, retrieves/deduplicates real records, saves sources and produces only an abstract/metadata-limited brief. It cannot claim to extract compositions or compare measured properties and pages before full-text evidence exists.
