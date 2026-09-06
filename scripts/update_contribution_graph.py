from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


GRAPHQL_URL = "https://api.github.com/graphql"
PUBLIC_API_URL = "https://github-contributions-api.jogruber.de/v4/{username}?y=last"
LEVELS = {
    "NONE": 0,
    "FIRST_QUARTILE": 1,
    "SECOND_QUARTILE": 2,
    "THIRD_QUARTILE": 3,
    "FOURTH_QUARTILE": 4,
}
COLORS = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def fetch_json(request: urllib.request.Request) -> object:
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Request failed: {exc.code} {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Request failed: {exc.reason}") from exc


def fetch_from_github(username: str, token: str) -> list[dict[str, object]]:
    query = """
    query($login: String!) {
      user(login: $login) {
        contributionsCollection {
          contributionCalendar {
            weeks {
              contributionDays {
                contributionCount
                contributionLevel
                date
                weekday
              }
            }
          }
        }
      }
    }
    """
    body = json.dumps({"query": query, "variables": {"login": username}}).encode("utf-8")
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=body,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "GitHub-Profile-Contribution-Graph",
        },
    )
    payload = fetch_json(request)
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub GraphQL returned an unexpected response.")
    if payload.get("errors"):
        raise RuntimeError(f"GitHub GraphQL returned errors: {payload['errors']}")

    try:
        weeks = payload["data"]["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("GitHub GraphQL response did not include a contribution calendar.") from exc

    days: list[dict[str, object]] = []
    for week in weeks:
        for day in week.get("contributionDays", []):
            level = LEVELS.get(str(day.get("contributionLevel", "NONE")), 0)
            days.append(
                {
                    "date": day.get("date"),
                    "count": day.get("contributionCount", 0),
                    "level": level,
                }
            )
    return days


def fetch_from_public_api(username: str) -> list[dict[str, object]]:
    url = PUBLIC_API_URL.format(username=urllib.parse.quote(username, safe=""))
    request = urllib.request.Request(url, headers={"User-Agent": "GitHub-Profile-Contribution-Graph"})
    payload = fetch_json(request)
    if not isinstance(payload, dict) or not isinstance(payload.get("contributions"), list):
        raise RuntimeError("The public contribution API returned an unexpected response.")
    return payload["contributions"]


def fetch_contributions(username: str, token: str | None) -> list[dict[str, object]]:
    if token:
        try:
            return fetch_from_github(username, token)
        except RuntimeError as exc:
            print(f"GitHub GraphQL request failed; using the public fallback: {exc}")
    return fetch_from_public_api(username)


def normalize_days(raw_days: list[dict[str, object]]) -> tuple[list[list[dict[str, object] | None]], int]:
    parsed: dict[dt.date, dict[str, object]] = {}
    for raw_day in raw_days:
        try:
            date = dt.date.fromisoformat(str(raw_day["date"]))
            count = max(0, int(raw_day.get("count", 0)))
            level = min(4, max(0, int(raw_day.get("level", 0))))
        except (AttributeError, KeyError, TypeError, ValueError):
            continue
        parsed[date] = {"date": date, "count": count, "level": level}

    if not parsed:
        raise RuntimeError("No valid contribution days were returned.")

    latest = max(parsed)
    end = latest + dt.timedelta(days=(5 - latest.weekday()) % 7)
    start = end - dt.timedelta(weeks=53) + dt.timedelta(days=1)
    weeks: list[list[dict[str, object] | None]] = []
    total = 0

    for week_index in range(53):
        week: list[dict[str, object] | None] = []
        sunday = start + dt.timedelta(weeks=week_index)
        for weekday in range(7):
            date = sunday + dt.timedelta(days=weekday)
            day = parsed.get(date)
            week.append(day)
            if day is not None:
                total += int(day["count"])
        weeks.append(week)

    return weeks, total


def render_svg(username: str, raw_days: list[dict[str, object]]) -> str:
    weeks, total = normalize_days(raw_days)
    width = 900
    height = 184
    cell = 11
    gap = 4
    grid_x = 55
    grid_y = 57
    safe_username = html.escape(username)
    cells: list[str] = []

    for week_index, week in enumerate(weeks):
        for weekday, day in enumerate(week):
            if day is None:
                continue
            date = day["date"]
            count = int(day["count"])
            level = int(day["level"])
            x = grid_x + week_index * (cell + gap)
            y = grid_y + weekday * (cell + gap)
            label = f"{count} contribution{'s' if count != 1 else ''} on {date.isoformat()}"
            cells.append(
                f'  <rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2" fill="{COLORS[level]}">'
                f"<title>{html.escape(label)}</title></rect>"
            )

    month_labels: list[str] = []
    seen_months: set[tuple[int, int]] = set()
    for week_index, week in enumerate(weeks):
        dates = [day["date"] for day in week if day is not None]
        for date in dates:
            key = (date.year, date.month)
            if date.day <= 7 and key not in seen_months:
                x = grid_x + week_index * (cell + gap)
                month_labels.append(
                    f'  <text x="{x}" y="48" class="muted" font-size="12">{MONTHS[date.month - 1]}</text>'
                )
                seen_months.add(key)
                break

    legend = []
    legend_x = width - 151
    for level, color in enumerate(COLORS):
        x = legend_x + level * (cell + gap)
        legend.append(f'  <rect x="{x}" y="161" width="{cell}" height="{cell}" rx="2" fill="{color}"/>')

    return f"""<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" fill="none" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="title desc">
  <title id="title">{safe_username}'s contribution graph</title>
  <desc id="desc">{total} contributions in the last year.</desc>
  <style>
    .text {{ fill: #f0f6fc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
    .muted {{ fill: #8b949e; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif; }}
  </style>
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="8" fill="#0d1117" stroke="#30363d"/>
  <text x="22" y="29" class="text" font-size="16" font-weight="600">{safe_username}'s Contribution Graph</text>
{chr(10).join(month_labels)}
  <text x="22" y="80" class="muted" font-size="11">Mon</text>
  <text x="22" y="110" class="muted" font-size="11">Wed</text>
  <text x="22" y="140" class="muted" font-size="11">Fri</text>
{chr(10).join(cells)}
  <text x="22" y="171" class="muted" font-size="12">{total} contributions in the last year</text>
  <text x="{legend_x - 32}" y="171" class="muted" font-size="11">Less</text>
{chr(10).join(legend)}
  <text x="{legend_x + 82}" y="171" class="muted" font-size="11">More</text>
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--username", default=os.environ.get("GITHUB_USERNAME", "blademaster679"))
    parser.add_argument("--output", default="images/contribution-graph.svg")
    parser.add_argument("--input", help="Read contribution JSON from a file instead of the network.")
    args = parser.parse_args()

    if args.input:
        payload = json.loads(Path(args.input).read_text(encoding="utf-8"))
        raw_days = payload.get("contributions", payload) if isinstance(payload, dict) else payload
        if not isinstance(raw_days, list):
            raise RuntimeError("Input must be a contribution array or an object containing one.")
    else:
        raw_days = fetch_contributions(args.username, os.environ.get("GITHUB_TOKEN"))

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_svg(args.username, raw_days), encoding="utf-8")


if __name__ == "__main__":
    main()
