import re
import httpx
from bs4 import BeautifulSoup
from fastapi.responses import JSONResponse
from app import app

URL = "https://www.cricbuzz.com/cricket-match/live-scores"
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0 Safari/537.36", "Referer": "https://www.cricbuzz.com/", "Accept-Language": "en-US,en;q=0.9"}

@app.get("/health")
async def health():
    return {"status": "ok", "service": "Live Cricket Score"}

@app.get("/matches")
async def live_matches():
    try:
        async with httpx.AsyncClient(timeout=12.0, follow_redirects=True) as client:
            response = await client.get(URL, headers=HEADERS)
            response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        matches = []
        seen = set()
        for anchor in soup.select('a[href*="/live-cricket-scores/"]'):
            href = anchor.get("href", "")
            found = re.search(r"/live-cricket-scores/(\d+)(?:/|$)", href)
            if not found:
                continue
            match_id = found.group(1)
            if match_id in seen:
                continue
            title = " ".join(anchor.get_text(" ", strip=True).split())
            if not title:
                parent = anchor.find_parent(["div", "li", "article"])
                title = " ".join(parent.get_text(" ", strip=True).split()) if parent else ""
            matches.append({"id": match_id, "title": (title or "Cricket match " + match_id)[:180], "url": "https://www.cricbuzz.com/live-cricket-scores/" + match_id + "/"})
            seen.add(match_id)
        return {"status": "success", "source": "Cricbuzz", "count": len(matches), "matches": matches[:30]}
    except httpx.TimeoutException:
        return JSONResponse(status_code=504, content={"status": "error", "message": "The live-score source timed out. Please retry shortly."})
    except Exception:
        return JSONResponse(status_code=502, content={"status": "error", "message": "Unable to retrieve live matches from the score provider."})
