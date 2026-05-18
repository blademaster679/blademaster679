from __future__ import annotations

import argparse
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


DEFAULT_COLORS = [
    "#3178c6",
    "#f1e05a",
    "#3572A5",
    "#e34c26",
    "#563d7c",
    "#89e051",
]


def github_request(url: str, token: str | None) -> object:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "GitHub-Profile-README-Top-Languages",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API request failed for {url}: {exc.code} {details}") from exc


def fetch_owner_repositories(username: str, token: str | None) -> list[dict[str, object]]:
    repos: list[dict[str, object]] = []
    page = 1

    while True:
        query = urllib.parse.urlencode(
            {
                "type": "owner",
                "sort": "updated",
                "per_page": "100",
                "page": str(page),
            }
        )
        payload = github_request(f"https://api.github.com/users/{username}/repos?{query}", token)
        if not isinstance(payload, list):
            raise RuntimeError("GitHub API returned an unexpected repository payload.")
        if not payload:
            break

        repos.extend(repo for repo in payload if isinstance(repo, dict))
        if len(payload) < 100:
            break
        page += 1

    return repos


def fetch_language_totals(username: str, token: str | None, include_forks: bool) -> dict[str, int]:
    totals: dict[str, int] = {}
    repos = fetch_owner_repositories(username, token)

    for repo in repos:
        if repo.get("archived"):
            continue
        if repo.get("fork") and not include_forks:
            continue

        name = repo.get("name")
        if not isinstance(name, str) or not name:
            continue

        payload = github_request(f"https://api.github.com/repos/{username}/{name}/languages", token)
        if not isinstance(payload, dict):
            continue

        for language, byte_count in payload.items():
            if isinstance(language, str) and isinstance(byte_count, int) and byte_count > 0:
                totals[language] = totals.get(language, 0) + byte_count

    return totals


def format_percent(value: float) -> str:
    if value >= 10:
        return f"{value:.1f}%"
    return f"{value:.2f}%"


def render_svg(language_totals: dict[str, int], max_languages: int) -> str:
    width = 420
    header_height = 52
    row_height = 28
    footer_height = 18
    shown = sorted(language_totals.items(), key=lambda item: item[1], reverse=True)[:max_languages]

    if not shown:
        height = 128
        return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">No language data is available yet.</desc>
  <rect width="{width}" height="{height}" rx="8" fill="#ffffff"/>
  <text x="24" y="36" fill="#111827" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="600">Top languages</text>
  <text x="24" y="76" fill="#6b7280" font-family="Segoe UI, Arial, sans-serif" font-size="14">No language data available.</text>
</svg>
"""

    total = sum(language_totals.values())
    height = header_height + len(shown) * row_height + footer_height
    safe_total = max(total, 1)

    rows: list[str] = []
    gradient_stops: list[str] = []
    offset = 0.0

    for index, (language, byte_count) in enumerate(shown):
        percent = byte_count / safe_total * 100
        color = DEFAULT_COLORS[index % len(DEFAULT_COLORS)]
        escaped_language = html.escape(language)
        y = header_height + index * row_height
        bar_width = max(4, round(percent / 100 * 250, 2))

        rows.append(
            f"""  <circle cx="28" cy="{y + 9}" r="5" fill="{color}"/>
  <text x="42" y="{y + 14}" fill="#111827" font-family="Segoe UI, Arial, sans-serif" font-size="13" font-weight="600">{escaped_language}</text>
  <rect x="146" y="{y + 3}" width="250" height="10" rx="5" fill="#e5e7eb"/>
  <rect x="146" y="{y + 3}" width="{bar_width}" height="10" rx="5" fill="{color}"/>
  <text x="396" y="{y + 14}" fill="#374151" font-family="Segoe UI, Arial, sans-serif" font-size="12" text-anchor="end">{format_percent(percent)}</text>"""
        )

        end_offset = offset + percent
        gradient_stops.append(f'    <stop offset="{offset:.4f}%" stop-color="{color}"/>')
        gradient_stops.append(f'    <stop offset="{end_offset:.4f}%" stop-color="{color}"/>')
        offset = end_offset

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">Top programming languages used across public repositories.</desc>
  <defs>
    <linearGradient id="language-gradient" x1="0" y1="0" x2="1" y2="0">
{chr(10).join(gradient_stops)}
    </linearGradient>
  </defs>
  <rect width="{width}" height="{height}" rx="8" fill="#ffffff"/>
  <text x="24" y="35" fill="#111827" font-family="Segoe UI, Arial, sans-serif" font-size="18" font-weight="600">Top languages</text>
  <rect x="24" y="46" width="372" height="8" rx="4" fill="url(#language-gradient)"/>
{chr(10).join(rows)}
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("GITHUB_USERNAME", "blademaster679"))
    parser.add_argument("--output", default="images/top-languages.svg")
    parser.add_argument("--max-languages", type=int, default=6)
    parser.add_argument("--include-forks", action="store_true")
    args = parser.parse_args()

    token = os.environ.get("GITHUB_TOKEN")
    totals = fetch_language_totals(args.username, token, args.include_forks)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(totals, args.max_languages), encoding="utf-8")


if __name__ == "__main__":
    main()
