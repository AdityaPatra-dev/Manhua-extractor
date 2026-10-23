#!/usr/bin/env python3
"""
Automated Issue Manager for Scraper Health Sentinel
Reads .github/reports/scraper_health.json and manages GitHub issues:
  1. Opens a new issue if a scraper genuinely fails (verified across dual passes) and no open issue exists.
  2. Appends a daily comment if an issue is already open and still failing.
  3. Automatically closes the issue when a broken scraper passes again.

Uses the GitHub REST API with GH_TOKEN / GITHUB_TOKEN (Personal Access Token or Action Token).
"""

from __future__ import annotations

import os
import sys
import re
import json
import urllib.request
import urllib.parse
import urllib.error
from typing import Dict, List, Any, Optional

GITHUB_API_URL = "https://api.github.com"
ISSUE_LABEL = "scraper-broken"
AUTO_LABEL = "automated-check"


class GitHubClient:
    def __init__(self, token: str, repository: str):
        self.token = token
        self.repository = repository
        self.headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Scraper-Sentinel-Reporter"
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

    def get_open_issues(self) -> List[Dict[str, Any]]:
        """Fetch all currently open scraper-broken issues."""
        endpoint = f"/issues?state=open&labels={urllib.parse.quote(ISSUE_LABEL)}&per_page=100"
        res = self._request("GET", endpoint)
        return res if isinstance(res, list) else []

    def create_issue(self, title: str, body: str, labels: List[str]) -> Optional[Dict[str, Any]]:
        """Create a new GitHub issue."""
        payload = {
            "title": title,
            "body": body,
            "labels": labels
        }
        return self._request("POST", "/issues", payload)

    def add_comment(self, issue_number: int, comment: str) -> Optional[Dict[str, Any]]:
        """Add a comment to an existing issue."""
        payload = {"body": comment}
        return self._request("POST", f"/issues/{issue_number}/comments", payload)

    def close_issue(self, issue_number: int, reason: str = "completed") -> Optional[Dict[str, Any]]:
        """Close an existing issue."""
        payload = {"state": "closed", "state_reason": reason}
        return self._request("PATCH", f"/issues/{issue_number}", payload)


def format_issue_title(source_name: str, source_key: str, category: Optional[str] = None) -> str:
    if category == "BOT_CHALLENGE":
        return f"[Bot-Locked] {source_name} ({source_key})"
    elif category == "DOMAIN_OUTAGE":
        return f"[Site Down] {source_name} ({source_key})"
    elif category == "SELECTOR_MISMATCH":
        return f"[Selector Broken] {source_name} ({source_key})"
    return f"[Scraper Down] {source_name} ({source_key})"


def format_issue_body(result: Dict[str, Any]) -> str:
    name = result.get("name")
    key = result.get("key")
    domain = result.get("domain") or "N/A"
    stype = result.get("type") or "N/A"
    category = result.get("failure_category") or "GENUINE_ERROR"
    sample_series = result.get("sample_series_url") or "None detected"
    sample_chapter = result.get("sample_chapter_url") or "None detected"
    timestamp = result.get("timestamp")

    search_status = result.get("search_status")
    search_err = result.get("search_error") or "None"
    search_hits = result.get("search_hits", 0)

    direct_status = result.get("direct_parse_status")
    direct_err = result.get("direct_parse_error") or "None"
    chapters_found = result.get("chapters_found", 0)

    image_status = result.get("image_extract_status")
    image_err = result.get("image_extract_error") or "None"
    panels_found = result.get("panels_found", 0)

    remediation = []
    if category == "BOT_CHALLENGE":
        remediation.append(f"1. **Anti-Bot Challenge Detected**: Target domain `{domain}` is blocking automated requests with Cloudflare Turnstile / DDoS-Guard.")
        remediation.append(f"2. In accordance with project policy for bot-locked domains, consider retiring `{key}` from active search tiers in `core/search/dispatcher.py`.")
    elif category == "SELECTOR_MISMATCH":
        remediation.append(f"1. **HTML Selector Mismatch**: The site loaded successfully (HTTP 200), but CSS selectors for titles, chapters, or panels did not match.")
        remediation.append(f"2. Inspect the DOM structure of `{sample_series or domain}` and update selectors in `core/search/dispatcher.py` or `extractors/`.")
    elif category == "DOMAIN_OUTAGE":
        remediation.append(f"1. **Domain Unreachable**: The domain `{domain}` failed DNS resolution or returned a connection error.")
        remediation.append(f"2. Check if the site has changed domains or permanently ceased operations.")
    else:
        remediation.append(f"1. Test locally using `python3 .github/scripts/check_scrapers.py --sources {key}`.")
        remediation.append(f"2. Check if the site structure or endpoints have updated.")

    remediation_str = "\n".join(remediation)

    return f"""### 🚨 Scraper Healthcheck Failure: {name}

> **Reported by:** @AdityaPatra-dev (Automated Scraper Sentinel)  
> **Timestamp:** `{timestamp}`  
> **Dual-Pass Verification:** ❌ Confirmed failed across initial batch + isolated sequential retry pass (transient IP rate-limiting ruled out).  
> **Category:** `{category}`

---

### Source Information
| Property | Value |
| :--- | :--- |
| **Source Name** | **{name}** |
| **Source Key** | `{key}` |
| **Engine / Type** | `{stype}` |
| **Target Domain** | `{domain}` |
| **Sample Series URL** | {sample_series} |
| **Sample Chapter URL** | {sample_chapter} |

---

### Phase Breakdown & Diagnostics

#### 1. 🔍 Global Search Test
- **Status:** `{search_status}`
- **Hits Found:** `{search_hits}`
- **Details:** `{search_err}`

#### 2. 🔗 Direct Link Parsing (Chapter Inspection)
- **Status:** `{direct_status}`
- **Chapters Extracted:** `{chapters_found}`
- **Details:** `{direct_err}`

#### 3. 🖼️ Chapter Image Extraction
- **Status:** `{image_status}`
- **Panels Extracted:** `{panels_found}`
- **Details:** `{image_err}`

---

### Non-Compliance Summary
> **Reason:** {result.get("non_compliance_reason") or "Unknown error"}

### Suggested Remediation Steps
{remediation_str}
"""


def format_update_comment(result: Dict[str, Any]) -> str:
    timestamp = result.get("timestamp")
    reason = result.get("non_compliance_reason") or "Scraper is still non-compliant"
    category = result.get("failure_category") or "GENUINE_ERROR"
    return f"""🔄 **Automated Sentinel Daily Update** (`{timestamp}`)

The daily healthcheck ran again and this source failed both initial and isolated sequential retry passes:
- **Category:** `{category}`
- **Reason:** {reason}
- **Search Status:** `{result.get('search_status')}` ({result.get('search_error') or 'OK'})
- **Direct Parse Status:** `{result.get('direct_parse_status')}` ({result.get('direct_parse_error') or 'OK'})
- **Image Extract Status:** `{result.get('image_extract_status')}` ({result.get('image_extract_error') or 'OK'})

Will re-check during tomorrow's scheduled run.
"""


def main():
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY", "AdityaPatra-dev/Manhua-extractor")

    report_path = os.environ.get("REPORT_PATH", ".github/reports/scraper_health.json")
    if not os.path.exists(report_path):
        print(f"Error: Report file not found at {report_path}")
        sys.exit(1)

    with open(report_path, "r", encoding="utf-8") as f:
        report_data = json.load(f)

    results = report_data.get("results", [])
    if not results:
        print("No test results found in report.")
        sys.exit(0)

    if not token:
        print("Notice: No GH_TOKEN or GITHUB_TOKEN set. Printing summary locally (dry-run mode).")
        for r in results:
            if r["overall_status"] == "FAIL":
                print(f"[FAIL] Would open/update issue for: {r['name']} ({r['key']}) -> {r['non_compliance_reason']}")
            else:
                print(f"[PASS] Source healthy: {r['name']} ({r['key']})")
        sys.exit(0)

    client = GitHubClient(token=token, repository=repo)

    print(f"Connecting to GitHub repository: {repo}")
    open_issues = client.get_open_issues()
    print(f"Found {len(open_issues)} existing open scraper issues.")

    # Map existing open issue titles to issue objects by extracting the key inside parentheses
    open_issues_by_key = {}
    for issue in open_issues:
        title = issue.get("title", "")
        m = re.search(r'\(([^)]+)\)$', title.strip())
        if m:
            extracted_key = m.group(1).strip().lower()
            open_issues_by_key[extracted_key] = issue

    created_count = 0
    updated_count = 0
    closed_count = 0

    for r in results:
        key = r.get("key", "").lower()
        name = r.get("name", key)
        status = r.get("overall_status")
        category = r.get("failure_category")

        existing_issue = open_issues_by_key.get(key)

        if status == "FAIL":
            if existing_issue:
                # Add daily comment
                issue_num = existing_issue["number"]
                comment_text = format_update_comment(r)
                client.add_comment(issue_num, comment_text)
                print(f"[UPDATED] Added daily failure comment to Issue #{issue_num} ({name})")
                updated_count += 1
            else:
                # Create new issue with verified failure category
                title = format_issue_title(name, key, category)
                body = format_issue_body(r)
                labels = [ISSUE_LABEL, AUTO_LABEL]
                created = client.create_issue(title, body, labels)
                if created:
                    print(f"[CREATED] Opened Issue #{created.get('number')} for {name}")
                    created_count += 1
                else:
                    print(f"[ERROR] Failed to create issue for {name}")
        elif status == "PASS":
            if existing_issue:
                # Auto-resolve
                issue_num = existing_issue["number"]
                close_comment = (
                    f"✅ **Auto-Resolved by Daily Sentinel** (`{r.get('timestamp')}`)\n\n"
                    f"This scraper passed all compliance checks during today's healthcheck run:\n"
                    f"- Global Search: Passed ({r.get('search_hits')} hits)\n"
                    f"- Direct Link Parsing: Passed ({r.get('chapters_found')} chapters)\n"
                    f"- Image Extraction: Passed ({r.get('panels_found')} panels)\n\n"
                    f"Closing this issue automatically."
                )
                client.add_comment(issue_num, close_comment)
                client.close_issue(issue_num, reason="completed")
                print(f"[CLOSED] Issue #{issue_num} auto-resolved for {name}!")
                closed_count += 1

    print("=" * 38)
    print(f"Issue Management Summary: {created_count} created, {updated_count} updated, {closed_count} auto-closed.")


if __name__ == "__main__":
    main()
