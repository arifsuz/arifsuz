"""
update_readme.py
────────────────
Fetches the latest public repositories (sorted by stars) and the most
recent commits across all repos for the authenticated GitHub user, then
patches the README.md in-place between the sentinel comment markers:

  <!-- PROJECTS_START --> … <!-- PROJECTS_END -->
  <!-- ACTIVITY_START --> … <!-- ACTIVITY_END -->
  <!-- FUN_START -->       … <!-- FUN_END -->

Requires env vars:
  GITHUB_TOKEN    – a PAT or the built-in GITHUB_TOKEN from Actions
  GITHUB_USERNAME – the target GitHub username (default: arifsuz)
"""

import os
import random
import re
import sys
from datetime import datetime, timezone
from typing import Any

import requests

# ── Configuration ────────────────────────────────────────────────────────────

TOKEN    = os.environ.get("GITHUB_TOKEN", "")
USERNAME = os.environ.get("GITHUB_USERNAME", "arifsuz")
README   = "README.md"

MAX_PROJECTS             = 10   # rows in the projects table
MAX_ACTIVITY             = 10   # rows in the activity table
MAX_COMMIT_MESSAGE_LENGTH = 72  # truncate long commit message subjects
MAX_DESCRIPTION_LENGTH    = 80  # truncate long repository descriptions

QUOTES = [
    "The best error message is the one that never shows up. — Thomas Fuchs",
    "Code is like humor. When you have to explain it, it's bad. — Cory House",
    "First, solve the problem. Then, write the code. — John Johnson",
    "Make it work, make it right, make it fast. — Kent Beck",
    "Simplicity is the soul of efficiency. — Austin Freeman",
    "Programs must be written for people to read. — Harold Abelson",
    "Talk is cheap. Show me the code. — Linus Torvalds",
    "Any fool can write code that a computer can understand. Good programmers write code that humans can understand. — Martin Fowler",
    "The most disastrous thing that you can ever learn is your first programming language. — Alan Kay",
    "It's not a bug – it's an undocumented feature. — Anonymous",
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def gh_get(url: str, params: dict[str, Any] | None = None) -> Any:
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/vnd.github+json"}
    resp = requests.get(url, headers=headers, params=params, timeout=20)
    if not resp.ok:
        raise requests.HTTPError(
            f"GitHub API error {resp.status_code} for {url}: {resp.text[:200]}",
            response=resp,
        )
    return resp.json()


def replace_section(content: str, start_marker: str, end_marker: str, new_body: str) -> str:
    pattern = re.compile(
        re.escape(start_marker) + r".*?" + re.escape(end_marker),
        re.DOTALL,
    )
    replacement = f"{start_marker}\n{new_body}\n{end_marker}"
    updated, count = pattern.subn(replacement, content)
    if count == 0:
        print(f"[WARN] Markers not found: {start_marker!r} … {end_marker!r}", file=sys.stderr)
    return updated


# ── Fetch data ────────────────────────────────────────────────────────────────

def fetch_top_repos() -> list[dict]:
    """Return non-fork public repos sorted by stars descending."""
    repos: list[dict] = []
    page = 1
    while True:
        batch = gh_get(
            f"https://api.github.com/users/{USERNAME}/repos",
            params={"type": "owner", "per_page": 100, "page": page},
        )
        if not batch:
            break
        repos.extend(r for r in batch if not r.get("fork") and not r.get("archived"))
        page += 1
    repos.sort(key=lambda r: r.get("stargazers_count", 0), reverse=True)
    return repos[:MAX_PROJECTS]


def fetch_recent_activity() -> list[dict]:
    """Return the most recent commits across all repos."""
    commits: list[dict] = []
    repos = gh_get(
        f"https://api.github.com/users/{USERNAME}/repos",
        params={"type": "owner", "per_page": 50, "sort": "pushed"},
    )
    for repo in repos:
        if repo.get("fork") or repo.get("archived"):
            continue
        try:
            repo_commits = gh_get(
                f"https://api.github.com/repos/{USERNAME}/{repo['name']}/commits",
                params={"per_page": 3, "author": USERNAME},
            )
            for c in repo_commits:
                commits.append({
                    "repo":    repo["name"],
                    "message": c["commit"]["message"].split("\n")[0][:MAX_COMMIT_MESSAGE_LENGTH],
                    "date":    c["commit"]["author"]["date"][:10],
                    "url":     repo["html_url"],
                })
        except requests.HTTPError:
            continue
        if len(commits) >= MAX_ACTIVITY * 3:
            break

    commits.sort(key=lambda c: c["date"], reverse=True)
    return commits[:MAX_ACTIVITY]


# ── Build sections ────────────────────────────────────────────────────────────

def build_projects_table(repos: list[dict]) -> str:
    rows = ["| # | Proyek | Bahasa | ⭐ |", "|---|--------|--------|-----|"]
    for i, r in enumerate(repos, 1):
        name  = r["name"]
        url   = r["html_url"]
        desc  = r.get("description") or ""
        lang  = r.get("language") or "—"
        stars = r.get("stargazers_count", 0)
        label = f"[{name}]({url})"
        if desc:
            label += f" — {desc[:MAX_DESCRIPTION_LENGTH]}"
        rows.append(f"| {i} | {label} | {lang} | {stars} |")
    return "\n".join(rows)


def build_activity_table(commits: list[dict]) -> str:
    rows = ["| Waktu | Pesan Commit | Repositori |", "|-------|-------------|------------|"]
    for c in commits:
        rows.append(f"| {c['date']} | {c['message']} | [{c['repo']}]({c['url']}) |")
    return "\n".join(rows)


def build_quote() -> str:
    q = random.choice(QUOTES)
    return f"> *\"{q}\"*"


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    if not TOKEN:
        print("[ERROR] GITHUB_TOKEN is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"[INFO] Fetching data for @{USERNAME} …")

    repos   = fetch_top_repos()
    commits = fetch_recent_activity()

    print(f"[INFO] Found {len(repos)} repos, {len(commits)} commits.")

    with open(README, encoding="utf-8") as fh:
        content = fh.read()

    content = replace_section(
        content,
        "<!-- PROJECTS_START -->",
        "<!-- PROJECTS_END -->",
        build_projects_table(repos),
    )
    content = replace_section(
        content,
        "<!-- ACTIVITY_START -->",
        "<!-- ACTIVITY_END -->",
        build_activity_table(commits),
    )
    content = replace_section(
        content,
        "<!-- FUN_START -->",
        "<!-- FUN_END -->",
        build_quote(),
    )

    with open(README, "w", encoding="utf-8") as fh:
        fh.write(content)

    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    print(f"[INFO] README updated successfully at {now}.")


if __name__ == "__main__":
    main()
