"""Summarisation tool — condenses long text into key points."""

import logging
from langchain_core.tools import tool
import openai

from maya.core.config import get_config

logger = logging.getLogger(__name__)


@tool
def summarise_text(text: str, max_words: int = 150) -> str:
    """Summarise long text, articles, or transcripts into clear and concise key points.

    Args:
        text: The text content to be summarised.
        max_words: Target maximum word count for the summary (default 150).

    Returns:
        Concise summary of the text.
    """
    cleaned_text = text.strip()
    if not cleaned_text:
        return "Error: No text provided to summarise."

    config = get_config()
    api_key = config.openrouter_api_key

    # Truncate input text to first 6,000 characters
    truncated_input = cleaned_text[:6000]

    # If API key is not configured, fallback to an extractive heuristic summary
    if not api_key:
        logger.warning(
            "OPENROUTER_API_KEY is not configured; using heuristic extractive summary."
        )
        sentences = [
            s.strip()
            for s in truncated_input.replace("\n", " ").split(".")
            if len(s.strip()) > 10
        ]
        if sentences:
            selected = sentences[:4]
            return f"(Extractive summary): {'. '.join(selected)}."
        words = truncated_input.split()[:max_words]
        return f"(Extractive summary): {' '.join(words)}..."

    try:
        client = openai.OpenAI(
            api_key=api_key,
            base_url=config.openrouter_base_url,
        )

        model = config.llm_fallback_1 or "openai/gpt-4o-mini"
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise summariser. Summarise the given text clearly and concisely.",
                },
                {
                    "role": "user",
                    "content": f"Summarise this in {max_words} words:\n\n{truncated_input}",
                },
            ],
            temperature=0.3,
            max_tokens=max(100, max_words * 3),
        )

        content = response.choices[0].message.content
        return content.strip() if content else "No summary generated."

    except Exception as e:
        logger.error("Failed to generate summary via OpenRouter API: %s", e)
        # Fallback to extractive summary
        words = truncated_input.split()[:max_words]
        return f"Summary (fallback): {' '.join(words)}..."
