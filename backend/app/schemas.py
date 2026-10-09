from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Provenance(StrictModel):
    provider: str = Field(max_length=100)
    record_id: str = Field(max_length=1000)
    retrieved_at: str = Field(max_length=100)
    source_url: str | None = Field(default=None, max_length=3000)
    doi: str | None = Field(default=None, max_length=300)
    oa_status: str | None = Field(default=None, max_length=100)
    license: str | None = Field(default=None, max_length=2000)
    raw_record: dict[str, Any] | None = None

class Paper(StrictModel):
    id: str = Field(min_length=1, max_length=500)
    title: str = Field(min_length=1, max_length=5000)
    authors: list[str] = Field(default_factory=list, max_length=300)
    year: int | None = Field(default=None, ge=1000, le=2200)
    journal: str | None = Field(default=None, max_length=2000)
    doi: str | None = Field(default=None, max_length=300)
    publication_type: Literal["article","review","preprint","conference","dataset","other"] = "other"
    citations: dict[str, int] = Field(default_factory=dict)
    is_oa: bool | None = None
    oa_url: str | None = Field(default=None, max_length=3000)
    pdf_url: str | None = Field(default=None, max_length=3000)
    abstract: str | None = Field(default=None, max_length=40000)
    provenance: list[Provenance] = Field(default_factory=list, max_length=100)
    source_basis: Literal["metadata","abstract"] = "metadata"

    @field_validator("oa_url", "pdf_url")
    @classmethod
    def external_url(cls, value):
        if value is not None:
            from urllib.parse import urlsplit
            parsed = urlsplit(value)
            if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
                raise ValueError("Only HTTP(S) source links are supported")
        return value

    @model_validator(mode="after")
    def honest_basis(self):
        self.source_basis = "abstract" if self.abstract else "metadata"
        return self

class Query(StrictModel):
    kind: str = Field(max_length=100)
    query: str = Field(min_length=1, max_length=1500)
    enabled: bool = True
    note: str | None = Field(default=None, max_length=1500)
    filters: list[str] | None = Field(default=None, max_length=20)
    sort: str | None = Field(default=None, max_length=100)

class Question(StrictModel):
    question: str = Field(min_length=3, max_length=3000)

class SearchRequest(Question):
    queries: list[Query] = Field(default_factory=list, max_length=7)
    year_from: int | None = Field(default=None, ge=1000, le=2200)
    year_to: int | None = Field(default=None, ge=1000, le=2200)
    oa_only: bool = False
    reviews_only: bool = False
    preprints_only: bool = False

    @model_validator(mode="after")
    def valid_years(self):
        if self.reviews_only and self.preprints_only:
            raise ValueError("Select reviews or preprints, not both")
        if self.year_from and self.year_to and self.year_from > self.year_to:
            raise ValueError("Start year must not exceed end year")
        return self

class ProviderError(StrictModel):
    provider: str
    code: str
    message: str

class ProjectCreate(StrictModel):
    name: str = Field(min_length=1, max_length=200)
    question: str = Field(default="", max_length=3000)
    @field_validator("name")
    @classmethod
    def nonempty(cls, value):
        if not value.strip():
            raise ValueError("Project name cannot be blank")
        return value.strip()

class SavePaper(StrictModel):
    paper: Paper
class Notes(StrictModel):
    content: str = Field(max_length=100000)
class SavedSearch(Question):
    queries: list[Query] = Field(max_length=8)
class DOIRequest(StrictModel):
    doi: str = Field(min_length=3, max_length=500)
class SynthesisRequest(Question):
    papers: list[Paper] = Field(default_factory=list, max_length=30)
    mode: Literal["Explore","Evidence Review","Compare Materials","Hypothesis"] = "Evidence Review"
class SettingsUpdate(StrictModel):
    llm_provider: Literal["none","openai","ollama"] | None = None
    openai_api_key: str | None = Field(default=None, max_length=2000)
    openai_model: str | None = Field(default=None, max_length=200)
    openalex_api_key: str | None = Field(default=None, max_length=2000)
    semantic_scholar_api_key: str | None = Field(default=None, max_length=2000)
    unpaywall_email: str | None = Field(default=None, max_length=320)
    crossref_email: str | None = Field(default=None, max_length=320)
    @field_validator("unpaywall_email", "crossref_email")
    @classmethod
    def valid_contact(cls, value):
        import re
        if value and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid contact email")
        return value
