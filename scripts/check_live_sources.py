"""Optional live diagnostic. Failures are reported independently, never replaced by fixtures."""
import json
import urllib.parse
import urllib.request
def get(url):
    request = urllib.request.Request(url, headers={"User-Agent":"OpenMaterialsResearchCopilot/0.1 (open-source research client)"})
    with urllib.request.urlopen(request,timeout=20) as response:
        return json.load(response)
sources = [
    ("OpenAlex", "https://api.openalex.org/works?"+urllib.parse.urlencode({"search":"tellurite glass","per_page":1})),
    ("Crossref", "https://api.crossref.org/works?"+urllib.parse.urlencode({"query.bibliographic":"tellurite glass","rows":1})),
]
success = 0
for provider,url in sources:
    try:
        data = get(url)
        works = data.get("results",[]) if provider=="OpenAlex" else data.get("message",{}).get("items",[])
        if not works:
            raise RuntimeError("No records returned")
        work = works[0]
        print(json.dumps({"provider":provider,"title":work.get("display_name") or work.get("title"),"doi":work.get("doi") or work.get("DOI")}))
        success += 1
    except Exception as exc:
        print(json.dumps({"provider":provider,"unavailable":str(exc)}))
if not success:
    raise SystemExit(1)
