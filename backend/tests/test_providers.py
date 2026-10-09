import asyncio
from datetime import datetime
import httpx
import pytest
from app.providers import Crossref, OpenAlex, ProviderClient, ProviderFailure, SemanticScholar, Unpaywall, _abstract_from_index, plain_text, safe_url
from app.schemas import Paper, SearchRequest
def run(awaitable):
    return asyncio.run(awaitable)
def paper(**updates):
    data = dict(id="doi:10.1234/test",title="An optical glass study",authors=["A Researcher"],year=2024,journal="Example journal",doi="10.1234/test",publication_type="article",citations={},is_oa=None,oa_url=None,pdf_url=None,abstract=None,source_basis="metadata",provenance=[])
    data.update(updates)
    return Paper(**data)
def client_with(payload,status=200):
    return ProviderClient(retries=0,transport=httpx.MockTransport(lambda req:httpx.Response(status,json=payload)))
def search_request(**updates):
    return SearchRequest(question="tellurite glasses",queries=[],**updates)
def test_openalex_missing_abstract_and_citations_preserves_provenance():
    async def scenario():
        client = client_with({"results":[{"id":"https://openalex.org/W123","display_name":"Optical <i>tellurite</i> glasses","doi":"https://doi.org/10.1234/TEST","publication_year":2024,"authorships":[{"author":{"display_name":"Alice Smith"}}],"type":"preprint","open_access":{"is_oa":False}}]})
        try:
            result = (await OpenAlex(client,{}).search("tellurite",search_request()))[0]
            assert result.doi == "10.1234/test"
            assert result.title == "Optical tellurite glasses"
            assert result.publication_type == "preprint"
            assert result.abstract is None and result.pdf_url is None
            assert result.citations == {} and result.source_basis == "metadata"
            assert result.provenance[0].provider == "openalex"
            assert result.provenance[0].record_id == "https://openalex.org/W123"
            assert datetime.fromisoformat(result.provenance[0].retrieved_at).tzinfo
        finally:
            await client.close()
    run(scenario())
def test_openalex_explicit_oa_and_filters():
    requests = []
    def handler(req):
        requests.append(req)
        return httpx.Response(200,json={"results":[{"id":"https://openalex.org/W10","display_name":"Glass review","open_access":{"is_oa":True},"best_oa_location":{"is_oa":True,"landing_page_url":"https://repository.example/paper","pdf_url":"https://repository.example/paper.pdf","license":"cc-by"},"abstract_inverted_index":{"Optical":[0],"glass.":[1]},"cited_by_count":0}]})
    async def scenario():
        client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
        try:
            result = (await OpenAlex(client,{}).search("glass",search_request(year_from=2020,year_to=2025,oa_only=True,reviews_only=True)))[0]
            assert result.is_oa is True
            assert result.pdf_url == "https://repository.example/paper.pdf"
            assert result.abstract == "Optical glass." and result.source_basis == "abstract"
            assert result.citations == {"openalex":0}
            assert result.provenance[0].license == "cc-by"
            assert "from_publication_date:2020-01-01" in requests[0].url.params["filter"]
            assert "type:review" in requests[0].url.params["filter"]
            assert "api_key" not in requests[0].url.params
        finally:
            await client.close()
    run(scenario())
def test_crossref_license_or_link_does_not_assert_oa():
    async def scenario():
        client = client_with({"message":{"DOI":"10.1234/test","title":["<b>Glass</b>"],"author":[{"given":"A","family":"Smith"}],"published":{"date-parts":[[2023,5,1]]},"container-title":["Journal"],"type":"journal-article","abstract":"<jats:p>Reported observation.</jats:p>","is-referenced-by-count":8,"license":[{"URL":"https://creativecommons.org/licenses/by/4.0/"}],"link":[{"URL":"https://publisher.example/full.pdf"}]}})
        try:
            result = await Crossref(client,{}).lookup("https://doi.org/10.1234/test")
            assert result.is_oa is None and result.pdf_url is None and result.oa_url is None
            assert result.year == 2023 and result.authors == ["A Smith"]
            assert result.abstract == "Reported observation."
            assert result.citations == {"crossref":8}
            assert result.provenance[0].doi == "10.1234/test"
        finally:
            await client.close()
    run(scenario())
def test_crossref_rejects_mismatched_doi():
    async def scenario():
        client = client_with({"message":{"DOI":"10.1234/different"}})
        try:
            with pytest.raises(ProviderFailure) as exc:
                await Crossref(client,{}).lookup("10.1234/test")
            assert exc.value.error.code == "invalid_response"
        finally:
            await client.close()
    run(scenario())
def test_semantic_scholar_counts_remain_separate_and_no_false_fulltext():
    async def scenario():
        client = client_with({"paperId":"abc","title":"Glass","externalIds":{"DOI":"10.1234/test"},"citationCount":7,"isOpenAccess":False,"openAccessPdf":{"url":"https://example.org/p.pdf"},"abstract":None})
        try:
            result = await SemanticScholar(client,{}).enrich(paper(citations={"openalex":9}))
            assert result.citations == {"openalex":9,"semantic_scholar":7}
            assert result.pdf_url is None and result.abstract is None
            assert result.provenance[0].provider == "semantic_scholar"
        finally:
            await client.close()
    run(scenario())
def test_unpaywall_requires_email_but_missing_doi_is_noop():
    async def scenario():
        client = client_with({})
        try:
            adapter = Unpaywall(client,{})
            no_doi = paper(id="no-doi",doi=None)
            assert await adapter.enrich(no_doi) is no_doi
            with pytest.raises(ProviderFailure) as exc:
                await adapter.enrich(paper())
            assert exc.value.error.code == "not_configured"
        finally:
            await client.close()
    run(scenario())
def test_unpaywall_legitimate_repository_location():
    async def scenario():
        client = client_with({"doi":"10.1234/test","is_oa":True,"best_oa_location":{"url_for_landing_page":"https://repository.example/123","url_for_pdf":"https://repository.example/123.pdf","license":"cc-by"}})
        try:
            result = await Unpaywall(client,{"unpaywall_email":"researcher@example.org"}).enrich(paper())
            assert result.is_oa is True and result.pdf_url == "https://repository.example/123.pdf"
            assert result.provenance[0].oa_status == "open" and result.provenance[0].license == "cc-by"
            assert result.source_basis == "metadata"
        finally:
            await client.close()
    run(scenario())
def test_unpaywall_closed_keeps_fulltext_unavailable():
    async def scenario():
        client = client_with({"doi":"10.1234/test","is_oa":False,"best_oa_location":{"url_for_pdf":"https://publisher.example/paywall.pdf"}})
        try:
            result = await Unpaywall(client,{"unpaywall_email":"r@example.org"}).enrich(paper())
            assert result.is_oa is False and result.pdf_url is None and result.oa_url is None
        finally:
            await client.close()
    run(scenario())
def test_cache_isolated_by_provider_configuration_and_defensive_copy():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(200,json={"nested":{"value":1}})
    async def scenario():
        client = ProviderClient(transport=httpx.MockTransport(handler))
        try:
            url = "https://api.openalex.org/works"
            first = await client.get("openalex",url,params={"api_key":"secret-one"})
            first["nested"]["value"] = 20
            assert (await client.get("openalex",url,params={"api_key":"secret-one"}))["nested"]["value"] == 1
            await client.get("openalex",url,params={"api_key":"secret-two"})
            assert len(calls) == 2
            assert all("secret" not in key for key in client._cache)
        finally:
            await client.close()
    run(scenario())
def test_rate_limit_backoff_and_recovery(monkeypatch):
    sleeps,calls = [],[]
    async def fake_sleep(delay):
        sleeps.append(delay)
    monkeypatch.setattr("app.providers.asyncio.sleep",fake_sleep)
    def handler(req):
        calls.append(req)
        return httpx.Response(429,headers={"Retry-After":"2"},json={}) if len(calls)==1 else httpx.Response(200,json={"results":[]})
    async def scenario():
        client = ProviderClient(transport=httpx.MockTransport(handler))
        try:
            assert await client.get("openalex","https://api.openalex.org/works") == {"results":[]}
            assert sleeps == [2] and len(calls) == 2
        finally:
            await client.close()
    run(scenario())
def test_rate_limit_exhaustion_is_normalized(monkeypatch):
    async def no_sleep(delay):
        pass
    monkeypatch.setattr("app.providers.asyncio.sleep",no_sleep)
    async def scenario():
        client = ProviderClient(retries=1,transport=httpx.MockTransport(lambda req:httpx.Response(429,json={"error":"provider internal detail"})))
        try:
            with pytest.raises(ProviderFailure) as exc:
                await client.get("semantic_scholar","https://api.semanticscholar.org/graph/v1/paper/DOI:10.1234/test")
            assert exc.value.error.provider == "semantic_scholar"
            assert exc.value.error.code == "rate_limited"
            assert "internal" not in exc.value.error.message
        finally:
            await client.close()
    run(scenario())
def test_independent_provider_failure_does_not_prevent_openalex():
    def handler(req):
        if req.url.host == "api.semanticscholar.org":
            return httpx.Response(503,json={})
        return httpx.Response(200,json={"results":[{"id":"https://openalex.org/W1","title":"Glass"}]})
    async def scenario():
        client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderFailure):
                await SemanticScholar(client,{}).enrich(paper())
            assert len(await OpenAlex(client,{}).search("glass",search_request())) == 1
        finally:
            await client.close()
    run(scenario())
def test_timeout_normalization():
    def handler(req):
        raise httpx.ReadTimeout("secret query",request=req)
    async def scenario():
        client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderFailure) as exc:
                await client.get("openalex","https://api.openalex.org/works")
            assert exc.value.error.code == "timeout" and "secret" not in str(exc.value)
        finally:
            await client.close()
    run(scenario())
def test_redirects_not_followed_and_external_endpoints_rejected():
    calls = []
    def handler(req):
        calls.append(req)
        return httpx.Response(302,headers={"Location":"http://127.0.0.1/private"})
    async def scenario():
        client = ProviderClient(retries=0,transport=httpx.MockTransport(handler))
        try:
            with pytest.raises(ProviderFailure) as exc:
                await client.get("openalex","https://api.openalex.org/works")
            assert exc.value.error.code == "http_error" and len(calls)==1
            with pytest.raises(ProviderFailure) as exc:
                await client.get("openalex","http://127.0.0.1/private")
            assert exc.value.error.code == "invalid_endpoint" and len(calls)==1
        finally:
            await client.close()
    run(scenario())
def test_safe_rendering_and_sparse_abstract():
    assert plain_text("<script>alert(1)</script><b>Glass</b>") == "Glass"
    assert safe_url("javascript:alert(1)") is None
    assert safe_url("https://user:password@example.org") is None
    assert safe_url("https://example.org/x") == "https://example.org/x"
    assert _abstract_from_index({"Glass":[0],"unsafe":[10**12],"study":[1]}) == "Glass study"
    assert _abstract_from_index(None) is None
@pytest.mark.parametrize("payload",[[],"not JSON object",42])
def test_invalid_provider_response(payload):
    async def scenario():
        client = client_with(payload)
        try:
            with pytest.raises(ProviderFailure) as exc:
                await client.get("openalex","https://api.openalex.org/works")
            assert exc.value.error.code == "invalid_response"
        finally:
            await client.close()
    run(scenario())
