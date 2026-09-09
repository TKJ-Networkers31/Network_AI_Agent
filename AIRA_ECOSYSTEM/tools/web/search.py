import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


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