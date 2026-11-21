from __future__ import annotations

import re


_SEARCH_TRIGGER_PATTERNS = (
    re.compile(r"\b(?:погугли(?:те|ть)?|загугли(?:те|ть)?|нагугли(?:те|ть)?|гугли(?:те|ть)?)\b", re.IGNORECASE),
    re.compile(r"\b(?:поищи(?:те|ть)?|ищи(?:те)?|найди(?:те)?|посмотри(?:те)?|поискать|найти)\b.{0,40}\b(?:в интернете|в сети|в гугле|онлайн)\b", re.IGNORECASE | re.DOTALL),
    re.compile(r"\b(?:google\s+(?:it|this|that|for|how|what|who|where|when|why)|search(?:\s+the\s+web|\s+online|\s+the\s+internet|\s+for)|look\s+(?:it\s+|this\s+|that\s+)?up|find(?:\s+(?:it|this|that))?\s+online)\b", re.IGNORECASE),
)


def contains_web_search_trigger(text: str) -> bool:
    return any(pattern.search(text) for pattern in _SEARCH_TRIGGER_PATTERNS)


def search_query_from_text(text: str) -> str | None:
    match = re.match(r"^/search(?:@\w+)?(?:\s+|$)(.*)$", text.strip(), re.IGNORECASE | re.DOTALL)
    return match.group(1).strip() if match else None


def search_citations(response: object) -> list[tuple[str, str]]:
    citations: list[tuple[str, str]] = []
    seen_urls: set[str] = set()

    for item in getattr(response, "output", []) or []:
        for content in getattr(item, "content", []) or []:
            for annotation in getattr(content, "annotations", []) or []:
                if getattr(annotation, "type", None) != "url_citation":
                    continue

                citation = getattr(annotation, "url_citation", None) or annotation
                url = getattr(citation, "url", None)
                if not url or url in seen_urls:
                    continue

                seen_urls.add(url)
                citations.append((getattr(citation, "title", None) or url, url))

    return citations
