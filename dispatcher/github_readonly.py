"""Read-only GitHub Issues adapter for the dispatcher."""
from __future__ import annotations
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

class GitHubReadError(RuntimeError):
    pass

def _api_request(url: str, token: str | None = None) -> Any:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "steam-cart-bot-cloud-codex-dispatcher",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            if response.status != 200:
                raise GitHubReadError(f"GitHub API returned HTTP {response.status}")
            payload = response.read(2_000_001)
            if len(payload) > 2_000_000:
                raise GitHubReadError("GitHub API response exceeded 2 MB")
            return json.loads(payload.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise GitHubReadError(f"GitHub API returned HTTP {exc.code}") from exc
    except urllib.error.URLError as exc:
        raise GitHubReadError("GitHub API request failed") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GitHubReadError("GitHub API returned invalid JSON") from exc

def fetch_open_issues(
    repository: str,
    *,
    labels: tuple[str, ...] = ("codex-ready",),
    max_pages: int = 3,
    per_page: int = 100,
    token: str | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(repository, str) or repository.count("/") != 1:
        raise ValueError("repository must be owner/name")
    if not 1 <= max_pages <= 10:
        raise ValueError("max_pages must be between 1 and 10")
    if not 1 <= per_page <= 100:
        raise ValueError("per_page must be between 1 and 100")
    if not labels or any(not isinstance(x, str) or not x.strip() for x in labels):
        raise ValueError("at least one non-empty label is required")

    auth_token = token if token is not None else os.getenv("GITHUB_TOKEN")
    result: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        query = urllib.parse.urlencode({
            "state": "open", "per_page": per_page, "page": page,
            "sort": "updated", "direction": "desc", "labels": ",".join(labels),
        })
        url = f"https://api.github.com/repos/{repository}/issues?{query}"
        payload = _api_request(url, auth_token)
        if not isinstance(payload, list):
            raise GitHubReadError("Unexpected GitHub issues response shape")
        for item in payload:
            if not isinstance(item, dict) or "pull_request" in item:
                continue
            result.append({
                "number": item.get("number"),
                "title": item.get("title"),
                "body": item.get("body") or "",
                "state": item.get("state"),
                "labels": item.get("labels") or [],
                "html_url": item.get("html_url"),
                "updated_at": item.get("updated_at"),
            })
        if len(payload) < per_page:
            break
    return result
