import asyncio
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from app.db import PaperRecord, Setting
from app.main import create_app
from app.schemas import Paper, Provenance
from app.providers import ProviderClient
from app.security import RateLimiter
import httpx
@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR",str(tmp_path))
    monkeypatch.setenv("CREDENTIALS_KEY",Fernet.generate_key().decode())
    monkeypatch.setenv("APP_ENV","development")
    monkeypatch.delenv("APP_ACCESS_TOKEN",raising=False)
    monkeypatch.delenv("LLM_PROVIDER",raising=False)
    monkeypatch.delenv("OPENAI_API_KEY",raising=False)
    app = create_app("sqlite:///:memory:",initialize=True)
    with TestClient(app) as value:
        yield value
def example():
    return Paper(id="doi:10.1234/example",title="A source record",doi="10.1234/example",
        abstract="Measurements were made at room temperature.",
        provenance=[Provenance(provider="fixture",record_id="1",retrieved_at="2026-10-09T00:00:00+00:00",
        doi="10.1234/example",source_url="https://doi.org/10.1234/example",oa_status=None,license=None)])
def test_project_notes_saved_search_and_paper_revision(client):
    made = client.post("/api/projects",json={"name":"Tellurite","question":"Optical glasses?"})
    assert made.status_code == 201
    path = "/api/projects/"+made.json()["id"]
    paper = example()
    assert client.post(path+"/papers",json={"paper":paper.model_dump()}).status_code == 200
    assert client.post(path+"/papers",json={"paper":paper.model_dump()}).status_code == 200
    assert len(client.get(path).json()["papers"]) == 1
    enriched = paper.model_copy(update={"citations":{"OpenAlex":12}})
    client.post(path+"/papers",json={"paper":enriched.model_dump()})
    with client.app.state.sessions() as session:
        assert session.query(PaperRecord).count() == 2
    assert client.get(path).json()["papers"][0]["provenance"][0]["record_id"] == "1"
    client.put(path+"/notes",json={"content":"<script>is plain text</script>"})
    assert client.get(path).json()["notes"] == "<script>is plain text</script>"
    saved = client.post(path+"/searches",json={"question":"Tellurite optics","queries":[{"kind":"direct","query":"tellurite","enabled":True}]})
    assert len(saved.json()["searches"]) == 1
    client.delete(path+"/papers/doi:10.1234/example")
    assert client.get(path).json()["papers"] == []
    assert client.delete(path).json() == {"deleted":True}
    assert client.get(path).status_code == 404
def test_projects_accept_no_fabricated_papers(client):
    assert client.get("/api/projects").json() == []
    assert client.post("/api/projects",json={"name":"  "}).status_code == 422
    project = client.post("/api/projects",json={"name":"New"}).json()
    assert project["papers"] == []
    assert project["searches"] == []
def test_credentials_never_returned_and_encrypted(client):
    secret = "test-secret-not-a-real-credential"
    response = client.put("/api/settings",json={"openai_api_key":secret,"openai_model":"configured-model"})
    assert response.status_code == 200
    assert secret not in response.text
    assert response.json()["configured"]["openai_api_key"] is True
    assert secret not in client.get("/api/settings").text
    with client.app.state.sessions() as session:
        assert secret not in session.get(Setting,"openai_api_key").encrypted_value
    assert client.put("/api/settings",json={"llm_base_url":"http://169.254.169.254"}).status_code == 422
    assert client.put("/api/settings",json={"unpaywall_email":"invalid"}).status_code == 422
def test_unsafe_urls_and_inputs_rejected(client):
    payload = example().model_dump()
    payload["pdf_url"] = "javascript:alert(1)"
    assert client.post("/api/enrich",json={"paper":payload}).status_code == 422
    assert client.post("/api/doi",json={"doi":"not a DOI"}).status_code == 422
    assert client.post("/api/search",json={"question":"test","year_from":2026,"year_to":2000}).status_code == 422
    assert client.post("/api/strategy",content=b"x"*(2*1024*1024+1),headers={"content-type":"application/json"}).status_code == 413
def test_auth_required_when_configured(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR",str(tmp_path))
    monkeypatch.setenv("APP_ACCESS_TOKEN","a-long-local-workspace-token")
    monkeypatch.setenv("APP_ENV","production")
    with TestClient(create_app("sqlite:///:memory:",initialize=True)) as client:
        assert client.get("/api/health").status_code == 200
        assert client.get("/api/projects").status_code == 401
        assert client.get("/api/projects",headers={"Authorization":"Bearer a-long-local-workspace-token"}).status_code == 200
def test_production_rejects_no_access_token(tmp_path,monkeypatch):
    monkeypatch.setenv("DATA_DIR",str(tmp_path))
    monkeypatch.setenv("APP_ENV","production")
    monkeypatch.delenv("APP_ACCESS_TOKEN",raising=False)
    with pytest.raises(RuntimeError,match="APP_ACCESS_TOKEN"):
        with TestClient(create_app("sqlite:///:memory:",initialize=True)):
            pass
def test_rate_limit_is_explicit():
    tick = [0]
    limiter = RateLimiter(limit=2,period=60,clock=lambda:tick[0])
    assert limiter.allowed("one")
    assert limiter.allowed("one")
    assert not limiter.allowed("one")
    assert limiter.allowed("another")
    tick[0] = 61
    assert limiter.allowed("one")
def test_http_rate_limit(tmp_path,monkeypatch):
    monkeypatch.setenv("DATA_DIR",str(tmp_path))
    monkeypatch.setenv("API_RATE_LIMIT","1")
    monkeypatch.setenv("APP_ENV","development")
    monkeypatch.delenv("APP_ACCESS_TOKEN",raising=False)
    with TestClient(create_app("sqlite:///:memory:",initialize=True)) as client:
        assert client.get("/api/projects").status_code == 200
        response = client.get("/api/projects")
        assert response.status_code == 429
        assert response.headers["retry-after"] == "60"
def test_search_failure_is_normalized(client):
    client.app.state.provider_client = ProviderClient(retries=0,transport=httpx.MockTransport(lambda req:httpx.Response(503)))
    response = client.post("/api/search",json={"question":"tellurite optics","queries":[{"kind":"direct","query":"tellurite"}]})
    assert response.status_code == 200
    assert response.json()["papers"] == []
    assert response.json()["errors"][0]["provider"]
    asyncio.run(client.app.state.provider_client.close())
def test_synthesis_without_model_is_honest(client):
    response = client.post("/api/synthesize",json={"question":"What is the thermal stability?","papers":[example().model_dump()],"mode":"Evidence Review"})
    assert response.status_code == 200
    value = response.json()
    assert "no AI" in value["provider"]
    assert any(item["classification"] == "UNKNOWN" for item in value["statements"])
    assert all(c["paper_id"] == example().id for item in value["statements"] for c in item["citations"])
def test_search_strategy_is_editable(client):
    value = client.post("/api/strategy",json={"question":"TeO2 glass transition temperature optical properties"}).json()
    assert len(value["queries"]) >= 6
    assert all("kind" in q and "query" in q and "enabled" in q for q in value["queries"])
    assert value["notes"]

def test_browser_provenance_raw_metadata_accepted(client):
    payload = example().model_dump()
    payload["provenance"][0]["raw_record"] = {"id":"source-1","abstract_inverted_index":{"Measurements":[0]}}
    p = client.post("/api/projects",json={"name":"Browser import"}).json()
    response = client.post("/api/projects/"+p["id"]+"/papers",json={"paper":payload})
    assert response.status_code == 200
    assert response.json()["papers"][0]["provenance"][0]["raw_record"]["id"] == "source-1"

def test_validation_does_not_echo_secret_input(client):
    secret = "invalid-private-secret"*200
    response = client.put("/api/settings",json={"openai_api_key":secret})
    assert response.status_code == 422
    assert secret not in response.text

def test_cors_wraps_auth_errors(tmp_path,monkeypatch):
    monkeypatch.setenv("DATA_DIR",str(tmp_path))
    monkeypatch.setenv("APP_ACCESS_TOKEN","a-long-local-workspace-token")
    monkeypatch.setenv("APP_ENV","production")
    monkeypatch.setenv("CORS_ORIGINS","https://research.example")
    with TestClient(create_app("sqlite:///:memory:",initialize=True)) as c:
        response = c.get("/api/projects",headers={"Origin":"https://research.example"})
        assert response.status_code == 401
        assert response.headers["access-control-allow-origin"] == "https://research.example"

def test_server_applies_strategy_dates_and_sort(client):
    from datetime import datetime, timezone
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={"results":[]})
    client.app.state.provider_client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
    response = client.post("/api/search",json={"question":"tellurite optics","queries":[
        {"kind":"Recent literature","query":"tellurite"},
        {"kind":"Foundational candidates","query":"tellurite"},
        {"kind":"Review papers","query":"tellurite"}]})
    assert response.status_code == 200
    params = [dict(r.url.params) for r in calls]
    year = datetime.now(timezone.utc).year
    assert any(p.get("sort") == "publication_date:desc" and str(year-4) in p["filter"] for p in params)
    assert any(p.get("sort") == "cited_by_count:desc" and str(year-8) in p["filter"] for p in params)
    assert any("type:review" in p.get("filter","") for p in params)
    assert all(q["filters"] for q in response.json()["queries"])
    asyncio.run(client.app.state.provider_client.close())

def test_crossref_keyword_fallback_preserves_error_and_unknown_access(client):
    def handler(request):
        if request.url.host == "api.openalex.org":
            return httpx.Response(429,headers={"Retry-After":"120"})
        return httpx.Response(200,json={"message":{"items":[{"DOI":"10.1234/fallback","title":["Metadata fixture"],"type":"journal-article"}]}})
    client.app.state.provider_client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
    response = client.post("/api/search",json={"question":"tellurite optics","queries":[{"kind":"direct","query":"tellurite"}]})
    value = response.json()
    assert response.status_code == 200
    assert len(value["papers"]) == 1
    assert value["papers"][0]["is_oa"] is None
    assert value["papers"][0]["source_basis"] == "metadata"
    assert value["papers"][0]["provenance"][0]["provider"] == "crossref"
    assert value["errors"][0]["code"] == "rate_limited"
    assert value["queries"][-1]["kind"] == "Crossref metadata fallback"
    asyncio.run(client.app.state.provider_client.close())

def test_saved_fallback_strategy_is_reusable(client):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(200,json={"results":[]})
    client.app.state.provider_client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
    queries = [{"kind":"direct","query":"tellurite","enabled":True},{"kind":"Crossref metadata fallback","query":"tellurite","enabled":True}]
    response = client.post("/api/search",json={"question":"tellurite optics","queries":queries})
    assert response.status_code == 200
    assert len(calls) == 1
    assert len(response.json()["queries"]) == 1
    asyncio.run(client.app.state.provider_client.close())
