# Open Materials Research Copilot

An installable, responsive research workspace for open literature. Phase 1 connects OpenAlex discovery, Crossref DOI imports, projects, saved papers, notes and traceable abstract/metadata briefs. The full backend adds Semantic Scholar enrichment, Unpaywall OA resolution, SQLite storage and optional OpenAI-compatible or local Ollama synthesis.

**This is Phase 1.** No PDF extraction, structured property evidence, OPTIMADE/materials search or scientific comparison table is claimed. Those screens explain their planned phase. The tellurite experimental comparison acceptance scenario requires later phases.

## Use on a OnePlus 13

The frontend can be hosted free on GitHub Pages. It works directly with public OpenAlex and Crossref, stores projects on your device, and requires no AI account or paid subscription.

1. Repository owner: enable **Settings → Pages → Build and deployment → Source → GitHub Actions** once.
2. The **Publish phone PWA** workflow publishes after successful checks on main. For an already enabled site, it can also be run manually from Actions.
3. Open the deployment URL shown by that workflow in Chrome.
4. Chrome menu → **Install app** or **Add to Home screen**.

Do not assume a deployment URL is live before GitHub reports a successful deployment. The repository Pages configuration is an owner action; the normal workflow token cannot enable a new Pages site.

GitHub Pages hosts the frontend only. For server SQLite, secrets, Unpaywall/Semantic Scholar enrichment and LLMs, run the included backend and connect its HTTPS URL in Settings. Browser mode is useful on its own and labels source-extract briefs as non-AI. Browser project data is private to that device's browser storage, not committed to this repository.

## Full app with Docker

Install Docker Engine with the Compose plugin (or Docker Desktop). Clone this repository, then:

```sh
cp .env.example .env
docker compose up --build
```

Open **http://localhost:8080**. In **Settings → Backend connection**, leave the backend URL blank to use the same-origin API, enter APP_ACCESS_TOKEN if configured, and select Connect. Create your server project. Provider keys are optional and never needed for public search.

Docker runs FastAPI and nginx, applies Alembic migrations and preserves database/encrypted configuration in a named volume. The default port binds to localhost. For a remotely reachable server, set a strong APP_ACCESS_TOKEN, configure HTTPS and explicit CORS origins. Production mode refuses to start without an access token. Development mode is intentionally unauthenticated unless a token is configured, and Compose binds its public port to localhost. Do not publish port 8000 directly or expose an unprotected dev installation.

PWA installation and service workers require HTTPS outside localhost; opening an HTTP LAN address on your phone does not provide a fully installable offline PWA. Use a trusted HTTPS deployment or the Pages frontend connected to your HTTPS backend.

## Research workflow

1. Enter a research question and select **Build search strategy**.
2. Edit or disable the seven direct, expanded, composition, property, review, recent and foundational queries.
3. Choose filters and **Search open literature**. Queries actually used are retained with the project.
4. Open original records and check provenance. Save useful papers to the current project.
5. Keep your own notes. Export project JSON and citation bibliographies.
6. Prepare a brief from a bounded selection of available abstracts/metadata records (up to eight sent to a configured model). Configure an optional backend model for AI synthesis.

The sample project contains the tellurite question but **no invented papers or measured data**. Search results come from real provider requests. Test fixtures are clearly marked and isolated in test directories.

## Scientific boundaries

- Every source retains provider, record ID, retrieval time, identifiers, source URLs, OA status and supplied license.
- Preprints stay labelled as preprints. An article type does not independently verify peer review.
- Citation counts remain associated with the provider that reported them.
- Missing metadata/abstracts remain null. A metadata-only paper is never presented as full-text analysed.
- An OA location is a link to a lawful copy, not a claim that its full text has been ingested.
- No paywall bypass or ResearchGate scraping.
- SUPPORTED / INFERRED / SPECULATIVE / UNKNOWN statements stay separate from source data.
- Citation checks ensure cited IDs and quoted text exist. They cannot establish scientific truth or validate a model's reasoning.
- If source evidence is insufficient, the app says so.

## Storage and offline use

The app shell is cached after the first successful production visit. Browser-mode projects, notes, abstracts, provenance and saved strategies live in IndexedDB and remain available offline. Searches and server operations need internet. Full-text documents are not cached or redistributed in Phase 1.

Browser storage is not multi-device sync. Export backups from Projects or Settings; clearing browser data removes local projects. Switching to backend mode does not migrate or erase local projects. Disconnect to return to them. The backend access token is only kept in tab memory and must be re-entered after reload.

## Local development

Requirements: Node.js 22+, Python 3.12+, npm. Dependencies are deliberately limited; no vector database or scientific toolkit is needed for Phase 1.

```sh
cd backend
python -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal:

```sh
cd web
npm ci
npm run dev
```

Open localhost:3000; connect http://localhost:8000 in Settings. Configure backend CORS for that origin (included in development defaults). Production uses static export and the API boundary remains compatible with later Tauri/Capacitor packaging.

## Tests and build

```sh
cd backend
python -m pytest -q
```

```sh
cd web
npm ci
npm run typecheck
npm test
npm run build
npx playwright install chromium
npm run test:e2e
```

Backend tests mock scientific APIs. Frontend tests cover normalization, missing values, deduplication, rates/retries, provenance, source citations and exports. Playwright tests exercise mobile/desktop search, paper saving, notebook persistence, offline reload, project export, honest deferred phases and provider errors. Docker CI starts the real application and checks API + frontend.

GitHub Actions runs checks on pushes and pull requests. It uploads the built PWA and Playwright failure reports. Review the current workflow result before treating a commit as verified.

## Provider and model configuration

See [.env.example](.env.example) and [backend/ARCHITECTURE.md](backend/ARCHITECTURE.md). Optional provider/LLM credentials can be entered through Settings after connecting to your own backend; they are encrypted server-side and never returned to the browser. Keep the encryption key with the database backup; do not rotate it casually.

- OpenAlex: public basic queries; optional free key improves daily quota.
- Crossref: public DOI metadata and keyword fallback if OpenAlex fails; optional contact email. Fallback is disabled for OA-only/review-only searches because Crossref cannot reliably enforce those filters.
- Semantic Scholar: optional enrichment; throttling/failure does not break other providers.
- Unpaywall: DOI resolution only, requires a contact email.
- OpenAI-compatible: user-selected API key/model; may incur provider charges.
- Ollama: local models on an operator-configured endpoint; no paid API required.

Provider quotas and CORS availability may change. Browser failures are explicit and preserve saved work. Backend adapters implement timeouts, bounded retries/backoff, cache and normalized errors.

## Layout and implementation plan

```
ARCHITECTURE.md
backend/             FastAPI, schemas, providers, LLM adapters, database
  migrations/           Versioned migrations
  tests/             Mocked API and scientific integrity tests
web/
  src/app/           Responsive PWA interface
  src/lib/           Typed records, browser providers and IndexedDB
  scripts/           Static PWA generation and preview
  tests/             Mobile/desktop/offline browser checks
.github/workflows/   CI, Docker smoke checks and optional Pages deployment
compose.yaml
.env.example
```

[ARCHITECTURE.md](ARCHITECTURE.md) defines the data contract, security model and Phase 2–4 plan. Backend and browser providers implement the same normalized source shape; no AI content overwrites original scientific evidence.

## Development sample

After migrations, run `python -m app.seed` from `backend` (or `docker compose exec api python -m app.seed`) to create the tellurite project without invented literature or property values. The browser creates the same kind of empty starter workspace automatically.
