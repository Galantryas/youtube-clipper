import os
import re
import yt_dlp
from typing import List, Dict, Any, Optional, Set

COUNTRY_MAP = {
    "US": "United States",
    "ID": "Indonesia",
    "GB": "United Kingdom",
    "IN": "India",
    "JP": "Japan",
    "CA": "Canada",
    "AU": "Australia",
    "BR": "Brazil",
    "DE": "Germany",
    "FR": "France",
    "KR": "South Korea",
    "PH": "Philippines",
    "ES": "Spain",
    "MX": "Mexico",
    "IT": "Italy"
}

COUNTRY_EMOJIS = {
    "US": "🇺🇸",
    "ID": "🇮🇩",
    "GB": "🇬🇧",
    "IN": "🇮🇳",
    "JP": "🇯🇵",
    "CA": "🇨🇦",
    "AU": "🇦🇺",
    "BR": "🇧🇷",
    "DE": "🇩🇪",
    "FR": "🇫🇷",
    "KR": "🇰🇷",
    "PH": "🇵🇭",
    "ES": "🇪🇸",
    "MX": "🇲🇽",
    "IT": "🇮🇹"
}


def fetch_country_trending(
    country_code: str = "US",
    category: str = "all",
    limit: int = 10,
    excluded_ids: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Fetches trending videos for a specific country and optional category.
    Filters out excluded IDs and non-standard durations (<45s or >40m).
    """
    c_code = country_code.upper().strip()
    c_name = COUNTRY_MAP.get(c_code, c_code)
    excluded = excluded_ids or set()

    category_query = ""
    if category and category.lower() not in ["all", "general"]:
        category_query = f" {category.strip()}"

    query = f"ytsearch{limit * 2}:trending{category_query} {c_name}"

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,
        "nocheckcertificate": True,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
            "Accept-Language": "en-US,en;q=0.9",
        }
    }

    results = []
    seen_ids = set()

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            data = ydl.extract_info(query, download=False)
            entries = data.get("entries", []) if data else []
            for e in entries:
                vid = e.get("id")
                if not vid or vid in seen_ids or vid in excluded:
                    continue

                dur = e.get("duration") or 0
                # Target ideal clipping duration (45s to 2400s)
                if dur > 0 and (dur < 45 or dur > 2400):
                    continue

                seen_ids.add(vid)
                results.append({
                    "video_id": vid,
                    "url": f"https://www.youtube.com/watch?v={vid}",
                    "title": e.get("title", "Untitled Video"),
                    "channel": e.get("uploader") or e.get("channel", "YouTube Channel"),
                    "duration": dur,
                    "view_count": e.get("view_count", 0),
                    "thumbnail": f"https://img.youtube.com/vi/{vid}/hqdefault.jpg",
                    "country_code": c_code,
                    "country_name": c_name,
                    "country_flag": COUNTRY_EMOJIS.get(c_code, "🌐"),
                    "category": category or "all"
                })

                if len(results) >= limit:
                    break
        except Exception as err:
            print(f"Warning: Failed to fetch trending for {c_code}: {err}")

    return results


def fetch_multi_country_trending(
    countries: List[str],
    category: str = "all",
    max_total_videos: int = 10,
    excluded_ids: Optional[Set[str]] = None
) -> List[Dict[str, Any]]:
    """
    Evenly distributes scraping across configured countries to reach max_total_videos.
    """
    if not countries:
        countries = ["US"]

    excluded = set(excluded_ids or [])
    all_videos = []
    seen_ids = set()

    # Determine per-country quota
    per_country_quota = max(2, (max_total_videos // len(countries)) + 1)

    for country in countries:
        c_code = country.upper().strip()
        country_videos = fetch_country_trending(
            country_code=c_code,
            category=category,
            limit=per_country_quota,
            excluded_ids=excluded | seen_ids
        )
        for v in country_videos:
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                all_videos.append(v)
                if len(all_videos) >= max_total_videos:
                    break
        if len(all_videos) >= max_total_videos:
            break

    return all_videos[:max_total_videos]
