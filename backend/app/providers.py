"""Replaceable adapters for lawful bibliographic metadata and OA resolution."""
from __future__ import annotations
import asyncio
import copy
import hashlib
import html
import json
import random
import re
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import quote, urlsplit
import httpx
from app.research import merge_papers, normalize_doi, stable_id
from app.schemas import Paper, Provenance, ProviderError, SearchRequest

class ProviderFailure(Exception):
    def __init__(self, provider: str, code: str, message: str):
        self.error = ProviderError(provider=provider, code=code, message=message)
        super().__init__(message)
class LiteratureProvider(Protocol):
    name: str
    async def lookup(self, doi: str) -> Paper: ...
class EnrichmentProvider(Protocol):
    name: str
    async def enrich(self, paper: Paper) -> Paper: ...
class _TextParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.suppressed = 0
    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.suppressed += 1
        elif tag in {"p", "br", "div", "jats:p", "jats:title"}:
            self.parts.append(" ")
    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.suppressed = max(0, self.suppressed - 1)
        elif tag in {"p", "div", "jats:p", "jats:title"}:
            self.parts.append(" ")
    def handle_data(self, data):
        if not self.suppressed:
            self.parts.append(data)
def plain_text(value: Any, limit: int = 40000) -> str | None:
    if not isinstance(value, str):
        return None
    parser = _TextParser()
    try:
        parser.feed(value[:limit * 2])
        text = " ".join("".join(parser.parts).split())[:limit]
    except (ValueError, AssertionError):
        text = " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())[:limit]
    return text or None
def safe_url(value: Any) -> str | None:
    if not isinstance(value, str) or len(value) > 3000 or re.search(r"[\x00-\x20\x7f]", value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password:
            return None
        return value
    except ValueError:
        return None
def _doi(value: Any) -> str | None:
    try:
        return normalize_doi(value)
    except (ValueError, TypeError):
        return None
def _integer(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None
def _year(value: Any) -> int | None:
    value = _integer(value)
    return value if value is not None and 1000 <= value <= 2200 else None
def _bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
def _mapping(value: Any) -> dict:
    return value if isinstance(value, dict) else {}
def _sequence(value: Any) -> list:
    return value if isinstance(value, list) else []
def _first_text(value: Any) -> str | None:
    for item in _sequence(value):
        text = plain_text(item, 2000)
        if text:
            return text
    return None
def _provenance(provider, record_id, doi, url, is_oa=None, license_value=None):
    return Provenance(provider=provider, record_id=record_id[:1000], retrieved_at=datetime.now(timezone.utc).isoformat(), source_url=safe_url(url), doi=doi, oa_status="open" if is_oa is True else "closed" if is_oa is False else "unknown", license=plain_text(license_value, 2000))
def _abstract_from_index(index: Any) -> str | None:
    if not isinstance(index, dict):
        return None
    words: dict[int, str] = {}
    for word, positions in list(index.items())[:15000]:
        if not isinstance(word, str):
            continue
        for position in _sequence(positions)[:1000]:
            if isinstance(position, int) and not isinstance(position, bool) and 0 <= position < 50000:
                words.setdefault(position, word[:1000])
    return plain_text(" ".join(words[i] for i in sorted(words))) if words else None

class ProviderClient:
    """Timeout, bounded retry, hashed TTL cache, and normalized provider failures."""
    HOSTS = {"openalex": "api.openalex.org", "crossref": "api.crossref.org", "semantic_scholar": "api.semanticscholar.org", "unpaywall": "api.unpaywall.org"}
    def __init__(self, timeout: float = 12, retries: int = 2, transport=None):
        self.retries = max(0, min(int(retries), 4))
        self.ttl = 300.0
        self._cache: dict[str, tuple[float, dict]] = {}
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(timeout), follow_redirects=False, transport=transport, headers={"User-Agent": "OpenMaterialsResearchCopilot/0.1 (+open-source research app)"})
        self._semaphore = asyncio.Semaphore(6)
    async def close(self):
        await self._http.aclose()
    def _delay(self, response, attempt):
        header = response.headers.get("retry-after") if response is not None else None
        if header:
            try:
                delay = float(header)
            except ValueError:
                try:
                    retry_at = parsedate_to_datetime(header)
                    if retry_at.tzinfo is None:
                        retry_at = retry_at.replace(tzinfo=timezone.utc)
                    delay = (retry_at - datetime.now(timezone.utc)).total_seconds()
                except (ValueError, TypeError, OverflowError):
                    delay = 0.5 * 2 ** attempt
            return max(0, min(86400.0, delay))
        return min(5.0, 0.5 * 2 ** attempt + random.random() * 0.15)
    async def get(self, provider: str, url: str, params=None, headers=None) -> dict:
        parsed = urlsplit(url)
        if (parsed.scheme != "https" or parsed.hostname != self.HOSTS.get(provider) or parsed.username or parsed.password or parsed.port not in {None, 443}):
            raise ProviderFailure(provider, "invalid_endpoint", "Provider endpoint is not permitted.")
        key = hashlib.sha256(json.dumps([provider, url, params or {}, headers or {}], sort_keys=True, default=str).encode()).hexdigest()
        cached = self._cache.get(key)
        if cached and cached[0] > time.monotonic():
            return copy.deepcopy(cached[1])
        for attempt in range(self.retries + 1):
            response = None
            try:
                async with self._semaphore:
                    response = await self._http.get(url, params=params, headers=headers)
            except httpx.TimeoutException:
                if attempt < self.retries:
                    await asyncio.sleep(self._delay(None, attempt))
                    continue
                raise ProviderFailure(provider, "timeout", "The provider timed out. Try again later.") from None
            except httpx.RequestError:
                if attempt < self.retries:
                    await asyncio.sleep(self._delay(None, attempt))
                    continue
                raise ProviderFailure(provider, "unavailable", "The provider could not be reached.") from None
            if response.status_code == 429 or response.status_code in {500, 502, 503, 504}:
                if attempt < self.retries:
                    delay = self._delay(response, attempt)
                    if delay <= 5.0:
                        await asyncio.sleep(delay)
                        continue
                code = "rate_limited" if response.status_code == 429 else "unavailable"
                message = "Provider rate limit reached. Try again later." if code == "rate_limited" else "Provider is temporarily unavailable."
                raise ProviderFailure(provider, code, message)
            if response.status_code == 404:
                raise ProviderFailure(provider, "not_found", "No provider record was found for this identifier.")
            if response.status_code in {401, 403}:
                raise ProviderFailure(provider, "unauthorized", "Provider access was refused. Check its configuration.")
            if not 200 <= response.status_code < 300:
                raise ProviderFailure(provider, "http_error", "The provider returned an unsuccessful response.")
            if len(response.content) > 8 * 1024 * 1024:
                raise ProviderFailure(provider, "invalid_response", "The provider response exceeded the size limit.")
            try:
                data = response.json()
                if not isinstance(data, dict):
                    raise ValueError("Expected an object")
            except (ValueError, UnicodeDecodeError):
                raise ProviderFailure(provider, "invalid_response", "The provider returned invalid metadata.") from None
            if len(self._cache) >= 512:
                self._cache.pop(next(iter(self._cache)))
            self._cache[key] = (time.monotonic() + self.ttl, copy.deepcopy(data))
            return data
        raise ProviderFailure(provider, "unavailable", "The provider is unavailable.")

class OpenAlex:
    name = "openalex"
    def __init__(self, client: ProviderClient, config: dict):
        self.client, self.config = client, config
    def _params(self):
        return {"api_key": self.config["openalex_api_key"]} if self.config.get("openalex_api_key") else {}
    def _paper(self, record):
        doi = _doi(record.get("doi"))
        record_id = str(record.get("id") or doi or hashlib.sha256(json.dumps(record, sort_keys=True, default=str).encode()).hexdigest())
        abstract = _abstract_from_index(record.get("abstract_inverted_index"))
        oa = _mapping(record.get("open_access"))
        is_oa = _bool(oa.get("is_oa"))
        location = _mapping(record.get("best_oa_location"))
        if not location:
            location = next((loc for loc in _sequence(record.get("locations")) if isinstance(loc, dict) and loc.get("is_oa") is True), {})
        location_open = location.get("is_oa") is True or (bool(location) and is_oa is True)
        if location.get("is_oa") is False:
            location_open = False
        if location_open:
            is_oa = True
        source = _mapping(_mapping(record.get("primary_location")).get("source"))
        authors = [name for item in _sequence(record.get("authorships"))[:200] if (name := plain_text(_mapping(_mapping(item).get("author")).get("display_name"), 300))]
        publication_type = {"article": "article", "review": "review", "preprint": "preprint", "proceedings-article": "conference", "conference-paper": "conference", "dataset": "dataset"}.get(record.get("type"), "other")
        count = _integer(record.get("cited_by_count"))
        return Paper(id=stable_id(self.name, record_id, doi), title=plain_text(record.get("display_name") or record.get("title"), 2000) or "Untitled record", authors=authors, year=_year(record.get("publication_year")), journal=plain_text(source.get("display_name"), 1000), doi=doi, publication_type=publication_type, citations={self.name: count} if count is not None else {}, is_oa=is_oa, oa_url=safe_url(location.get("landing_page_url") or location.get("pdf_url")) if location_open else None, pdf_url=safe_url(location.get("pdf_url")) if location_open else None, abstract=abstract, source_basis="abstract" if abstract else "metadata", provenance=[_provenance(self.name, record_id, doi, record.get("id"), is_oa, location.get("license"))])
    async def search(self, query: str, filters: SearchRequest, sort: str | None = None) -> list[Paper]:
        params = {**self._params(), "search": query[:1500], "per_page": 25}
        if sort in {"cited_by_count:desc", "publication_date:desc"}:
            params["sort"] = sort
        constraints = []
        if filters.year_from is not None:
            constraints.append(f"from_publication_date:{filters.year_from}-01-01")
        if filters.year_to is not None:
            constraints.append(f"to_publication_date:{filters.year_to}-12-31")
        if filters.oa_only:
            constraints.append("open_access.is_oa:true")
        if filters.reviews_only:
            constraints.append("type:review")
        if filters.preprints_only:
            constraints.append("type:preprint")
        if constraints:
            params["filter"] = ",".join(constraints)
        data = await self.client.get(self.name, "https://api.openalex.org/works", params=params)
        if not isinstance(data.get("results"), list):
            raise ProviderFailure(self.name, "invalid_response", "OpenAlex returned no valid result list.")
        return [self._paper(record) for record in data["results"][:100] if isinstance(record, dict)]
    async def lookup(self, doi: str) -> Paper:
        doi = normalize_doi(doi)
        record = await self.client.get(self.name, "https://api.openalex.org/works/https://doi.org/" + quote(doi, safe=""), params=self._params())
        if not record.get("id"):
            raise ProviderFailure(self.name, "invalid_response", "OpenAlex returned no work identifier.")
        return self._paper(record)

class Crossref:
    name = "crossref"
    def __init__(self, client: ProviderClient, config: dict):
        self.client, self.config = client, config
    async def lookup(self, doi: str) -> Paper:
        doi = normalize_doi(doi)
        params = {"mailto": self.config["crossref_email"]} if self.config.get("crossref_email") else {}
        data = await self.client.get(self.name, "https://api.crossref.org/works/" + quote(doi, safe=""), params=params)
        record = _mapping(data.get("message"))
        if not record.get("DOI") or _doi(record.get("DOI")) != doi:
            raise ProviderFailure(self.name, "invalid_response", "Crossref returned no matching DOI metadata.")
        authors = []
        for author in _sequence(record.get("author"))[:200]:
            author = _mapping(author)
            name = plain_text(" ".join(str(author.get(k) or "") for k in ("given", "family")), 300)
            name = name or plain_text(author.get("name"), 300)
            if name:
                authors.append(name)
        year = None
        for key in ("published", "published-print", "published-online", "issued"):
            dates = _sequence(_mapping(record.get(key)).get("date-parts"))
            first = _sequence(dates[0]) if dates else []
            if first and (year := _year(first[0])) is not None:
                break
        publication_type = {"journal-article": "article", "proceedings-article": "conference", "posted-content": "preprint", "dataset": "dataset"}.get(record.get("type"), "other")
        abstract = plain_text(record.get("abstract"))
        count = _integer(record.get("is-referenced-by-count"))
        licenses = _sequence(record.get("license"))
        license_value = safe_url(_mapping(licenses[0]).get("URL")) if licenses else None
        return Paper(id=stable_id(self.name, doi, doi), title=_first_text(record.get("title")) or "Untitled record", authors=authors, year=year, journal=_first_text(record.get("container-title")), doi=doi, publication_type=publication_type, citations={self.name: count} if count is not None else {}, is_oa=None, oa_url=None, pdf_url=None, abstract=abstract, source_basis="abstract" if abstract else "metadata", provenance=[_provenance(self.name, doi, doi, record.get("URL") or "https://doi.org/" + doi, license_value=license_value)])

class SemanticScholar:
    name = "semantic_scholar"
    def __init__(self, client: ProviderClient, config: dict):
        self.client, self.config = client, config
    async def enrich(self, paper: Paper) -> Paper:
        if not paper.doi:
            return paper
        doi = normalize_doi(paper.doi)
        headers = {"x-api-key": self.config["semantic_scholar_api_key"]} if self.config.get("semantic_scholar_api_key") else {}
        record = await self.client.get(self.name, "https://api.semanticscholar.org/graph/v1/paper/DOI:" + quote(doi, safe=""), params={"fields": "paperId,title,authors,year,venue,externalIds,abstract,citationCount,isOpenAccess,openAccessPdf,publicationTypes,url"}, headers=headers)
        if not record.get("paperId"):
            raise ProviderFailure(self.name, "invalid_response", "Semantic Scholar returned no paper identifier.")
        supplied_doi = _doi(_mapping(record.get("externalIds")).get("DOI"))
        if supplied_doi and supplied_doi != doi:
            raise ProviderFailure(self.name, "invalid_response", "Semantic Scholar returned a different DOI.")
        is_oa = _bool(record.get("isOpenAccess"))
        pdf = _mapping(record.get("openAccessPdf"))
        pdf_url = safe_url(pdf.get("url")) if is_oa is True else None
        abstract = plain_text(record.get("abstract"))
        count = _integer(record.get("citationCount"))
        kinds = _sequence(record.get("publicationTypes"))
        publication_type = "review" if "Review" in kinds else "conference" if "Conference" in kinds else "other"
        record_id = str(record["paperId"])
        extra = Paper(id=stable_id(self.name, record_id, doi), title=plain_text(record.get("title"), 2000) or "Untitled record", authors=[name for a in _sequence(record.get("authors"))[:200] if (name := plain_text(_mapping(a).get("name"), 300))], year=_year(record.get("year")), journal=plain_text(record.get("venue"), 1000), doi=doi, publication_type=publication_type, citations={self.name: count} if count is not None else {}, is_oa=is_oa, oa_url=pdf_url, pdf_url=pdf_url, abstract=abstract, source_basis="abstract" if abstract else "metadata", provenance=[_provenance(self.name, record_id, doi, record.get("url"), is_oa, pdf.get("license"))])
        return merge_papers(paper, extra)

class Unpaywall:
    name = "unpaywall"
    def __init__(self, client: ProviderClient, config: dict):
        self.client, self.config = client, config
    async def enrich(self, paper: Paper) -> Paper:
        if not paper.doi:
            return paper
        email = self.config.get("unpaywall_email")
        if not email:
            raise ProviderFailure(self.name, "not_configured", "Add a contact email in Settings to use Unpaywall.")
        doi = normalize_doi(paper.doi)
        record = await self.client.get(self.name, "https://api.unpaywall.org/v2/" + quote(doi, safe=""), params={"email": email})
        if _doi(record.get("doi")) != doi:
            raise ProviderFailure(self.name, "invalid_response", "Unpaywall returned no matching DOI.")
        is_oa = _bool(record.get("is_oa"))
        location = _mapping(record.get("best_oa_location")) if is_oa is True else {}
        extra = Paper(id=paper.id, title=paper.title, authors=[], year=None, journal=None, doi=doi, publication_type="other", citations={}, is_oa=is_oa, oa_url=safe_url(location.get("url_for_landing_page") or location.get("url") or location.get("url_for_pdf")), pdf_url=safe_url(location.get("url_for_pdf")), abstract=None, source_basis="metadata", provenance=[_provenance(self.name, doi, doi, "https://doi.org/" + doi, is_oa, location.get("license"))])
        return merge_papers(paper, extra)
