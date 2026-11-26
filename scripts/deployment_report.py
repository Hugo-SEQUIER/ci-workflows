"""Deployment report: tell Cladeo what the project's deploy job deployed, and the new commits.

Reads GITHUB_REPOSITORY, set by GitHub Actions, and CLADEO_URL, CLADEO_KEY, PROJECT, ENVIRONMENT,
DEPLOY_RESULT, DEPLOY_URL and DEPLOYED_COMMIT, set by the deployment-report workflow. Runs in a
clone of the project with its whole history. Asks Cladeo for the last successful deployment of
the environment, lists the commits from there to the deployed commit with git, and sends the
report. Prints the report and Cladeo's answer, never the key. Exits 1 when a setting is missing
or a call fails.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime

# Cladeo takes at most this many commits in one report.
MAX_COMMITS = 1000
SETTINGS = ("GITHUB_REPOSITORY", "CLADEO_URL", "CLADEO_KEY", "PROJECT", "ENVIRONMENT",
            "DEPLOY_RESULT", "DEPLOYED_COMMIT")


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
            "User-Agent": "ci-workflows-deployment-report",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def new_commits(last, deployed):
    """
    The commits after `last` up to `deployed`, newest first. With no `last`, or one this history
    lacks, every commit up to `deployed`: the first deployment of an environment ships them all.
    """
    if last is not None:
        listed = subprocess.run(["git", "rev-list", f"--max-count={MAX_COMMITS}", f"{last}..{deployed}"],
                                capture_output=True, text=True)
        if listed.returncode == 0:
            return listed.stdout.split()
        print(f"{last}, the last successful deployment, is not in this history.")
    listed = subprocess.run(["git", "rev-list", f"--max-count={MAX_COMMITS}", deployed],
                            capture_output=True, text=True, check=True)
    return listed.stdout.split()


def main():
    missing = [name for name in SETTINGS if not os.environ.get(name)]
    if missing:
        print(
            "Missing: " + ", ".join(missing) + ". Set the repository variable CLADEO_URL to the "
            "Cladeo address and the secret CLADEO_KEY to a Cladeo agent key, and pass them, the "
            "project, the environment and the deploy job's result to deployment-report.yml."
        )
        return 1
    env = os.environ
    cladeo, key = env["CLADEO_URL"].rstrip("/"), env["CLADEO_KEY"]
    where = {"project": env["PROJECT"], "repository": env["GITHUB_REPOSITORY"],
             "environment": env["ENVIRONMENT"]}
    deployed = subprocess.run(["git", "rev-parse", env["DEPLOYED_COMMIT"]], capture_output=True,
                              text=True, check=True).stdout.strip()
    try:
        last = call(f"{cladeo}/v1/deployments/last-success?{urllib.parse.urlencode(where)}", key)
        report = where | {
            "commit": deployed,
            "commits": new_commits(last["deployment"] and last["deployment"]["commit"], deployed),
            "status": "succeeded" if env["DEPLOY_RESULT"] == "success" else "failed",
            "finished_at": datetime.now(UTC).isoformat(),
        }
        if env.get("DEPLOY_URL"):
            report["url"] = env["DEPLOY_URL"]
        print(f"Deployment report: {json.dumps(report | {'commits': len(report['commits'])})}")
        answer = call(f"{cladeo}/v1/deployment-reports", key, report)
    except urllib.error.HTTPError as error:
        print(f"Cladeo answered HTTP {error.code}: {error.read().decode(errors='replace')[:2000]}")
        return 1
    except OSError as error:
        print(f"Cladeo did not answer at {cladeo}: {error}")
        return 1
    for task in answer["tasks"] or [{"task": "no merged task is in these commits"}]:
        print(f"  {json.dumps(task)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
