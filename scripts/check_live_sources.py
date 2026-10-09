"""Optional, bounded network diagnostic; deterministic provider tests use mocks."""
import json
import urllib.parse
import urllib.request

def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "OpenMaterialsResearchCopilot/0.1 (open-source research client)"})
    with urllib.request.urlopen(request, timeout=20) as response:
        return json.load(response)

data = get("https://api.openalex.org/works?" + urllib.parse.urlencode({"search": "tellurite glass", "per_page": 1}))
works = data.get("results", [])
if not works:
    raise RuntimeError("OpenAlex returned no records for the live diagnostic")
work = works[0]
doi = work.get("doi")
print(json.dumps({"provider": "OpenAlex", "title": work.get("display_name"), "doi": doi, "oa": work.get("open_access", {}).get("is_oa")}))
if doi:
    identifier = doi.removeprefix("https://doi.org/")
    record = get("https://api.crossref.org/works/" + urllib.parse.quote(identifier, safe=""))["message"]
    print(json.dumps({"provider": "Crossref", "doi": record.get("DOI"), "title": record.get("title")}))
