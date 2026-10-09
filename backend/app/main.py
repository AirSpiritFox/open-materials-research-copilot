import asyncio
import hashlib
import json
import os
from datetime import datetime, timezone
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from sqlalchemy import delete, select
from app.db import Base, Project, PaperRecord, ProjectPaper, SearchRecord, make_engine, make_session
from app.schemas import (DOIRequest, Notes, ProjectCreate, SavePaper, SavedSearch,
                         SearchRequest, SettingsUpdate, SynthesisRequest, Question)
from app.security import RateLimiter, authorized, load_settings, safe_settings, update_settings
from app.providers import ProviderClient, ProviderFailure, OpenAlex, Crossref, SemanticScholar, Unpaywall
from app.research import deduplicate, merge_papers, normalize_doi, strategy
from app.llm import synthesize
MAX_BODY = 2 * 1024 * 1024

def create_app(database_url=None, initialize=False):
    data_directory = Path(os.getenv("DATA_DIR", "./data"))
    data_directory.mkdir(parents=True, exist_ok=True)
    engine = make_engine(database_url)
    sessions = make_session(engine)
    client = ProviderClient()
    access_token = os.getenv("APP_ACCESS_TOKEN", "")
    limiter = RateLimiter(limit=int(os.getenv("API_RATE_LIMIT", "90")))

    @asynccontextmanager
    async def lifespan(app):
        if os.getenv("APP_ENV", "development") != "development" and len(access_token) < 24:
            raise RuntimeError("Production requires an APP_ACCESS_TOKEN of at least 24 characters")
        if initialize:
            Base.metadata.create_all(engine)
        yield
        await client.close()
        engine.dispose()

    app = FastAPI(title="Open Materials Research Copilot", version="0.1.0", lifespan=lifespan,
                  docs_url=None, redoc_url=None)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": [
            {"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()
        ]})
    app.state.sessions = sessions
    app.state.provider_client = client
    app.state.limiter = limiter
    origins = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if x.strip()]
    if "*" in origins:
        raise RuntimeError("CORS_ORIGINS must name explicit origins")

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.url.path == "/api/health":
            return await call_next(request)
        if request.method == "OPTIONS":
            return await call_next(request)
        if not authorized(request.headers.get("authorization", ""), access_token):
            return JSONResponse(status_code=401, content={"detail": "A valid workspace access token is required"})
        origin = request.headers.get("origin")
        if not access_token and origin and origin not in origins:
            return JSONResponse(status_code=403, content={"detail": "Origin is not allowed"})
        key = request.client.host if request.client else "unknown"
        if not limiter.allowed(key):
            return JSONResponse(status_code=429, headers={"Retry-After": "60"}, content={"detail": "Too many requests. Retry shortly."})
        raw_length = request.headers.get("content-length")
        if raw_length:
            try:
                if int(raw_length) > MAX_BODY or int(raw_length) < 0:
                    return JSONResponse(status_code=413, content={"detail": "Request body exceeds 2 MiB"})
            except ValueError:
                return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        chunks, length = [], 0
        async for chunk in request.stream():
            length += len(chunk)
            if length > MAX_BODY:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds 2 MiB"})
            chunks.append(chunk)
        request._body = b"".join(chunks)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    def configuration():
        with sessions() as session:
            return load_settings(session)
    def require_project(session, project_id):
        project = session.get(Project, project_id)
        if not project:
            raise HTTPException(404, "Project not found")
        return project
    def view_project(session, project):
        rows = session.execute(select(PaperRecord).join(ProjectPaper, ProjectPaper.paper_id == PaperRecord.id)
                               .where(ProjectPaper.project_id == project.id).order_by(ProjectPaper.linked_at)).scalars().all()
        searches = session.execute(select(SearchRecord).where(SearchRecord.project_id == project.id)
                                   .order_by(SearchRecord.created_at)).scalars().all()
        return {"id": project.id, "name": project.name, "question": project.question,
                "notes": project.notes, "created_at": project.created_at,
                "papers": [record.payload for record in rows],
                "searches": [{"id": row.id, "question": row.question, "queries": row.queries,
                              "created_at": row.created_at} for row in searches]}

    @app.get("/api/health")
    async def health():
        return {"status": "ok", "phase": 1}
    @app.get("/api/projects")
    def projects():
        with sessions() as session:
            rows = session.execute(select(Project).order_by(Project.created_at.desc())).scalars()
            return [view_project(session, project) for project in rows]
    @app.post("/api/projects", status_code=201)
    def create_project(body: ProjectCreate):
        with sessions() as session:
            project = Project(name=body.name, question=body.question)
            session.add(project)
            session.commit()
            return view_project(session, project)
    @app.get("/api/projects/{project_id}")
    def get_project(project_id: str):
        with sessions() as session:
            return view_project(session, require_project(session, project_id))
    @app.delete("/api/projects/{project_id}")
    def remove_project(project_id: str):
        with sessions() as session:
            project = require_project(session, project_id)
            session.delete(project)
            session.commit()
            return {"deleted": True}
    @app.put("/api/projects/{project_id}/notes")
    def notes(project_id: str, body: Notes):
        with sessions() as session:
            project = require_project(session, project_id)
            project.notes = body.content
            session.commit()
            return view_project(session, project)
    @app.post("/api/projects/{project_id}/papers")
    def save_paper(project_id: str, body: SavePaper):
        paper = body.paper
        with sessions() as session:
            project = require_project(session, project_id)
            payload = paper.model_dump()
            digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            record_id = "import:" + digest
            if session.get(PaperRecord, record_id) is None:
                session.add(PaperRecord(id=record_id, canonical_id=paper.id, doi=paper.doi, payload=payload))
                session.flush()
            linked = session.execute(select(PaperRecord).join(ProjectPaper, ProjectPaper.paper_id == PaperRecord.id)
                                     .where(ProjectPaper.project_id == project_id)).scalars().all()
            for record in linked:
                if record.canonical_id == paper.id or (paper.doi and record.doi == paper.doi):
                    session.execute(delete(ProjectPaper).where(ProjectPaper.project_id == project_id, ProjectPaper.paper_id == record.id))
            session.add(ProjectPaper(project_id=project_id, paper_id=record_id))
            session.commit()
            return view_project(session, project)
    @app.delete("/api/projects/{project_id}/papers/{paper_id:path}")
    def remove_paper(project_id: str, paper_id: str):
        with sessions() as session:
            project = require_project(session, project_id)
            ids = select(PaperRecord.id).where(PaperRecord.canonical_id == paper_id)
            session.execute(delete(ProjectPaper).where(ProjectPaper.project_id == project_id, ProjectPaper.paper_id.in_(ids)))
            session.commit()
            return view_project(session, project)
    @app.post("/api/projects/{project_id}/searches")
    def save_search(project_id: str, body: SavedSearch):
        with sessions() as session:
            project = require_project(session, project_id)
            session.add(SearchRecord(project_id=project_id, question=body.question, queries=[q.model_dump() for q in body.queries]))
            session.commit()
            return view_project(session, project)
    @app.post("/api/strategy")
    async def plan(body: Question):
        return strategy(body.question)
    def error_for(provider, exc):
        if isinstance(exc, ProviderFailure):
            value = exc.error
            return value.model_dump() if hasattr(value, "model_dump") else value
        return {"provider": provider, "code": "unavailable", "message": "Provider request failed; other results remain available."}
    @app.post("/api/search")
    async def search(body: SearchRequest):
        queries = body.queries
        if not queries:
            generated = strategy(body.question)["queries"]
            from app.schemas import Query
            queries = [q if isinstance(q, Query) else Query.model_validate(q) for q in generated]
        performed, requests, errors = [], [], []
        year = datetime.now(timezone.utc).year
        provider = OpenAlex(app.state.provider_client, configuration())
        for q in queries:
            if not q.enabled or q.kind == "Crossref metadata fallback":
                continue
            lower, upper = body.year_from, body.year_to
            kind = q.kind.casefold()
            recent = kind in {"recent", "recent literature"}
            foundational = kind in {"foundational", "foundational candidates"}
            review = kind in {"review", "review papers"}
            if recent:
                lower = max(lower or 1000, year - 4)
            if foundational:
                upper = min(upper or year, year - 8)
            if lower and upper and lower > upper:
                errors.append({"provider": "OpenAlex", "code": "incompatible_dates",
                               "message": q.kind + " skipped: its date range conflicts with your year filter."})
                continue
            effective = body.model_copy(update={
                "year_from": lower, "year_to": upper,
                "reviews_only": (body.reviews_only or review) and not body.preprints_only,
            })
            applied = []
            if lower:
                applied.append(f"from_publication_date:{lower}-01-01")
            if upper:
                applied.append(f"to_publication_date:{upper}-12-31")
            if body.oa_only:
                applied.append("open_access.is_oa:true")
            if body.preprints_only:
                applied.append("type:preprint")
            elif effective.reviews_only:
                applied.append("type:review")
            sort = "cited_by_count:desc" if foundational else "publication_date:desc" if recent else None
            performed.append(q.model_copy(update={"filters": applied, "sort": sort}))
            requests.append(provider.search(q.query, effective, sort=sort))
        results = await asyncio.gather(*requests, return_exceptions=True)
        papers = []
        for result in results:
            if isinstance(result, BaseException):
                errors.append(error_for("OpenAlex", result))
            else:
                papers.extend(result)
        if not papers and errors and performed and not body.oa_only and not body.reviews_only:
            query = performed[0].query
            fallback = performed[0].model_copy(update={
                "kind": "Crossref metadata fallback", "query": query, "filters": [], "sort": None,
                "note": "OpenAlex was unavailable. Crossref supplies bibliographic metadata; OA status remains unknown.",
            })
            applied = []
            if body.year_from:
                applied.append(f"from-pub-date:{body.year_from}-01-01")
            if body.year_to:
                applied.append(f"until-pub-date:{body.year_to}-12-31")
            if body.preprints_only:
                applied.append("type:posted-content")
            performed.append(fallback.model_copy(update={"filters": applied}))
            try:
                papers.extend(await Crossref(app.state.provider_client, configuration()).search(query, body))
            except Exception as exc:
                errors.append(error_for("Crossref", exc))
        unique = deduplicate(papers)
        return {"papers": [p.model_dump() for p in unique], "errors": errors,
                "queries": [q.model_dump() for q in performed], "deduplicated": len(papers) - len(unique)}
    @app.post("/api/doi")
    async def doi_lookup(body: DOIRequest):
        try:
            doi = normalize_doi(body.doi)
        except ValueError as exc:
            raise HTTPException(422, "Enter a valid DOI or doi.org URL") from exc
        config = configuration()
        providers = [("Crossref", Crossref(app.state.provider_client, config)), ("OpenAlex", OpenAlex(app.state.provider_client, config))]
        responses = await asyncio.gather(*(provider.lookup(doi) for _, provider in providers), return_exceptions=True)
        papers, errors = [], []
        for (name, _), response in zip(providers, responses):
            if isinstance(response, BaseException):
                errors.append(error_for(name, response))
            else:
                papers.append(response)
        unique = deduplicate(papers)
        return {"papers": [p.model_dump() for p in unique], "errors": errors, "queries": [], "deduplicated": len(papers) - len(unique)}
    @app.post("/api/enrich")
    async def enrich(body: SavePaper):
        config = configuration()
        providers = [("Semantic Scholar", SemanticScholar(app.state.provider_client, config)),
                     ("Unpaywall", Unpaywall(app.state.provider_client, config))]
        responses = await asyncio.gather(*(provider.enrich(body.paper) for _, provider in providers), return_exceptions=True)
        result, errors = body.paper, []
        for (name, _), response in zip(providers, responses):
            if isinstance(response, BaseException):
                errors.append(error_for(name, response))
            else:
                result = merge_papers(result, response)
        return {"paper": result.model_dump(), "errors": errors}
    @app.post("/api/synthesize")
    async def synthesis(body: SynthesisRequest):
        return await synthesize(body, configuration())
    @app.get("/api/settings")
    def settings():
        return safe_settings(configuration())
    @app.put("/api/settings")
    def configure(body: SettingsUpdate):
        with sessions() as session:
            return update_settings(session, body)
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_credentials=False,
                       allow_methods=["GET","POST","PUT","DELETE","OPTIONS"],
                       allow_headers=["Authorization","Content-Type"])
    return app
app = create_app()
