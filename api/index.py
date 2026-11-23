import re

import httpx
from bs4 import BeautifulSoup
from fastapi.responses import JSONResponse

from app import APIError, ScoreService, app

URL = "https://www.cricbuzz.com/cricket-match/live-scores"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0 Safari/537.36"
    ),
    "Referer": "https://www.cricbuzz.com/",
    "Accept-Language": "en-US,en;q=0.9",
}


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
                title = (
                    " ".join(parent.get_text(" ", strip=True).split())
                    if parent
                    else ""
                )

            matches.append(
                {
                    "id": match_id,
                    "title": (title or f"Cricket match {match_id}")[:180],
                    "url": f"https://www.cricbuzz.com/live-cricket-scores/{match_id}/",
                }
            )
            seen.add(match_id)

        return {
            "status": "success",
            "source": "Cricbuzz",
            "count": len(matches),
            "matches": matches[:30],
        }

    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={
                "status": "error",
                "message": "The live-score source timed out. Please retry shortly.",
            },
        )
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": f"The live-score provider returned HTTP {exc.response.status_code}.",
            },
        )
    except httpx.RequestError:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "Unable to connect to the live-score provider.",
            },
        )
    except Exception:
        return JSONResponse(
            status_code=502,
            content={
                "status": "error",
                "message": "Unable to retrieve live matches from the score provider.",
            },
        )


@app.get("/score/{match_id}")
async def match_score(match_id: str):
    if not re.fullmatch(r"\d{4,20}", match_id):
        raise APIError(422, "invalid score id")

    return await ScoreService.fetch_score(match_id)
