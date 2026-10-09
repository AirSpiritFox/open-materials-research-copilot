"""Conservative query planning, identifier normalization, and record merging."""
from __future__ import annotations
import hashlib
import re
import unicodedata
from urllib.parse import unquote, urlsplit
from app.schemas import Paper, Query

def normalize_doi(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("DOI must be a string")
    value = value.strip()
    if value.lower().startswith(("http://", "https://")):
        parsed = urlsplit(value)
        if (parsed.hostname or "").lower() not in {"doi.org", "dx.doi.org"}:
            raise ValueError("Expected a doi.org URL or DOI identifier")
        if parsed.username or parsed.password:
            raise ValueError("DOI URL must not contain credentials")
        value = unquote(parsed.path.lstrip("/"))
    else:
        value = unquote(re.sub(r"^doi:\s*", "", value, flags=re.I))
    value = value.strip().lower()
    if len(value) > 300 or not re.fullmatch(r'10\.\d{4,9}/[^\s<>"\x00-\x1f\x7f]+', value):
        raise ValueError("Invalid DOI identifier")
    return value

def stable_id(provider: str, record_id: str, doi: str | None = None) -> str:
    if doi:
        return "doi:" + normalize_doi(doi)
    return provider + ":" + hashlib.sha256(record_id.encode()).hexdigest()[:24]

def _title(value: str) -> str:
    return re.sub(r"[^\w]+", " ", unicodedata.normalize("NFKC", value).casefold()).strip()

def merge_papers(a: Paper, b: Paper) -> Paper:
    """Fill absent metadata, retaining all provenance and separate provider counts."""
    if a.doi and b.doi and normalize_doi(a.doi) != normalize_doi(b.doi):
        raise ValueError("Cannot merge papers with distinct DOIs")
    provenance, seen = [], set()
    for entry in [*a.provenance, *b.provenance]:
        key = (entry.provider, entry.record_id, entry.retrieved_at)
        if key not in seen:
            seen.add(key)
            provenance.append(entry)
    abstract = a.abstract or b.abstract
    publication_type = a.publication_type
    if publication_type == "other":
        publication_type = b.publication_type
    if "preprint" in {a.publication_type, b.publication_type}:
        publication_type = "preprint"
    oa = True if a.is_oa is True or b.is_oa is True else (False if a.is_oa is False or b.is_oa is False else None)
    return a.model_copy(update={
        "id": b.id if not a.doi and b.doi else a.id,
        "title": a.title if a.title and a.title != "Untitled record" else b.title,
        "authors": a.authors or b.authors, "year": a.year or b.year,
        "journal": a.journal or b.journal, "doi": a.doi or b.doi,
        "publication_type": publication_type, "citations": {**a.citations, **b.citations},
        "is_oa": oa, "oa_url": a.oa_url or b.oa_url, "pdf_url": a.pdf_url or b.pdf_url,
        "abstract": abstract, "source_basis": "abstract" if abstract else "metadata",
        "provenance": provenance,
    })

def deduplicate(papers: list[Paper]) -> list[Paper]:
    result: list[Paper] = []
    for paper in papers:
        candidate = paper
        if paper.doi:
            try:
                candidate = paper.model_copy(update={"doi": normalize_doi(paper.doi)})
            except ValueError:
                candidate = paper.model_copy(update={"doi": None})
        found = None
        for i, previous in enumerate(result):
            if candidate.doi and previous.doi:
                if candidate.doi == previous.doi:
                    found = i
                    break
                continue
            if candidate.id == previous.id:
                found = i
                break
            title = _title(candidate.title)
            if (len(title) >= 16 and title != "untitled record"
                and title == _title(previous.title)
                and candidate.year is not None and candidate.year == previous.year
                and candidate.authors and previous.authors
                and _title(candidate.authors[0]) == _title(previous.authors[0])):
                found = i
                break
        if found is None:
            result.append(candidate)
        else:
            result[found] = merge_papers(result[found], candidate)
    return result

def strategy(question: str) -> dict:
    """Seven editable, transparent keyword searches without an LLM."""
    question = " ".join(question.split())[:3000]
    if not question:
        raise ValueError("Enter a research question")
    lower = question.casefold()
    stop = {"a", "an", "the", "and", "or", "for", "of", "to", "in", "on", "with", "find", "investigate", "identify", "compare", "what", "which", "how", "studied", "containing", "applications", "their", "its", "is", "are", "that", "this", "by", "from", "into", "using", "please", "research"}
    terms = re.findall(r"[A-Za-z][A-Za-z0-9+\-]*", question)
    keywords = list(dict.fromkeys(t for t in terms if t.casefold() not in stop))
    direct = (" ".join(keywords[:12]) or question)[:1500]
    related, material_terms, property_terms = [], [], []
    notes = ["Queries are editable keyword suggestions. Review each before searching.", "Related terminology broadens discovery; it does not assert scientific equivalence.", "Recent and foundational labels are search intentions; use year filters to enforce dates."]
    if any(term in lower for term in ("tellurite", "teo2", "tellurium dioxide")):
        material_terms.extend(["tellurite glass", "TeO2"])
        related.extend(["tellurium dioxide", "tellurite"])
    if any(term in lower for term in ("rare-earth", "rare earth", "lanthanide")):
        related.extend(["rare earth", "lanthanide", "RE-doped"])
    if any(term in lower for term in ("glass transition", "tg", "thermal")):
        property_terms.extend(["glass transition temperature", "Tg", "thermal stability"])
    if any(term in lower for term in ("optical", "visible", "near-ir", "near infrared", "display")):
        property_terms.extend(["optical absorption", "photoluminescence", "refractive index"])
        related.extend(["near infrared", "NIR", "luminescence"])
    if "volumetric" in lower:
        related.extend(["upconversion", "volumetric display"])
        notes.append("Upconversion is a related optical mechanism, not evidence of display suitability.")
    formulas = re.findall(r"\b(?:[A-Z][a-z]?\d*){2,}\b", question)
    material_terms.extend(formulas)
    if not material_terms:
        material_terms = keywords[:5]
    base = (material_terms[0] if material_terms else direct)[:500]
    property_query = base + " " + ("(" + " OR ".join('"' + term + '"' for term in dict.fromkeys(property_terms)) + ")" if property_terms else "properties")
    expansions = "(" + " OR ".join('"' + term + '"' for term in dict.fromkeys(related)) + ")" if related else "characterization"
    return {"queries": [
        Query(kind="direct", query=direct),
        Query(kind="synonym", query=(base + " " + expansions).strip()),
        Query(kind="composition", query=base + " composition"),
        Query(kind="property", query=property_query),
        Query(kind="review", query=base + " review"),
        Query(kind="recent", query=base + " recent advances"),
        Query(kind="foundational", query=base + " experimental"),
    ], "notes": notes}
