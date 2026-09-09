"""
agents/rei/research_tools.py — wrapper tipis di atas tools/web.
web_search/web_fetch dianggap kemampuan riset REI (bukan network AKANE),
sesuai tools/README.md.
"""

from tools.web.search import web_search as _web_search, web_fetch as _web_fetch


def web_search(query: str, max_results: int = 5) -> dict:
    return _web_search(query, max_results)


def web_fetch(url: str, max_chars: int = 3000) -> dict:
    return _web_fetch(url, max_chars)
