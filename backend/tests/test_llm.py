"""Grounding and provider behavior tests without external network."""
import asyncio
import copy
import json
import httpx
import pytest
from app import llm
from app.schemas import Paper, SynthesisRequest

def paper(paper_id="p1", abstract="The glass transition temperature was 330 K. Samples were melt quenched."):
    return Paper.model_construct(id=paper_id, title="Tellurite optical glass", abstract=abstract)
def request(papers=None):
    return SynthesisRequest.model_construct(question="What thermal properties were measured for tellurite optical glass?", papers=[paper()] if papers is None else papers, mode="Evidence Review")
def config(provider="openai"):
    return {"llm_provider": provider, "llm_model": "test-model",
        "llm_base_url": "https://model.example/v1" if provider == "openai" else "http://localhost:11434",
        "llm_api_key": "private-test-key"}
def statement(text="The glass transition temperature was 330 K.", basis="abstract", paper_id="p1", quote=None):
    return {"classification": "SUPPORTED", "text": text, "citations": [{"paper_id": paper_id, "basis": basis, "quote": quote if quote is not None else text}]}
def mock_provider(monkeypatch, statements=None, status=200, response_data=None, handler=None, provider="openai"):
    real_client, calls = httpx.AsyncClient, []
    def respond(req):
        calls.append(req)
        if handler:
            return handler(req)
        data = response_data
        if data is None:
            content = json.dumps({"statements": statements or [statement()]})
            data = {"choices": [{"message": {"content": content}}]} if provider == "openai" else {"message": {"content": content}}
        return httpx.Response(status, json=data)
    transport = httpx.MockTransport(respond)
    def client(**kwargs):
        assert kwargs.get("follow_redirects") is False
        return real_client(transport=transport, **kwargs)
    monkeypatch.setattr(llm.httpx, "AsyncClient", client)
    return calls
def run(req=None, cfg=None):
    return asyncio.run(llm.synthesize(req or request(), cfg if cfg is not None else config()))
def test_no_configuration_returns_source_extracts_and_unknown():
    result = run(cfg={})
    assert result["provider"] == "source-extract (no AI)"
    assert result["statements"][0]["classification"] == "SUPPORTED"
    assert result["statements"][0]["text"] in paper().abstract
    assert result["statements"][-1] == llm._unknown()
def test_no_papers_returns_insufficient_evidence():
    result = run(request([]), {})
    assert result["basis"] == "none"
    assert result["statements"] == [llm._unknown()]
def test_missing_abstract_is_metadata_only():
    result = run(request([paper(abstract=None)]), {})
    assert result["basis"] == "metadata"
    assert result["statements"][0]["citations"][0]["basis"] == "metadata"
    assert result["statements"][0]["text"] == "Tellurite optical glass"
def test_openai_request_and_exact_quote_validation(monkeypatch):
    calls = mock_provider(monkeypatch)
    result = run()
    assert result["provider"] == "OpenAI-compatible"
    assert result["statements"][0]["classification"] == "SUPPORTED"
    assert calls[0].url.path == "/v1/chat/completions"
    body = json.loads(calls[0].content)
    assert body["response_format"] == {"type": "json_object"}
    assert calls[0].headers["Authorization"] == "Bearer private-test-key"
    assert result["basis"] == "abstract"
@pytest.mark.parametrize("bad", [
    statement(paper_id="invented-paper"),
    statement(quote="The glass transition temperature was 999 K."),
    statement(basis="metadata"), statement(basis="full text"),
    statement(text="The measured glass transition temperature was 999 K.", quote="The glass transition temperature was 330 K."),
])
def test_invalid_citations_or_fabricated_values_are_removed(monkeypatch, bad):
    mock_provider(monkeypatch, statements=[bad])
    result = run()
    assert result["statements"] == [llm._unknown()]
    assert "999" not in json.dumps(result)
def test_abstract_citation_rejected_when_only_title_available(monkeypatch):
    mock_provider(monkeypatch, statements=[statement(text="Tellurite optical glass")])
    assert run(request([paper(abstract=None)]))["statements"] == [llm._unknown()]
def test_generated_paraphrase_is_inference_not_direct_evidence(monkeypatch):
    mock_provider(monkeypatch, statements=[statement(text="The reported thermal measurement concerns the glass transition.", quote="The glass transition temperature was 330 K.")])
    assert run()["statements"][0]["classification"] == "INFERRED"
def test_unknown_model_claim_does_not_retain_invented_values(monkeypatch):
    mock_provider(monkeypatch, statements=[{"classification":"UNKNOWN","text":"Possibly stable to 9999 K.","citations":[]}])
    result = run()
    assert result["statements"] == [llm._unknown()]
    assert "9999" not in json.dumps(result)
def test_ollama_uses_nonstreaming_json_mode(monkeypatch):
    calls = mock_provider(monkeypatch, provider="ollama")
    result = run(cfg=config("ollama"))
    body = json.loads(calls[0].content)
    assert calls[0].url.path == "/api/chat"
    assert body["format"] == "json"
    assert body["stream"] is False
    assert result["provider"] == "Ollama"
def test_provider_rate_limit_falls_back_without_response_disclosure(monkeypatch):
    mock_provider(monkeypatch, status=429, response_data={"error":"secret-key-and-private-provider-url"})
    result = run()
    assert result["provider"] == "source-extract (no AI)"
    assert "secret-key-and-private-provider-url" not in json.dumps(result)
    assert "private-test-key" not in json.dumps(result)
def test_timeout_falls_back_without_exception_disclosure(monkeypatch):
    def timeout(req):
        raise httpx.ConnectTimeout("private-provider-token", request=req)
    mock_provider(monkeypatch, handler=timeout)
    result = run()
    assert result["provider"] == "source-extract (no AI)"
    assert "private-provider-token" not in json.dumps(result)
def test_redirects_are_not_followed(monkeypatch):
    calls = mock_provider(monkeypatch, handler=lambda req:httpx.Response(302,headers={"Location":"http://other-host.example/private"}))
    assert run()["provider"] == "source-extract (no AI)"
    assert len(calls) == 1
def test_oversized_model_response_is_rejected(monkeypatch):
    mock_provider(monkeypatch, handler=lambda req:httpx.Response(200,content=b"x"*(llm.MAX_RESPONSE_BYTES+1)))
    assert run()["provider"] == "source-extract (no AI)"
def test_malformed_json_response_is_rejected(monkeypatch):
    mock_provider(monkeypatch, response_data={"choices":[{"message":{"content":"not JSON"}}]})
    assert run()["provider"] == "source-extract (no AI)"
def test_bounded_source_selection_and_original_records_unchanged(monkeypatch):
    papers = [paper("p"+str(i), ("Long unrelated context. "*300)+"The measured temperature was 330 K.") for i in range(40)]
    req = request(papers)
    before = copy.deepcopy([p.model_dump() for p in papers])
    calls = mock_provider(monkeypatch)
    run(req)
    body = json.loads(calls[0].content)
    sources = json.loads(body["messages"][1]["content"])["untrusted_source_data"]
    assert len(sources) <= 8
    assert sum(len(p["title"])+len(p["abstract_excerpt"]) for p in sources) <= 12_000
    assert [p.model_dump() for p in papers] == before
    assert "untrusted data" in body["messages"][0]["content"]
def test_model_limitations_cannot_inject_uncited_scientific_claims(monkeypatch):
    content = json.dumps({"statements":[statement()],"limitations":["The glass is stable to 9999 K."]})
    mock_provider(monkeypatch, response_data={"choices":[{"message":{"content":content}}]})
    assert "9999" not in json.dumps(run())
def test_speculative_label_is_preserved(monkeypatch):
    speculative = statement(text="A different processing route could change the measured transition.", quote="The glass transition temperature was 330 K.")
    speculative["classification"] = "SPECULATIVE"
    mock_provider(monkeypatch, statements=[speculative])
    assert run()["statements"][0]["classification"] == "SPECULATIVE"
