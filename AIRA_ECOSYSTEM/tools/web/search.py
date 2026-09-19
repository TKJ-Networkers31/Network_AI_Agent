import logging
import os
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS

logger = logging.getLogger("aira.tools.web")

GOOGLE_CSE_ENDPOINT = "https://www.googleapis.com/customsearch/v1"
DEFAULT_IMAGE_RESULTS = 4
MAX_IMAGE_RESULTS = 6


def web_search(query, max_results=5):

    try:
        with DDGS() as ddgs:
            raw_results = list(
                ddgs.text(
                    query,
                    max_results=max_results
                )
            )

        results = []

        for item in raw_results:
            results.append({
                "title": item.get("title"),
                "url": item.get("href"),
                "snippet": item.get("body")
            })

        return {
            "success": True,
            "tool": "web_search",
            "query": query,
            "count": len(results),
            "results": results
        }

    except Exception as exc:
        return {
            "success": False,
            "tool": "web_search",
            "query": query,
            "error": str(exc)
        }


def web_fetch(url, max_chars=3000):

    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; NetworkAIAgent/1.0)"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=15
        )
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()

        raw_text = soup.get_text(separator="\n", strip=True)

        lines = [
            line for line in raw_text.splitlines()
            if line.strip()
        ]

        text = "\n".join(lines)
        truncated = text[:max_chars]

        return {
            "success": True,
            "tool": "web_fetch",
            "url": url,
            "content": truncated,
            "is_truncated": len(text) > max_chars
        }

    except Exception as exc:
        return {
            "success": False,
            "tool": "web_fetch",
            "url": url,
            "error": str(exc)
        }


# ------------------------------------------------------------------
# IMAGE SEARCH
#
# Sumber: Google Custom Search (searchType=image) kalau
# GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID diset di .env; kalau tidak diset
# atau gagal/kosong, otomatis jatuh ke DuckDuckGo Images (lewat ddgs
# yang sudah jadi dependency) - tidak butuh API key.
#
# 'image_url' sengaja memakai THUMBNAIL kalau ada: URL gambar asli
# sering diblokir hotlink / kedaluwarsa, sedangkan thumbnail dari
# Google/Bing stabil ditampilkan di browser. URL asli tetap dikirim
# di 'original_url'.
# ------------------------------------------------------------------

def _host(url):

    try:
        return urlparse(url or "").netloc.replace("www.", "") or None
    except Exception:
        return None


def _google_images(query, count):
    """Return list hasil mentah, atau None kalau Google CSE belum dikonfigurasi."""

    api_key = os.getenv("GOOGLE_CSE_API_KEY")
    cx = os.getenv("GOOGLE_CSE_ID")

    if not api_key or not cx:
        return None

    response = requests.get(
        GOOGLE_CSE_ENDPOINT,
        params={
            "key": api_key,
            "cx": cx,
            "q": query,
            "searchType": "image",
            "num": min(count, 10),
            "safe": "active",
        },
        timeout=15,
    )
    response.raise_for_status()

    results = []

    for item in response.json().get("items", []):
        image = item.get("image") or {}
        results.append({
            "title": item.get("title"),
            "original_url": item.get("link"),
            "thumbnail_url": image.get("thumbnailLink"),
            "page_url": image.get("contextLink"),
            "width": image.get("width"),
            "height": image.get("height"),
        })

    return results


def _ddgs_images(query, count):

    with DDGS() as ddgs:
        raw_results = list(
            ddgs.images(
                query,
                max_results=count * 2,
                safesearch="moderate",
            )
        )

    return [
        {
            "title": item.get("title"),
            "original_url": item.get("image"),
            "thumbnail_url": item.get("thumbnail"),
            "page_url": item.get("url"),
            "width": item.get("width"),
            "height": item.get("height"),
        }
        for item in raw_results
    ]


def _normalize_images(raw_results, count):

    images = []
    seen = set()

    for item in raw_results:

        original = item.get("original_url")
        display = item.get("thumbnail_url") or original

        if not display or not display.startswith(("http://", "https://")):
            continue

        if display in seen:
            continue

        seen.add(display)

        title = " ".join((item.get("title") or "").split())

        images.append({
            "title": title[:90] or "gambar",
            "image_url": display,
            "original_url": original,
            "source": _host(item.get("page_url") or original),
            "page_url": item.get("page_url"),
            "width": item.get("width"),
            "height": item.get("height"),
        })

        if len(images) >= count:
            break

    return images


def web_image_search(query, max_results=DEFAULT_IMAGE_RESULTS):

    try:
        count = max(1, min(int(max_results or DEFAULT_IMAGE_RESULTS), MAX_IMAGE_RESULTS))
    except (TypeError, ValueError):
        count = DEFAULT_IMAGE_RESULTS

    try:
        source = "google"
        raw_results = None

        try:
            raw_results = _google_images(query, count)
        except Exception as exc:
            logger.warning("Google Image Search gagal, fallback ke DuckDuckGo: %s", exc)

        if not raw_results:
            source = "duckduckgo"
            raw_results = _ddgs_images(query, count)

        images = _normalize_images(raw_results, count)

        return {
            "success": bool(images),
            "tool": "web_image_search",
            "query": query,
            "source": source,
            "count": len(images),
            "images": images,
            "note": (
                "Tampilkan dengan Markdown ![deskripsi](image_url) memakai "
                "image_url PERSIS dari hasil ini, lalu sebut 'source'."
            ),
            **({} if images else {"error": "Tidak ada gambar yang ditemukan."}),
        }

    except Exception as exc:
        return {
            "success": False,
            "tool": "web_image_search",
            "query": query,
            "error": str(exc)
        }