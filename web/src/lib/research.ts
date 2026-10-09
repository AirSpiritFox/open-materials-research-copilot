import type {ExportFormat,Paper,ProviderError,PublicationType,SearchInput,SearchResult,Strategy,SynthesisResult} from "./types";
export type {Paper,Project,SearchInput,SearchResult,Strategy,SynthesisResult} from "./types";
const OPENALEX="https://api.openalex.org/works",CROSSREF="https://api.crossref.org/works";
type Obj=Record<string,unknown>;
const object=(value:unknown):Obj=>value!==null&&typeof value==="object"&&!Array.isArray(value)?value as Obj:{};
const array=(value:unknown):unknown[]=>Array.isArray(value)?value:[];
const str=(value:unknown):string|null=>typeof value==="string"&&value.trim()?value.trim():null;
const integer=(value:unknown):number|null=>typeof value==="number"&&Number.isSafeInteger(value)&&value>=0?value:null;
export function safeUrl(value:unknown):string|null{if(typeof value!=="string")return null;try{const u=new URL(value);return ["https:","http:"].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
export function normalizeDoi(value:unknown):string|null{
 if(typeof value!=="string")return null;let doi=value.trim();
 if(/^https?:\/\/(?:dx\.)?doi\.org\//i.test(doi)){try{doi=new URL(doi).pathname.slice(1);}catch{return null;}}
 else doi=doi.replace(/^doi\s*:\s*/i,"");
 try{doi=decodeURIComponent(doi);}catch{return null;}doi=doi.trim().toLowerCase();
 return /^10\.\d{4,9}\/[^\s<>"]+$/.test(doi)&&doi.length<=512?doi:null;
}
const STOP=new Set("a an and are as at be by for from how in into is it of on or that the their these this to using with find investigate identify compare studied experimentally containing applications what still requires major strongest candidates relevant".split(" "));
const terms=(question:string)=>question.replace(/[^\p{L}\p{N}\s-]/gu," ").split(/\s+/).filter(t=>t.length>1&&!STOP.has(t.toLowerCase()));
const quote=(value:string)=>'"'+value.replace(/["\\]/g," ").trim()+'"';
export function generateStrategies(question:string):Strategy[]{
 const q=question.trim().slice(0,2000);if(!q)return [];const tokens=terms(q),tellurite=/tellurite|tellurium dioxide|TeO2/i.test(q),glass=/glass/i.test(q);
 const material=tellurite?'"tellurite glass"':glass?quote(tokens.find(t=>/glass/i.test(t))||"glass"):tokens.slice(0,3).join(" ");
 const direct=tokens.slice(0,10).join(" ")||q.slice(0,250);
 const formulae=Array.from(new Set(q.match(/\b(?:[A-Z][a-z]?\d*){2,}\b/g)||[]));
 const properties=[/optic|optical|visible|near.?IR|lumines|display/i.test(q)?'("optical" OR "luminescence" OR "refractive index")':"",/thermal|glass.?transition|\bTg\b/i.test(q)?'("glass transition temperature" OR "Tg" OR "thermal stability")':"",/band.?gap/i.test(q)?'("band gap" OR "bandgap")':"",/density/i.test(q)?'"density"':"",/elastic|modul/i.test(q)?'("elastic modulus" OR "Young modulus")':""].filter(Boolean);
 const synonymMaterial=tellurite?'("tellurite" OR "tellurium dioxide" OR "TeO2")':material;
 const dopants=/rare.?earth|lanthanide/i.test(q)?'("rare earth" OR "lanthanide")':/dopan/i.test(q)?'"doped"':"";
 return [
 {kind:"Direct keywords",query:direct,enabled:true,note:"Keywords retained from your question; edit before searching."},
 {kind:"Related terminology",query:[synonymMaterial,dopants,glass?'"glass"':""].filter(Boolean).join(" "),enabled:true,note:"Related discovery terms, not a claim that substances or properties are equivalent."},
 {kind:"Material / composition",query:[formulae.length?"("+formulae.map(quote).join(" OR ")+")":material,'("composition" OR "synthesis")',dopants].filter(Boolean).join(" "),enabled:true},
 {kind:"Property specific",query:[material,properties[0]||'"properties"',properties[1]||""].filter(Boolean).join(" "),enabled:true,note:"Tg and thermal stability are related search concepts, not interchangeable measured quantities."},
 {kind:"Review papers",query:material+' ("review" OR "overview")',enabled:true,note:"Review classification is filtered separately where supplied by OpenAlex."},
 {kind:"Recent literature",query:material+(properties[0]?" "+properties[0]:""),enabled:true,note:"Uses a publication-year filter covering the last five calendar years."},
 {kind:"Foundational candidates",query:material,enabled:true,note:"Older papers sorted by OpenAlex citation count; age and citations do not establish scientific quality."}
 ];
}
function plainText(value:unknown):string|null{const text=str(value);if(!text)return null;return text.replace(/<[^>]*>/g," ").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&amp;/g,"&").replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/\s+/g," ").trim().slice(0,60000)||null;}
export function reconstructAbstract(value:unknown):string|null{const index=object(value),words:(string|undefined)[]=[];for(const [word,positions]of Object.entries(index))for(const p of array(positions))if(typeof p==="number"&&Number.isInteger(p)&&p>=0&&p<12000)words[p]=word;return words.length?words.map(w=>w??"").join(" ").trim()||null:null;}
function publicationType(value:unknown):PublicationType{if(value==="posted-content"||value==="preprint")return "preprint";if(value==="review")return "review";if(value==="proceedings-article"||value==="conference-paper")return "conference";if(value==="dataset")return "dataset";if(value==="journal-article"||value==="article")return "article";return "other";}
export function fromOpenAlex(value:unknown,retrievedAt=new Date().toISOString()):Paper{
 const work=object(value),doi=normalizeDoi(work.doi),primary=object(work.primary_location),access=object(work.open_access);
 const isOa=typeof access.is_oa==="boolean"?access.is_oa:null;
 const oaLocations=[object(work.best_oa_location),...array(work.locations).map(object)].filter(location=>location.is_oa===true),location=oaLocations[0]||{};
 const abstract=reconstructAbstract(work.abstract_inverted_index),recordId=str(work.id)||(doi?"https://doi.org/"+doi:"");if(!recordId)throw new Error("OpenAlex returned a record without an identifier.");
 const citations=integer(work.cited_by_count);
 return {id:"openalex:"+recordId.split("/").pop(),title:plainText(work.display_name)||plainText(work.title)||"Untitled record",authors:array(work.authorships).map(a=>str(object(object(a).author).display_name)).filter((a):a is string=>a!==null),year:integer(work.publication_year),journal:str(object(primary.source).display_name),doi,publication_type:publicationType(work.type),citations:citations===null?{}:{OpenAlex:citations},is_oa:isOa,oa_url:isOa===true?safeUrl(location.landing_page_url)||safeUrl(access.oa_url)||safeUrl(location.pdf_url):null,pdf_url:isOa===true?safeUrl(location.pdf_url):null,abstract,source_basis:abstract?"abstract":"metadata",provenance:[{provider:"OpenAlex",record_id:recordId,retrieved_at:retrievedAt,source_url:safeUrl(recordId),doi,oa_status:str(access.oa_status),license:str(location.license),raw_record:work}]};
}
export function fromCrossref(value:unknown,retrievedAt=new Date().toISOString()):Paper{
 const work=object(value),doi=normalizeDoi(work.DOI);if(!doi)throw new Error("Crossref returned a record without a valid DOI.");
 const parts=array(object(work.published)["date-parts"]),year=integer(array(parts[0])[0]),abstract=plainText(work.abstract),citations=integer(work["is-referenced-by-count"]);
 return {id:"doi:"+doi,title:plainText(array(work.title)[0])||"Untitled record",authors:array(work.author).map(a=>{const author=object(a);return [str(author.given),str(author.family)].filter(Boolean).join(" ")||str(author.name)||"";}).filter(Boolean),year,journal:str(array(work["container-title"])[0]),doi,publication_type:publicationType(work.type),citations:citations===null?{}:{Crossref:citations},is_oa:null,oa_url:null,pdf_url:null,abstract,source_basis:abstract?"abstract":"metadata",provenance:[{provider:"Crossref",record_id:doi,retrieved_at:retrievedAt,source_url:safeUrl(work.URL)||"https://doi.org/"+doi,doi,oa_status:null,license:str(object(array(work.license)[0]).URL),raw_record:work}]};
}
const titleKey=(paper:Paper)=>paper.title.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}]/gu,"");
const authorKey=(author:string)=>author.toLowerCase().normalize("NFKD").replace(/[^\p{L}\p{N}]/gu,"");
function samePaper(a:Paper,b:Paper):boolean{
 const ad=normalizeDoi(a.doi),bd=normalizeDoi(b.doi);if(ad&&bd)return ad===bd;if(a.id===b.id)return true;
 const ak=titleKey(a),bk=titleKey(b);if(ak.length<20||ak!==bk||!a.year||a.year!==b.year)return false;
 return a.authors.length>0&&b.authors.length>0&&authorKey(a.authors[0])===authorKey(b.authors[0]);
}
function mergePapers(a:Paper,b:Paper):Paper{
 const provenance=[...a.provenance];for(const p of b.provenance)if(!provenance.some(x=>x.provider===p.provider&&x.record_id===p.record_id&&x.retrieved_at===p.retrieved_at))provenance.push(p);
 const abstract=a.abstract||b.abstract,isOa=a.is_oa===true||b.is_oa===true?true:a.is_oa??b.is_oa;
 return {...a,doi:normalizeDoi(a.doi)||normalizeDoi(b.doi),authors:a.authors.length?a.authors:b.authors,title:a.title==="Untitled record"?b.title:a.title,year:a.year??b.year,journal:a.journal||b.journal,publication_type:a.publication_type==="preprint"||b.publication_type==="preprint"?"preprint":a.publication_type==="other"?b.publication_type:a.publication_type,citations:{...b.citations,...a.citations},is_oa:isOa,oa_url:a.oa_url||b.oa_url,pdf_url:a.pdf_url||b.pdf_url,abstract,source_basis:abstract?"abstract":"metadata",provenance};
}
export function deduplicate(papers:Paper[]):Paper[]{const result:Paper[]=[];for(const paper of papers){const i=result.findIndex(existing=>samePaper(existing,paper));if(i<0)result.push({...paper,doi:normalizeDoi(paper.doi),provenance:[...paper.provenance]});else result[i]=mergePapers(result[i],paper);}return result;}

class ProviderRequestError extends Error{constructor(public provider:string,public code:string,message:string){super(message);}}
const cache=new Map<string,{expires:number;value:unknown;retrievedAt:string}>();
function abortError(){return new DOMException("Search cancelled.","AbortError");}
function checkAbort(signal?:AbortSignal){if(signal?.aborted)throw abortError();}
function delay(ms:number,signal?:AbortSignal):Promise<void>{return new Promise((resolve,reject)=>{if(signal?.aborted){reject(abortError());return;}const onAbort=()=>{clearTimeout(timer);reject(abortError());};const timer=setTimeout(()=>{signal?.removeEventListener("abort",onAbort);resolve();},ms);signal?.addEventListener("abort",onAbort,{once:true});});}
async function requestJson(url:string,provider:string,signal?:AbortSignal):Promise<{value:unknown;retrievedAt:string}>{
 checkAbort(signal);const hit=cache.get(url);if(hit&&hit.expires>Date.now())return hit;
 for(let attempt=0;attempt<3;attempt++){
  checkAbort(signal);const controller=new AbortController(),onAbort=()=>controller.abort();signal?.addEventListener("abort",onAbort,{once:true});const timer=setTimeout(()=>controller.abort(),15000);
  let pause=600*2**attempt,failure:ProviderRequestError|null=null;
  try{
   const response=await fetch(url,{signal:controller.signal,headers:{Accept:"application/json"},credentials:"omit",referrerPolicy:"no-referrer"});
   if(!response.ok){
    const retryAfter=response.headers.get("Retry-After"),retryMs=retryAfter?(/^\d+$/.test(retryAfter)?Number(retryAfter)*1000:Date.parse(retryAfter)-Date.now()):0;
    if(response.status===429){failure=new ProviderRequestError(provider,"RATE_LIMITED",provider+" has reached its usage limit. Wait before searching again; saved projects still work offline.");if(retryMs>30000)throw failure;pause=Math.max(pause,Number.isFinite(retryMs)?retryMs:0);}
    else if(response.status>=500)failure=new ProviderRequestError(provider,"UNAVAILABLE",provider+" is temporarily unavailable.");
    else throw new ProviderRequestError(provider,String(response.status),response.status===404?"No record found in "+provider+".":provider+" rejected this request ("+response.status+").");
   }else{
    const payload:unknown=await response.json(),entry={value:payload,retrievedAt:new Date().toISOString(),expires:Date.now()+15*60*1000};
    if(cache.size>=120)cache.delete(cache.keys().next().value!);cache.set(url,entry);return entry;
   }
  }catch(error){checkAbort(signal);if(error instanceof ProviderRequestError)throw error;failure=new ProviderRequestError(provider,controller.signal.aborted?"TIMEOUT":"NETWORK",controller.signal.aborted?provider+" timed out.":provider+" could not be reached. Check connectivity; the provider may also block browser requests.");}
  finally{clearTimeout(timer);signal?.removeEventListener("abort",onAbort);}
  if(attempt===2)throw failure||new ProviderRequestError(provider,"UNAVAILABLE",provider+" failed.");await delay(pause,signal);
 }
 throw new ProviderRequestError(provider,"UNAVAILABLE",provider+" failed.");
}
const normalizedError=(error:unknown,provider:string):ProviderError=>error instanceof ProviderRequestError?{provider:error.provider,code:error.code,message:error.message}:{provider,code:"INVALID_RESPONSE",message:error instanceof Error?error.message:provider+" returned invalid data."};
function actualStrategy(strategy:Strategy,input:SearchInput):Strategy{
 const year=new Date().getUTCFullYear();let lower=input.year_from,upper=input.year_to;const filters:string[]=[];
 if(strategy.kind==="Recent literature")lower=Math.max(lower||1,year-4);
 if(strategy.kind==="Foundational candidates")upper=Math.min(upper||year,year-8);
 if(lower)filters.push("from_publication_date:"+lower+"-01-01");if(upper)filters.push("to_publication_date:"+upper+"-12-31");
 if(input.oa_only)filters.push("is_oa:true");if(input.preprints_only)filters.push("type:preprint");else if(input.reviews_only||strategy.kind==="Review papers")filters.push("type:review");
 return {...strategy,query:strategy.query.trim().slice(0,500),filters,sort:strategy.kind==="Foundational candidates"?"cited_by_count:desc":strategy.kind==="Recent literature"?"publication_date:desc":undefined};
}
export async function searchLiterature(input:SearchInput,signal?:AbortSignal):Promise<SearchResult>{
 const year=new Date().getUTCFullYear()+1;for(const value of [input.year_from,input.year_to])if(value!==null&&(!Number.isInteger(value)||value<1000||value>year))throw new Error("Enter a valid publication year.");
 if(input.year_from&&input.year_to&&input.year_from>input.year_to)throw new Error("The starting year must not be later than the ending year.");
 if(input.reviews_only&&input.preprints_only)throw new Error("Select either reviews or preprints, not both.");
 const queries=input.queries.filter(q=>q.enabled&&q.query.trim()).slice(0,7).map(q=>actualStrategy(q,input));if(!queries.length)throw new Error("Enable at least one nonempty search query.");
 const collected:Paper[][]=Array.from({length:queries.length},()=>[]),errors:ProviderError[]=[];let cursor=0,limited=false;const performed:Strategy[]=[];
 async function worker(){
  while(cursor<queries.length&&!limited){
   checkAbort(signal);const index=cursor++,strategy=queries[index],url=new URL(OPENALEX);url.searchParams.set("search",strategy.query);url.searchParams.set("per_page","10");
   if(strategy.filters?.length)url.searchParams.set("filter",strategy.filters.join(","));if(strategy.sort)url.searchParams.set("sort",strategy.sort);performed.push(strategy);
   try{
    const {value,retrievedAt}=await requestJson(url.href,"OpenAlex",signal),results=object(value).results;if(!Array.isArray(results))throw new Error("OpenAlex returned no results array.");
    for(const record of results){try{collected[index].push(fromOpenAlex(record,retrievedAt));}catch(error){errors.push(normalizedError(error,"OpenAlex"));}}
   }catch(error){checkAbort(signal);const normalized=normalizedError(error,"OpenAlex");if(normalized.code==="RATE_LIMITED")limited=true;if(!errors.some(e=>e.code===normalized.code&&e.message===normalized.message))errors.push(normalized);}
  }
 }
 await Promise.all([worker(),worker()]);const all=collected.flat(),papers=deduplicate(all);
 if(limited&&performed.length<queries.length)errors.push({provider:"OpenAlex",code:"QUERIES_SKIPPED",message:"Remaining queries were skipped because the provider rate limit was reached."});
 return {papers,errors,queries:performed,deduplicated:all.length-papers.length};
}
export async function lookupDoi(value:string,signal?:AbortSignal):Promise<SearchResult>{
 const doi=normalizeDoi(value);if(!doi)throw new Error("Enter a valid DOI, for example 10.1000/example, or its doi.org URL.");
 const settled=await Promise.allSettled([requestJson(CROSSREF+"/"+encodeURIComponent(doi),"Crossref",signal).then(({value,retrievedAt})=>fromCrossref(object(value).message,retrievedAt)),requestJson(OPENALEX+"/https://doi.org/"+encodeURIComponent(doi),"OpenAlex",signal).then(({value,retrievedAt})=>fromOpenAlex(value,retrievedAt))]);
 checkAbort(signal);const papers:Paper[]=[],errors:ProviderError[]=[];settled.forEach((result,i)=>result.status==="fulfilled"?papers.push(result.value):errors.push(normalizedError(result.reason,i===0?"Crossref":"OpenAlex")));
 const combined=deduplicate(papers);return {papers:combined,errors,queries:[{kind:"DOI lookup",query:doi,enabled:true}],deduplicated:papers.length-combined.length};
}
export function basicBrief(question:string,papers:Paper[],mode="Evidence Review"):SynthesisResult{
 const abstracts=papers.filter(p=>p.abstract),tokens=terms(question).map(t=>t.toLowerCase()).filter(t=>t.length>3);
 const statements:SynthesisResult["statements"]=abstracts.slice(0,8).map(paper=>{
  const sentences=paper.abstract!.match(/[^.!?]+(?:[.!?]+|$)/g)?.map(s=>s.trim()).filter(Boolean)||[paper.abstract!];
  const score=(sentence:string)=>tokens.reduce((sum,token)=>sum+Number(sentence.toLowerCase().includes(token)),0);
  const candidate=sentences.reduce((best,s)=>score(s)>score(best)?s:best,sentences[0]||paper.abstract!);
  const excerpt=(candidate.match(/(?:\S+\s*){1,24}/)?.[0]||candidate).trim();
  return {classification:"SUPPORTED",text:"Source extract from the abstract: “"+excerpt+"”",citations:[{paper_id:paper.id,quote:excerpt,basis:"abstract"}]};
 });
 statements.push({classification:"UNKNOWN",text:"The retrieved metadata and abstract excerpts are insufficient to establish compositions, measured values, experimental conditions, contradictions, or the strongest material candidate. Full-text review and structured evidence extraction are required.",citations:[]});
 return {mode,question,basis:abstracts.length?"abstract":"metadata",statements,limitations:["This is a deterministic source brief, not an AI analysis. It extracts text without assessing scientific validity or completeness.","No full text was ingested. Open-access availability does not mean a paper has been read.","No page citations or experimentally verified property comparison can be produced from this Phase 1 brief.","Citation counts are provider-specific and are not evidence-strength scores.","Missing facts remain unknown. Related terminology is used only for discovery."],provider:"Source extracts (no AI model)"};
}
function bibEscape(value:string):string{return value.replace(/[\\{}%&_#$]/g,match=>"\\"+match).replace(/[\r\n]+/g," ");}
function line(value:string):string{return value.replace(/[\r\n]+/g," ");}
function markdownEscape(value:string):string{return value.replace(/[\\\[\]*_<>]/g,match=>"\\"+match);}
function csvCell(value:unknown):string{let text=value==null?"":String(value);if(/^[\s]*[=+@-]/.test(text))text="'"+text;return '"'+text.replace(/"/g,'""')+'"';}
export function exportBibliography(papers:Paper[],format:ExportFormat):string{
 if(format==="json")return JSON.stringify(papers,null,2);
 if(format==="csv"){const rows:unknown[][]=[["Title","Authors","Year","Journal","DOI","Type","Open access","Source URL","Providers"]];for(const p of papers)rows.push([p.title,p.authors.join("; "),p.year,p.journal,p.doi,p.publication_type,p.is_oa===null?"unknown":p.is_oa,p.oa_url||p.provenance[0]?.source_url,p.provenance.map(s=>s.provider).join("; ")]);return rows.map(row=>row.map(csvCell).join(",")).join("\r\n");}
 if(format==="markdown")return papers.map((p,index)=>{const doi=normalizeDoi(p.doi);return (index+1)+". "+(p.authors.length?markdownEscape(p.authors.join(", "))+". ":"")+(p.year?"("+p.year+"). ":"")+markdownEscape(p.title)+"."+(p.journal?" "+markdownEscape(p.journal)+".":"")+(doi?" [DOI](https://doi.org/"+encodeURIComponent(doi)+")":"");}).join("\n\n");
 if(format==="ris")return papers.map(p=>{const kind=p.publication_type==="dataset"?"DATA":p.publication_type==="conference"?"CONF":p.publication_type==="article"||p.publication_type==="review"?"JOUR":"GEN";return ["TY  - "+kind,"TI  - "+line(p.title),...p.authors.map(a=>"AU  - "+line(a)),...(p.year?["PY  - "+p.year]:[]),...(p.journal?["JO  - "+line(p.journal)]:[]),...(p.doi?["DO  - "+line(p.doi)]:[]),"ER  -"].join("\n");}).join("\n\n");
 return papers.map((p,i)=>{const fields:string[]=["title = {"+bibEscape(p.title)+"}"];if(p.authors.length)fields.push("author = {"+p.authors.map(bibEscape).join(" and ")+"}");if(p.year)fields.push("year = {"+p.year+"}");if(p.journal)fields.push("journal = {"+bibEscape(p.journal)+"}");if(p.doi)fields.push("doi = {"+bibEscape(p.doi)+"}");return "@"+(p.publication_type==="article"||p.publication_type==="review"?"article":"misc")+"{paper"+(i+1)+",\n  "+fields.join(",\n  ")+"\n}";}).join("\n\n");
}
