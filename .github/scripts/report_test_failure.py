#!/usr/bin/env python3
"""
Automated Issue Manager for Daily Test Suite Failures.
- Automatically opens/updates an issue if daily unittest suite fails.
- Automatically closes the issue when the test suite passes again.
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

GITHUB_API_URL = "https://api.github.com"
ISSUE_LABEL = "test-failure"
AUTO_LABEL = "automated-check"
ISSUE_TITLE = "[Test Failure] Daily Test Suite Broken"


class GitHubClient:
    def __init__(self, token: str, repository: str):
        self.token = token
        self.repository = repository
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Daily-Test-Reporter"
        }

    def _request(self, method: str, endpoint: str, data: Optional[Dict[str, Any]] = None) -> Any:
        url = f"{GITHUB_API_URL}/repos/{self.repository}{endpoint}"
        payload = json.dumps(data).encode("utf-8") if data is not None else None
        req = urllib.request.Request(url, data=payload, headers=self.headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                if resp.status in (200, 201):
                    return json.loads(resp.read().decode("utf-8"))
                return None
        except urllib.error.HTTPError as e:
            err_body = e.read().decode("utf-8")
            print(f"[GitHub API Error] {method} {url} returned HTTP {e.code}: {err_body}")
            return None
        except Exception as e:
            print(f"[Network Error] {method} {url}: {e}")
            return None

    def get_open_test_issues(self) -> List[Dict[str, Any]]:
        endpoint = f"/issues?state=open&labels={urllib.parse.quote(ISSUE_LABEL)}&per_page=50"
        res = self._request("GET", endpoint)
        if not isinstance(res, list):
            return []
        return [i for i in res if "[Test Failure]" in i.get("title", "")]

    def open_issue(self, title: str, body: str, labels: List[str]) -> Optional[Dict[str, Any]]:
        endpoint = "/issues"
        return self._request("POST", endpoint, {"title": title, "body": body, "labels": labels})

    def comment_issue(self, issue_number: int, comment: str) -> Optional[Dict[str, Any]]:
        endpoint = f"/issues/{issue_number}/comments"
        return self._request("POST", endpoint, {"body": comment})

    def close_issue(self, issue_number: int, reason_comment: str) -> None:
        self.comment_issue(issue_number, reason_comment)
        endpoint = f"/issues/{issue_number}"
        self._request("PATCH", endpoint, {"state": "closed", "state_reason": "completed"})


def main():
    parser = argparse.ArgumentParser(description="Report daily test failures to GitHub Issues")
    parser.add_argument("--status", choices=["success", "failure"], required=True, help="Test run status")
    parser.add_argument("--log-file", type=str, default="", help="Path to test output log file")
    args = parser.parse_args()

    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    if not token or not repo:
        print("[Reporter] GH_TOKEN or GITHUB_REPOSITORY not set. Skipping GitHub issue reporting.")
        sys.exit(0)

    client = GitHubClient(token, repo)
    open_issues = client.get_open_test_issues()
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    log_content = ""
    if args.log_file and os.path.exists(args.log_file):
        try:
            with open(args.log_file, "r", encoding="utf-8", errors="ignore") as f:
                log_content = f.read().strip()
        except Exception as e:
            log_content = f"Could not read log file: {e}"

    # Truncate log to last 3000 chars if excessively large
    if len(log_content) > 3000:
        log_content = "...\n" + log_content[-3000:]

    if args.status == "failure":
        body = f"""### 🚨 Daily Test Suite Execution Failure

> **Reported by:** Automated Daily Test Runner  
> **Timestamp:** `{now_str}`  
> **Repository:** `{repo}`  

---

### Failure Output / Traceback
```text
{log_content if log_content else 'No output captured.'}
```

---
### Suggested Remediation Steps
1. Run the test suite locally: `python3 -m unittest discover -s tests -p "test_*.py"`.
2. Inspect failing assertions or tracebacks above.
3. Commit fixes to `main` branch. This issue will automatically close upon the next successful test run.
"""
        if open_issues:
            issue = open_issues[0]
            print(f"[Reporter] Appending failure comment to open issue #{issue['number']}...")
            client.comment_issue(
                issue["number"],
                f"### ⚠️ Daily Test Suite Failed Again ({now_str})\n\n```text\n{log_content}\n```"
            )
        else:
            print("[Reporter] Opening new GitHub issue for test suite failure...")
            client.open_issue(ISSUE_TITLE, body, [ISSUE_LABEL, AUTO_LABEL])

    elif args.status == "success":
        if open_issues:
            for issue in open_issues:
                print(f"[Reporter] Resolving and closing issue #{issue['number']}...")
                client.close_issue(
                    issue["number"],
                    f"### ✅ Daily Test Suite Restored ({now_str})\n\nAll unit tests passed successfully on latest commit."
                )
        else:
            print("[Reporter] All tests passed and no open test issues. Clean.")


if __name__ == "__main__":
    main()
