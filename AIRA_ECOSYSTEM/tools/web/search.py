import ipaddress
import logging
import os
import re
import socket
from urllib.parse import urljoin, urlparse

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


def _validate_safe_url(url: str) -> tuple[bool, str]:
    """Validates URL against SSRF attacks (only http/https, no private/internal IPs)."""
    try:
        parsed = urlparse(url)
    except Exception as e:
        return False, f"Invalid URL format: {e}"

    if parsed.scheme not in ("http", "https"):
        return False, f"Invalid scheme '{parsed.scheme}'. Only http and https are permitted."

    hostname = parsed.hostname
    if not hostname:
        return False, "URL missing hostname."

    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addr_info = socket.getaddrinfo(hostname, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for _, _, _, _, sockaddr in addr_info:
            ip_str = sockaddr[0]
            ip_obj = ipaddress.ip_address(ip_str)
            if (
                ip_obj.is_private
                or ip_obj.is_loopback
                or ip_obj.is_link_local
                or ip_obj.is_reserved
                or ip_obj.is_multicast
            ):
                return False, f"Access to private/local address '{ip_str}' is denied."
    except socket.gaierror as e:
        return False, f"Could not resolve hostname '{hostname}': {e}"
    except Exception as e:
        return False, f"Error validating target host '{hostname}': {e}"

    return True, ""


def web_fetch(url, max_chars=3000):
    try:
        is_safe, reason = _validate_safe_url(url)
        if not is_safe:
            return {
                "success": False,
                "tool": "web_fetch",
                "url": url,
                "error": f"SSRF Protection: {reason}",
            }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; NetworkAIAgent/1.0)"
            )
        }

        current_url = url
        session = requests.Session()
        session.headers.update(headers)

        response = None
        for _ in range(5):
            res = session.get(current_url, timeout=15, stream=True, allow_redirects=False)
            if 300 <= res.status_code < 400 and "Location" in res.headers:
                next_url = urljoin(current_url, res.headers["Location"])
                is_safe, reason = _validate_safe_url(next_url)
                if not is_safe:
                    return {
                        "success": False,
                        "tool": "web_fetch",
                        "url": next_url,
                        "error": f"SSRF Protection (Redirect): {reason}",
                    }
                current_url = next_url
                continue
            response = res
            break

        if response is None:
            return {
                "success": False,
                "tool": "web_fetch",
                "url": url,
                "error": "Too many redirects or no response."
            }

        response.raise_for_status()

        chunks = []
        bytes_read = 0
        max_bytes = 2 * 1024 * 1024
        for chunk in response.iter_content(chunk_size=8192, decode_unicode=True):
            if chunk:
                chunks.append(chunk)
                bytes_read += len(chunk.encode("utf-8", errors="ignore"))
                if bytes_read >= max_bytes:
                    break
        content_text = "".join(chunks)

        soup = BeautifulSoup(content_text, "html.parser")

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
            "url": current_url,
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

    try:
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
    except Exception as exc:
        sanitized = re.sub(r"key=[^&\s'\"]+", "key=[REDACTED]", str(exc))
        raise RuntimeError(f"Google CSE error: {sanitized}") from None

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
            sanitized = re.sub(r"key=[^&\s'\"]+", "key=[REDACTED]", str(exc))
            logger.warning("Google Image Search gagal, fallback ke DuckDuckGo: %s", sanitized)

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