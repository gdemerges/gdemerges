#!/usr/bin/env python3
"""Generate the README stat cards as self-hosted SVGs.

Queries the GitHub GraphQL API once, then writes four files at the repo root:
stats.svg / stats-light.svg and languages.svg / languages-light.svg.

Needs a token with `public_repo` in GITHUB_TOKEN (the Actions default works).
"""

import json
import os
import subprocess
import sys
from collections import Counter

USER = os.environ.get("STATS_USER", "gdemerges")
TOP_N = 6

# Languages we never want on the card (config / markup noise).
EXCLUDED_LANGS = {"HTML", "CSS", "Makefile", "Dockerfile", "Shell", "Batchfile"}

LANG_COLORS = {
    "Python": "#3572A5", "Swift": "#F05138", "TypeScript": "#3178C6",
    "JavaScript": "#F1E05A", "Jupyter Notebook": "#DA5B0B", "SQL": "#E38C00",
    "Go": "#00ADD8", "Rust": "#DEA584", "Java": "#B07219", "C": "#555555",
    "C++": "#F34B7D", "Ruby": "#701516", "Kotlin": "#A97BFF", "Vue": "#41B883",
}
FALLBACK_LANG_COLOR = "#8B949E"

THEMES = {
    "": {  # dark, the default file name
        "bg": "#0D1117", "border": "#30363D", "title": "#58A6FF",
        "text": "#C9D1D9", "muted": "#8B949E", "track": "#21262D",
    },
    "-light": {
        "bg": "#FFFFFF", "border": "#D0D7DE", "title": "#0969DA",
        "text": "#1F2328", "muted": "#59636E", "track": "#EAEEF2",
    },
}

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    contributionsCollection {
      contributionCalendar { totalContributions }
      totalCommitContributions
      totalPullRequestContributions
    }
    repositories(
      first: 100, after: $cursor, ownerAffiliations: OWNER,
      isFork: false, privacy: PUBLIC
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name } }
        }
      }
    }
  }
}
"""


def gh_graphql(cursor):
    """Run one page of the query through `gh api graphql`."""
    args = [
        "gh", "api", "graphql",
        "-f", f"query={QUERY}",
        "-F", f"login={USER}",
    ]
    args += ["-F", f"cursor={cursor}"] if cursor else ["-F", "cursor="]
    out = subprocess.run(args, capture_output=True, text=True)
    if out.returncode != 0:
        sys.exit(f"gh api graphql failed:\n{out.stderr}")
    return json.loads(out.stdout)["data"]["user"]


def collect():
    stars = repos = 0
    langs = Counter()
    cursor = None
    user = None
    while True:
        user = gh_graphql(cursor)
        page = user["repositories"]
        for repo in page["nodes"]:
            repos += 1
            stars += repo["stargazerCount"]
            for edge in repo["languages"]["edges"]:
                name = edge["node"]["name"]
                if name not in EXCLUDED_LANGS:
                    langs[name] += edge["size"]
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]

    contrib = user["contributionsCollection"]
    return {
        "stars": stars,
        "repos": repos,
        "followers": user["followers"]["totalCount"],
        "contributions": contrib["contributionCalendar"]["totalContributions"],
        "commits": contrib["totalCommitContributions"],
        "prs": contrib["totalPullRequestContributions"],
        "langs": langs,
    }


def esc(text):
    return str(text).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def frame(width, height, theme, title, body):
    """Card chrome shared by both SVGs. No CSS/animation: GitHub strips those."""
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" \
viewBox="0 0 {width} {height}" font-family="'Segoe UI',Ubuntu,Helvetica,Arial,sans-serif">
  <rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="6"
        fill="{theme['bg']}" stroke="{theme['border']}"/>
  <text x="25" y="35" font-size="16" font-weight="600" fill="{theme['title']}">{esc(title)}</text>
{body}
</svg>
"""


def render_stats(data, theme):
    rows = [
        ("Public repositories", data["repos"]),
        ("Contributions (last year)", data["contributions"]),
        ("Commits (last year)", data["commits"]),
        ("Pull requests (last year)", data["prs"]),
    ]
    body = []
    y = 70
    for label, value in rows:
        body.append(
            f'  <text x="25" y="{y}" font-size="13" fill="{theme["text"]}">{esc(label)}</text>\n'
            f'  <text x="{440 - 25}" y="{y}" font-size="13" font-weight="700" '
            f'text-anchor="end" fill="{theme["title"]}">{value:,}</text>'
        )
        y += 26
    return frame(440, y + 5, theme, f"{USER}'s GitHub stats", "\n".join(body))


def render_langs(data, theme):
    top = data["langs"].most_common(TOP_N)
    total = sum(size for _, size in top) or 1

    body = []
    # Stacked proportion bar.
    x = 25.0
    bar_w = 390.0
    body.append(
        f'  <rect x="25" y="55" width="{bar_w}" height="10" rx="5" fill="{theme["track"]}"/>'
    )
    for name, size in top:
        seg = bar_w * size / total
        color = LANG_COLORS.get(name, FALLBACK_LANG_COLOR)
        body.append(
            f'  <rect x="{x:.2f}" y="55" width="{seg:.2f}" height="10" fill="{color}"/>'
        )
        x += seg

    # Two-column legend.
    y = 95
    for i, (name, size) in enumerate(top):
        col_x = 25 if i % 2 == 0 else 225
        color = LANG_COLORS.get(name, FALLBACK_LANG_COLOR)
        pct = 100 * size / total
        body.append(
            f'  <circle cx="{col_x + 5}" cy="{y - 4}" r="5" fill="{color}"/>\n'
            f'  <text x="{col_x + 18}" y="{y}" font-size="12" fill="{theme["text"]}">'
            f'{esc(name)} <tspan fill="{theme["muted"]}">{pct:.1f}%</tspan></text>'
        )
        if i % 2 == 1:
            y += 24
    if len(top) % 2 == 1:
        y += 24

    return frame(440, y + 5, theme, "Most used languages", "\n".join(body))


def main():
    data = collect()
    for suffix, theme in THEMES.items():
        with open(f"stats{suffix}.svg", "w") as fh:
            fh.write(render_stats(data, theme))
        with open(f"languages{suffix}.svg", "w") as fh:
            fh.write(render_langs(data, theme))
    print(
        f"{data['repos']} repos, {data['stars']} stars, "
        f"{data['contributions']} contributions, "
        f"top langs: {', '.join(n for n, _ in data['langs'].most_common(TOP_N))}"
    )


if __name__ == "__main__":
    main()
