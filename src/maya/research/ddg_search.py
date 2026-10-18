from ddgs import DDGS


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """Search the web using DDGS without an API key."""
    with DDGS() as ddgs:
        results = ddgs.text(
            query,
            max_results=max(1, min(max_results, 10)),
        )

        return [
            {
                "title": item.get("title", ""),
                "url": item.get("href", ""),
                "snippet": item.get("body", ""),
            }
            for item in results
        ]
