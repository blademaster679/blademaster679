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
    width = 540
    padding_x = 28
    header_height = 86
    row_height = 34
    footer_height = 26
    top_bar_y = 56
    top_bar_width = width - padding_x * 2
    language_x = 58
    row_bar_x = 232
    row_bar_width = 210
    percent_x = width - padding_x
    shown = sorted(language_totals.items(), key=lambda item: item[1], reverse=True)[:max_languages]

    if not shown:
        height = 128
        return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">No language data is available yet.</desc>
  <defs>
    <linearGradient id="card-gradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#f8fafc"/>
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="url(#card-gradient)" stroke="#e5e7eb"/>
  <text x="{padding_x}" y="38" fill="#0f172a" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="700">Top languages</text>
  <text x="{padding_x}" y="78" fill="#64748b" font-family="Segoe UI, Arial, sans-serif" font-size="14">No language data available.</text>
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
        bar_width = max(5, round(percent / 100 * row_bar_width, 2))

        rows.append(
            f"""  <circle cx="{padding_x + 6}" cy="{y + 15}" r="6" fill="{color}"/>
  <text x="{language_x}" y="{y + 20}" fill="#0f172a" font-family="Segoe UI, Arial, sans-serif" font-size="14" font-weight="650">{escaped_language}</text>
  <rect x="{row_bar_x}" y="{y + 8}" width="{row_bar_width}" height="13" rx="6.5" fill="#e8edf3"/>
  <rect x="{row_bar_x}" y="{y + 8}" width="{bar_width}" height="13" rx="6.5" fill="{color}"/>
  <text x="{percent_x}" y="{y + 20}" fill="#334155" font-family="Segoe UI, Arial, sans-serif" font-size="13" text-anchor="end">{format_percent(percent)}</text>"""
        )

        end_offset = offset + percent
        gradient_stops.append(f'    <stop offset="{offset:.4f}%" stop-color="{color}"/>')
        gradient_stops.append(f'    <stop offset="{end_offset:.4f}%" stop-color="{color}"/>')
        offset = end_offset

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">Top languages</title>
  <desc id="desc">Top programming languages used across public repositories.</desc>
  <defs>
    <linearGradient id="card-gradient" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="#ffffff"/>
      <stop offset="100%" stop-color="#f8fafc"/>
    </linearGradient>
    <linearGradient id="language-gradient" x1="0" y1="0" x2="1" y2="0">
{chr(10).join(gradient_stops)}
    </linearGradient>
  </defs>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="14" fill="url(#card-gradient)" stroke="#e5e7eb"/>
  <text x="{padding_x}" y="38" fill="#0f172a" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="700">Top languages</text>
  <rect x="{padding_x}" y="{top_bar_y}" width="{top_bar_width}" height="11" rx="5.5" fill="url(#language-gradient)"/>
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
