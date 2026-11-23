import asyncio
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
    "Accept": "application/json, text/plain, */*",
}


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Live Cricket Score"}


@app.get("/api/matches")
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
            found = re.search(r"/live-cricket-scores/(\\d+)(?:/|$)", href)
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
            content={"status": "error", "message": "The live-score source timed out. Please retry shortly."},
        )
    except httpx.HTTPStatusError as exc:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": f"The live-score provider returned HTTP {exc.response.status_code}."},
        )
    except httpx.RequestError:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Unable to connect to the live-score provider."},
        )
    except Exception:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Unable to retrieve live matches from the score provider."},
        )


async def fetch_cricbuzz_json(client: httpx.AsyncClient, endpoint: str):
    response = await client.get(
        f"https://www.cricbuzz.com/api/mcenter/{endpoint}",
        headers=HEADERS,
    )
    response.raise_for_status()
    return response.json()


@app.get("/api/match/{match_id}")
async def full_match(match_id: str):
    if not re.fullmatch(r"\\d{4,20}", match_id):
        raise APIError(422, "invalid match id")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
            live_task = fetch_cricbuzz_json(client, f"comm/{match_id}")
            scorecard_task = fetch_cricbuzz_json(client, f"scorecard/{match_id}")
            live_result, scorecard_result = await asyncio.gather(
                live_task, scorecard_task, return_exceptions=True
            )

        errors = {}
        live_data = live_result if isinstance(live_result, dict) else None
        scorecard_data = scorecard_result if isinstance(scorecard_result, dict) else None

        if live_data is None:
            errors["live"] = str(live_result)
        if scorecard_data is None:
            errors["scorecard"] = str(scorecard_result)

        if live_data is None and scorecard_data is None:
            return JSONResponse(
                status_code=502,
                content={
                    "status": "error",
                    "message": "Cricbuzz did not return match data. The match ID may be invalid or the provider may be temporarily unavailable.",
                    "provider_errors": errors,
                },
            )

        header = (live_data or {}).get("matchHeader") or (scorecard_data or {}).get("matchHeader") or {}
        miniscore = (live_data or {}).get("miniscore") or {}
        commentary = (live_data or {}).get("matchCommentary") or {}
        innings = (scorecard_data or {}).get("scoreCard") or []

        return {
            "status": "success",
            "source": "Cricbuzz",
            "match_id": match_id,
            "match_url": f"https://www.cricbuzz.com/live-cricket-scores/{match_id}/",
            "match_header": header,
            "live_score": miniscore,
            "commentary": commentary,
            "scorecard": innings,
            "live_data": live_data,
            "scorecard_data": scorecard_data,
            "provider_errors": errors or None,
        }

    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={"status": "error", "message": "Cricbuzz request timed out. Please retry."},
        )
    except httpx.RequestError:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Unable to connect to Cricbuzz."},
        )
    except Exception as exc:
        return JSONResponse(
            status_code=502,
            content={"status": "error", "message": "Unable to parse Cricbuzz match data.", "detail": str(exc)},
        )


@app.get("/api/score/{match_id}")
async def match_score(match_id: str):
    if not re.fullmatch(r"\\d{4,20}", match_id):
        raise APIError(422, "invalid score id")

    return await ScoreService.fetch_score(match_id)
