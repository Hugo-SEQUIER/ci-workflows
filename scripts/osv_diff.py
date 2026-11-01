#!/usr/bin/env python3
"""Compare two osv-scanner JSON reports and list the vulnerabilities only the head has.

usage: osv_diff.py HEAD_JSON [BASE_JSON]

Without BASE_JSON every vulnerability in HEAD_JSON is reported and the exit code is 0
(report only, used on pushes to the default branch). With BASE_JSON the exit code is 1
when the head adds a vulnerable dependency the base did not have, so a pull request
fails only for what it introduced, never for older debt.

Writes a Markdown summary to $GITHUB_STEP_SUMMARY when that variable is set.
"""

import json
import os
import sys


def load(path):
    """Return {(ecosystem, package): [alias sets]} for every vulnerability group."""
    with open(path, encoding="utf-8") as fh:
        text = fh.read().strip()
    data = json.loads(text) if text else {}
    found = {}
    for result in data.get("results") or []:
        for pkg in result.get("packages") or []:
            info = pkg.get("package") or {}
            key = (info.get("ecosystem", "?"), info.get("name", "?"))
            version = info.get("version", "?")
            summaries = {v.get("id"): (v.get("summary") or "").strip() for v in pkg.get("vulnerabilities") or []}
            groups = pkg.get("groups") or [{"ids": [i]} for i in summaries]
            for group in groups:
                ids = set(group.get("ids") or [])
                if not ids:
                    continue
                severity = group.get("max_severity") or ""
                summary = next((summaries[i] for i in sorted(ids) if summaries.get(i)), "")
                found.setdefault(key, []).append(
                    {"ids": ids, "version": version, "severity": severity, "summary": summary}
                )
    return found


def line(key, vuln):
    eco, name = key
    ids = ", ".join(sorted(vuln["ids"]))
    sev = f" (CVSS {vuln['severity']})" if vuln["severity"] else ""
    summary = f": {vuln['summary'][:140]}" if vuln["summary"] else ""
    return f"- `{name}@{vuln['version']}` ({eco}) {ids}{sev}{summary}"


def main(argv):
    if len(argv) not in (2, 3):
        print(__doc__, file=sys.stderr)
        return 2
    head = load(argv[1])
    base = load(argv[2]) if len(argv) == 3 else None

    if base is None:
        rows = [line(k, v) for k, vs in sorted(head.items()) for v in vs]
        title = f"Dependencies: {len(rows)} known vulnerabilities (report only)"
        failed = False
    else:
        rows = []
        for key, vulns in sorted(head.items()):
            old = base.get(key, [])
            for vuln in vulns:
                if not any(vuln["ids"] & o["ids"] for o in old):
                    rows.append(line(key, vuln))
        existing = sum(len(v) for v in base.values())
        title = (
            f"Dependencies: this PR adds {len(rows)} vulnerable dependencies"
            if rows
            else f"Dependencies: nothing new ({existing} older findings on the base, not blocking)"
        )
        failed = bool(rows)

    body = "\n".join([f"### {title}", "", *rows]) + "\n"
    print(body)
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as fh:
            fh.write(body)
    if failed:
        print("Upgrade or replace the dependencies above, or add a justified entry to osv-scanner.toml.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
