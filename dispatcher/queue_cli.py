"""Read-only queue inspection entry point."""
from __future__ import annotations
import argparse
import json
import os
import sys
from dispatcher import select_next_task
from dispatcher.github_readonly import GitHubReadError, fetch_open_issues

def main() -> int:
    parser = argparse.ArgumentParser(description="Read and validate the Cloud Codex issue queue.")
    parser.add_argument("--repository", default=os.getenv("GITHUB_REPOSITORY", ""))
    parser.add_argument("--max-pages", type=int, default=2)
    parser.add_argument("--per-page", type=int, default=100)
    args = parser.parse_args()
    if not args.repository:
        parser.error("--repository or GITHUB_REPOSITORY is required")
    try:
        issues = fetch_open_issues(args.repository, max_pages=args.max_pages, per_page=args.per_page)
    except (GitHubReadError, ValueError) as exc:
        print(json.dumps({"status": "error", "reason": str(exc)}))
        return 2
    selected = select_next_task(issues)
    output = {
        "status": "eligible" if selected else "no_eligible_task",
        "issues_read": len(issues),
        "selected": None if selected is None else {
            "number": selected.issue_number, "title": selected.title, "priority": selected.priority,
        },
        "mode": "read_only", "codex_invoked": False, "repository_mutated": False,
    }
    print(json.dumps(output, ensure_ascii=False, sort_keys=True))
    return 0

if __name__ == "__main__":
    sys.exit(main())
