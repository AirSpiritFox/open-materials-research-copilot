export type PublicationType = "article" | "review" | "preprint" | "conference" | "dataset" | "other";
export type SourceBasis = "metadata" | "abstract";
export type Classification = "SUPPORTED" | "INFERRED" | "SPECULATIVE" | "UNKNOWN";
export interface Provenance {provider:string;record_id:string;retrieved_at:string;source_url:string|null;doi:string|null;oa_status:string|null;license:string|null;raw_record?:unknown;}
export interface Paper {id:string;title:string;authors:string[];year:number|null;journal:string|null;doi:string|null;publication_type:PublicationType;citations:Record<string,number>;is_oa:boolean|null;oa_url:string|null;pdf_url:string|null;abstract:string|null;provenance:Provenance[];source_basis:SourceBasis;}
export interface Strategy {kind:string;query:string;enabled:boolean;note?:string;filters?:string[];sort?:string;}
export interface Project {id:string;name:string;question:string;notes:string;papers:Paper[];searches:{question:string;queries:Strategy[]}[];created_at:string;}
export interface ProviderError {provider:string;code:string;message:string;}
export interface SearchInput {question:string;queries:Strategy[];year_from:number|null;year_to:number|null;oa_only:boolean;reviews_only:boolean;preprints_only:boolean;}
export interface SearchResult {papers:Paper[];errors:ProviderError[];queries:Strategy[];deduplicated:number;}
export interface Citation {paper_id:string;quote:string;basis:SourceBasis;}
export interface SynthesisResult {mode:string;basis:SourceBasis;statements:{classification:Classification;text:string;citations:Citation[]}[];limitations:string[];provider:string;question?:string;}
export type ExportFormat = "bibtex"|"ris"|"markdown"|"csv"|"json";
