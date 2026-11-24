"""Merge report: find the pull request merged as the pushed commit and report it to Cladeo.

Reads GITHUB_API_URL, GITHUB_REPOSITORY, GITHUB_SHA and GITHUB_TOKEN, set by GitHub Actions, and
CLADEO_URL and CLADEO_KEY, set by the merge-report workflow. Prints each report and Cladeo's
answer, never the key. Exits 1 when a setting is missing or a call fails.
"""

import json
import os
import sys
import urllib.error
import urllib.request


def call(url, token, body=None):
    """GET, or POST `body` as JSON, with a bearer token. Returns the decoded JSON answer."""
    request = urllib.request.Request(
        url,
        data=None if body is None else json.dumps(body).encode(),
        method="GET" if body is None else "POST",
        headers={
            "Accept": "application/json",
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "User-Agent": "ci-workflows-merge-report",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def main():
    missing = [
        name
        for name in ("GITHUB_REPOSITORY", "GITHUB_SHA", "GITHUB_TOKEN", "CLADEO_URL", "CLADEO_KEY")
        if not os.environ.get(name)
    ]
    if missing:
        print(
            "Missing: " + ", ".join(missing) + ". Set the repository variable CLADEO_URL to the "
            "Cladeo address and the secret CLADEO_KEY to a Cladeo agent key, and pass them to "
            "merge-report.yml as `cladeo-url` and `CLADEO_KEY`."
        )
        return 1
    repository, sha = os.environ["GITHUB_REPOSITORY"], os.environ["GITHUB_SHA"]
    api = os.environ.get("GITHUB_API_URL", "https://api.github.com")
    cladeo = os.environ["CLADEO_URL"].rstrip("/")
    try:
        pulls = call(f"{api}/repos/{repository}/commits/{sha}/pulls", os.environ["GITHUB_TOKEN"])
    except urllib.error.HTTPError as error:
        print(f"GitHub answered HTTP {error.code} for the pull requests of {sha}. The caller job "
              "needs `pull-requests: read`.")
        return 1
    # Squash, merge and rebase merges all record the pushed commit as the merge commit.
    merged = [p for p in pulls if p.get("merged_at") and p.get("merge_commit_sha") == sha]
    if not merged:
        print(f"No pull request was merged as {sha}: nothing to report.")
        return 0
    failed = False
    for pull in merged:
        body = {
            "repository": repository,
            "pull_request_number": pull["number"],
            "merged_commit": sha,
        }
        print(f"Merge report: {json.dumps(body)}")
        try:
            answer = call(f"{cladeo}/v1/merge-reports", os.environ["CLADEO_KEY"], body)
        except urllib.error.HTTPError as error:
            print(f"Cladeo answered HTTP {error.code}: {error.read().decode(errors='replace')[:2000]}")
            failed = True
            continue
        except OSError as error:
            print(f"Cladeo did not answer at {cladeo}: {error}")
            failed = True
            continue
        for task in answer["tasks"] or [{"task": "no task has this pull request"}]:
            print(f"  {json.dumps(task)}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
