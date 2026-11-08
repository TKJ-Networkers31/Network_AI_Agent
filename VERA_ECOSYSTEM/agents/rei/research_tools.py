"""
agents/rei/research_tools.py — wrapper tipis di atas tools/web.
web_search/web_fetch/web_image_search dianggap kemampuan riset REI (bukan
network AKANE), sesuai tools/README.md.
"""

from tools.web.search import (
    web_search as _web_search,
    web_fetch as _web_fetch,
    web_image_search as _web_image_search,
)


def web_search(query: str, max_results: int = 5) -> dict:
    return _web_search(query, max_results)


def web_fetch(url: str, max_chars: int = 3000) -> dict:
    return _web_fetch(url, max_chars)


def web_image_search(query: str, max_results: int = 4) -> dict:
    return _web_image_search(query, max_results)