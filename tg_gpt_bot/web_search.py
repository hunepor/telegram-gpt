from __future__ import annotations

import re


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
