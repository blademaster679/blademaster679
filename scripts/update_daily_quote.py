from __future__ import annotations

import argparse
import html
import json
import os
import re
import urllib.request
from pathlib import Path


START = "<!-- DAILY_QUOTE_START -->"
END = "<!-- DAILY_QUOTE_END -->"
ZENQUOTES_TODAY_URL = "https://zenquotes.io/api/today"


def fetch_quote() -> tuple[str, str]:
    env_quote = os.environ.get("DAILY_QUOTE_TEXT")
    if env_quote:
        return env_quote.strip(), os.environ.get("DAILY_QUOTE_AUTHOR", "").strip()

    request = urllib.request.Request(
        ZENQUOTES_TODAY_URL,
        headers={"User-Agent": "GitHub-Profile-README-Daily-Quote"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))

    if not isinstance(payload, list) or not payload:
        raise ValueError("ZenQuotes returned an empty response.")

    quote = str(payload[0].get("q", "")).strip()
    author = str(payload[0].get("a", "")).strip()
    if not quote:
        raise ValueError("ZenQuotes response did not include a quote.")

    return quote, author


def render_quote_block(quote: str, author: str) -> str:
    quote_text = html.escape(quote, quote=False)
    author_text = html.escape(author, quote=False)
    text = f'"{quote_text}"'
    if author_text:
        text = f"{text} - {author_text}"

    return f'{START}\n<div align="center">\n  <sub>{text}</sub>\n</div>\n{END}'


def update_readme(path: Path, quote: str, author: str) -> None:
    content = path.read_text(encoding="utf-8")
    pattern = re.compile(f"{re.escape(START)}.*?{re.escape(END)}", re.DOTALL)
    replacement = render_quote_block(quote, author)
    updated, count = pattern.subn(replacement, content, count=1)

    if count != 1:
        raise ValueError(f"Could not find quote markers in {path}.")

    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--readme", default="README.md")
    args = parser.parse_args()

    quote, author = fetch_quote()
    update_readme(Path(args.readme), quote, author)


if __name__ == "__main__":
    main()
