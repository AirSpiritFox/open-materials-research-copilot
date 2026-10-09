import assert from "node:assert/strict";
import test from "node:test";
import {basicBrief,deduplicate,exportBibliography,fromCrossref,fromOpenAlex,generateStrategies,lookupDoi,normalizeDoi,reconstructAbstract,safeUrl,searchLiterature} from "../research";
import type {Paper,SearchInput} from "../types";
const record=(overrides:Record<string,unknown>={})=>({id:"https://openalex.org/W123",doi:"https://doi.org/10.1234/EXAMPLE",display_name:"An experimental glass study for testing",publication_year:2022,type:"article",authorships:[{author:{display_name:"A. Researcher"}}],primary_location:{source:{display_name:"Test journal"}},open_access:{is_oa:true,oa_status:"green",oa_url:"https://example.org/repository"},best_oa_location:{is_oa:true,landing_page_url:"https://example.org/repository",pdf_url:"https://example.org/paper.pdf",license:"cc-by"},abstract_inverted_index:{Synthetic:[0],fixture:[1],only:[2]},cited_by_count:4,...overrides});
const paper=(overrides:Partial<Paper>={}):Paper=>({...fromOpenAlex(record(),"2026-01-01T00:00:00Z"),...overrides});
const input=(q:string):SearchInput=>({question:q,queries:[{kind:"Direct keywords",query:q,enabled:true}],year_from:null,year_to:null,oa_only:false,reviews_only:false,preprints_only:false});
async function withFetch(implementation:typeof fetch,run:()=>Promise<void>){const previous=globalThis.fetch;globalThis.fetch=implementation;try{await run();}finally{globalThis.fetch=previous;}}
test("DOI normalization accepts URL and prefix, rejects malformed input",()=>{assert.equal(normalizeDoi(" https://doi.org/10.1234/ABC%2FTest "),"10.1234/abc/test");assert.equal(normalizeDoi("doi:10.1234/AbC"),"10.1234/abc");assert.equal(normalizeDoi("10.1234/example(2)"),"10.1234/example(2)");for(const invalid of [null,"","hello","10.1234/","10.1234/a b","javascript:10.1234/a"])assert.equal(normalizeDoi(invalid),null);});
test("unsafe metadata links are never executable",()=>{assert.equal(safeUrl("javascript:alert(1)"),null);assert.equal(safeUrl("data:text/html,test"),null);assert.equal(safeUrl("https://user:password@example.org"),null);assert.equal(safeUrl("https://example.org/paper"),"https://example.org/paper");});
test("abstract reconstruction handles missing and malformed offsets",()=>{assert.equal(reconstructAbstract(null),null);assert.equal(reconstructAbstract({glass:[1],Test:[0],invalid:[-1,9999999]}),"Test glass");assert.equal(paper({abstract:null,source_basis:"metadata"}).source_basis,"metadata");});
test("OA resolution trusts only provider-marked open locations",()=>{const closed=fromOpenAlex(record({open_access:{is_oa:false,oa_status:"closed"}}));assert.equal(closed.oa_url,null);assert.equal(closed.pdf_url,null);const open=fromOpenAlex(record());assert.equal(open.pdf_url,"https://example.org/paper.pdf");assert.equal(open.provenance[0].license,"cc-by");assert.equal(open.source_basis,"abstract");});
test("missing DOI and abstract remain null and metadata-only",()=>{const p=fromOpenAlex(record({doi:null,abstract_inverted_index:null,cited_by_count:null}));assert.equal(p.doi,null);assert.equal(p.abstract,null);assert.deepEqual(p.citations,{});assert.equal(p.source_basis,"metadata");});
test("deduplication retains provenance and separate provider citation counts",()=>{const a=paper(),b=fromCrossref({DOI:"10.1234/example",title:[a.title],type:"journal-article",published:{"date-parts":[[2022]]},author:[{given:"A.",family:"Researcher"}],"is-referenced-by-count":2});const [merged]=deduplicate([a,b]);assert.equal(deduplicate([a,b]).length,1);assert.deepEqual(merged.citations,{Crossref:2,OpenAlex:4});assert.equal(merged.provenance.length,2);assert.equal(merged.provenance[0].retrieved_at,"2026-01-01T00:00:00Z");assert.ok(merged.provenance[0].raw_record);assert.equal(merged.pdf_url,a.pdf_url);});
test("missing-DOI matching requires title, year and author",()=>{const a=paper();assert.equal(deduplicate([a,paper({id:"alternate",doi:null})]).length,1);assert.equal(deduplicate([a,paper({id:"alternate",doi:null,authors:[]})]).length,2);assert.equal(deduplicate([a,paper({id:"alternate",doi:"10.1234/different"})]).length,2);});
test("preprints are not relabelled peer reviewed during merge",()=>{assert.equal(deduplicate([paper(),paper({publication_type:"preprint"})])[0].publication_type,"preprint");});
test("seven editable strategies distinguish expansion from scientific equivalence",()=>{const strategies=generateStrategies("Tellurite TeO2 glass optical properties and thermal stability with rare earth dopants");assert.equal(strategies.length,7);assert.ok(strategies.every(s=>s.enabled&&s.query));assert.match(strategies[1].note!,/not a claim/);assert.match(strategies[2].query,/TeO2/);assert.match(strategies[3].query,/Tg/);});
test("source briefs cite exact abstract text and leave scientific gaps unknown",()=>{const result=basicBrief("glass",[paper()]);const extract=result.statements.find(s=>s.classification==="SUPPORTED")!;assert.equal(extract.citations[0].paper_id,paper().id);assert.ok(paper().abstract!.includes(extract.citations[0].quote));assert.equal(extract.citations[0].basis,"abstract");assert.ok(result.statements.some(s=>s.classification==="UNKNOWN"));assert.equal(result.provider,"Source extracts (no AI model)");const missing=basicBrief("glass",[paper({abstract:null,source_basis:"metadata"})]);assert.equal(missing.basis,"metadata");assert.equal(missing.statements.filter(s=>s.classification==="SUPPORTED").length,0);});
test("citation exports never invent unavailable metadata and CSV blocks formulas",()=>{const p=paper({authors:[],journal:null,year:null,doi:null,title:"=HYPERLINK(test)"});const bib=exportBibliography([p],"bibtex");assert.doesNotMatch(bib,/author =|journal =|year =|doi =/);assert.match(exportBibliography([p],"csv"),/'=HYPERLINK/);assert.match(exportBibliography([p],"ris"),/TY  - JOUR/);assert.equal(JSON.parse(exportBibliography([p],"json"))[0].doi,null);});
test("search exposes performed filters and deduplicates repeated records",async()=>{await withFetch(async()=>new Response(JSON.stringify({results:[record(),record()]}),{status:200}),async()=>{const result=await searchLiterature({...input("test-filter-a"),oa_only:true,year_from:2020});assert.equal(result.papers.length,1);assert.equal(result.deduplicated,1);assert.deepEqual(result.queries[0].filters,["from_publication_date:2020-01-01","is_oa:true"]);assert.equal(result.errors.length,0);});});
test("rate limiting is a normalized failure without breaking the app",async()=>{await withFetch(async()=>new Response("",{status:429,headers:{"Retry-After":"120"}}),async()=>{const result=await searchLiterature(input("test-rate-limit-b"));assert.equal(result.papers.length,0);assert.equal(result.errors[0].code,"RATE_LIMITED");});});
test("failed OpenAlex DOI lookup does not lose the Crossref result",async()=>{await withFetch(async url=>String(url).includes("crossref")?new Response(JSON.stringify({message:{DOI:"10.1234/provider-failure",title:["Provider survival"]}}),{status:200}):new Response("",{status:404}),async()=>{const result=await lookupDoi("10.1234/provider-failure");assert.equal(result.papers.length,1);assert.equal(result.papers[0].provenance[0].provider,"Crossref");assert.equal(result.papers[0].is_oa,null);assert.equal(result.errors[0].provider,"OpenAlex");});});
test("an already aborted request is cancelled before network access",async()=>{const controller=new AbortController();controller.abort();await assert.rejects(searchLiterature(input("cancelled-test"),controller.signal),{name:"AbortError"});});
test("cached metadata preserves original retrieval time and avoids a second fetch",async()=>{let calls=0;await withFetch(async()=>{calls++;return new Response(JSON.stringify({results:[record()]}),{status:200});},async()=>{const a=await searchLiterature(input("test-cache-c")),b=await searchLiterature(input("test-cache-c"));assert.equal(calls,1);assert.equal(a.papers[0].provenance[0].retrieved_at,b.papers[0].provenance[0].retrieved_at);});});

test("source quote verification preserves original whitespace",()=>{const p=paper({abstract:"Glass  measurements\nrequire explicit conditions."});const result=basicBrief("glass",[p]);const citation=result.statements[0].citations[0];assert.ok(p.abstract!.includes(citation.quote));});

test("Crossref fallback remains metadata-only and preserves provider failure",async()=>{
 await withFetch(async url=>String(url).includes("crossref")?new Response(JSON.stringify({message:{items:[{DOI:"10.1234/fallback-real-shape",title:["Fallback metadata fixture"],type:"journal-article"}]}}),{status:200}):new Response("",{status:429,headers:{"Retry-After":"120"}}),async()=>{
  const result=await searchLiterature(input("fallback-keywords-d"));
  assert.equal(result.papers.length,1);
  assert.equal(result.papers[0].is_oa,null);
  assert.equal(result.papers[0].source_basis,"metadata");
  assert.equal(result.papers[0].provenance[0].provider,"Crossref");
  assert.equal(result.errors[0].provider,"OpenAlex");
  assert.equal(result.queries.at(-1)?.kind,"Crossref metadata fallback");
 });
});

test("repeating a saved fallback strategy does not search the diagnostic row",async()=>{
 let calls=0;
 await withFetch(async()=>{calls++;return new Response(JSON.stringify({results:[]}),{status:200});},async()=>{
  const request=input("reused-fallback-e");
  request.queries.push({kind:"Crossref metadata fallback",query:"old fallback",enabled:true});
  const result=await searchLiterature(request);
  assert.equal(calls,1);
  assert.equal(result.queries.length,1);
 });
});
