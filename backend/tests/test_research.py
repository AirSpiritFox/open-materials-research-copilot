import pytest
from app.research import deduplicate, merge_papers, normalize_doi, strategy
from app.schemas import Paper, Provenance
def paper(**updates):
    data = dict(id="doi:10.1234/glass",title="Optical properties of tellurite glass",authors=["Alice Smith"],year=2024,journal="Example journal",doi="10.1234/glass",publication_type="article",citations={},is_oa=None,oa_url=None,pdf_url=None,abstract=None,source_basis="metadata",provenance=[])
    data.update(updates)
    return Paper(**data)
@pytest.mark.parametrize(("raw","expected"),[
    ("10.1234/ABC","10.1234/abc"),(" DOI: 10.1234/AbC ","10.1234/abc"),
    ("https://doi.org/10.1234/ABC","10.1234/abc"),
    ("http://dx.doi.org/10.1234/ABC?tracking=true","10.1234/abc"),
    ("https://doi.org/10.1234%2FABC","10.1234/abc"),
    ("10.1234/test(2024)","10.1234/test(2024)"),
])
def test_doi_normalization(raw,expected):
    assert normalize_doi(raw) == expected
@pytest.mark.parametrize("raw",["","not a doi","10.12/abc","https://evil.example/10.1234/abc","https://user:pass@doi.org/10.1234/abc","10.1234/white space","10.1234/<script>","javascript:10.1234/abc",None])
def test_invalid_doi(raw):
    with pytest.raises(ValueError):
        normalize_doi(raw)
def provenance(provider):
    return Provenance(provider=provider,record_id=provider+"-123",retrieved_at="2026-01-01T00:00:00+00:00",source_url="https://doi.org/10.1234/glass",doi="10.1234/glass",oa_status="unknown",license=None)
def test_same_doi_merges_sources_but_keeps_citation_counts_separate():
    first = paper(citations={"openalex":12},provenance=[provenance("openalex")])
    second = paper(id="other",doi="https://doi.org/10.1234/GLASS",citations={"crossref":8},abstract="An observation.",source_basis="abstract",provenance=[provenance("crossref")])
    result = deduplicate([first,second])
    assert len(result) == 1
    assert result[0].citations == {"openalex":12,"crossref":8}
    assert {p.provider for p in result[0].provenance} == {"openalex","crossref"}
    assert result[0].abstract == "An observation."
    assert result[0].source_basis == "abstract"
    assert first.abstract is None
def test_missing_doi_can_merge_only_with_sufficient_identity():
    result = deduplicate([paper(id="local:1",doi=None),paper()])
    assert len(result) == 1
    assert result[0].doi == "10.1234/glass"
    assert result[0].id == "doi:10.1234/glass"
def test_two_distinct_known_dois_never_merge_by_title():
    assert len(deduplicate([paper(),paper(id="other",doi="10.1234/different")])) == 2
def test_dedup_requires_known_year_and_first_author_without_doi():
    assert len(deduplicate([paper(id="local:a",doi=None,year=None),paper()])) == 2
    assert len(deduplicate([paper(id="local:b",doi=None,authors=[]),paper()])) == 2
    assert len(deduplicate([paper(id="local:c",doi=None,authors=["Another Author"]),paper()])) == 2
    assert len(deduplicate([paper(id="local:d",doi=None,title="Glass"),paper(title="Glass")])) == 2
def test_exact_source_identifier_deduplicates_sparse_metadata():
    p = paper(id="openalex:1",doi=None,year=None,authors=[])
    assert len(deduplicate([p,p])) == 1
def test_merge_rejects_distinct_doi():
    with pytest.raises(ValueError):
        merge_papers(paper(),paper(doi="10.1234/different"))
def test_duplicate_provenance_retained_once_and_preprint_not_promoted():
    result = merge_papers(paper(publication_type="preprint",provenance=[provenance("openalex")]),paper(publication_type="article",provenance=[provenance("openalex")]))
    assert result.publication_type == "preprint"
    assert len(result.provenance) == 1
def test_oa_resolution_enriches_without_asserting_fulltext_analysis():
    result = merge_papers(paper(is_oa=False),paper(is_oa=True,pdf_url="https://repository.example/p.pdf",oa_url="https://repository.example/p"))
    assert result.is_oa is True
    assert result.pdf_url == "https://repository.example/p.pdf"
    assert result.source_basis == "metadata"
    assert result.abstract is None
def test_query_strategies_are_editable_and_expansion_is_qualified():
    result = strategy("Find TeO2 tellurite glass for near-IR optical applications with rare-earth dopants and compare glass transition temperature.")
    assert len(result["queries"]) == 7
    assert len({q.kind for q in result["queries"]}) == 7
    assert all(q.enabled for q in result["queries"])
    combined = " ".join(q.query for q in result["queries"])
    assert "tellurium dioxide" in combined and "Tg" in combined
    assert any("equivalence" in note for note in result["notes"])
    assert any("year filters" in note for note in result["notes"])
    result["queries"][0].query = "my edited query"
    assert result["queries"][0].query == "my edited query"
def test_unknown_material_question_still_produces_queries_without_inventing_data():
    result = strategy("Compare aluminum alloy fatigue")
    assert len(result["queries"]) == 7
    assert all(q.query and "tellurite" not in q.query for q in result["queries"])
def test_empty_question_is_invalid():
    with pytest.raises(ValueError):
        strategy("  ")
