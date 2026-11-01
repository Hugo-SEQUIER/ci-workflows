# Hermes review loop: how an author agent reads and answers a review

Every open pull request in Hugo's repositories gets one **Hermes review** comment, updated in
place on each new push (usually 10 to 20 minutes after the push settles). It has three parts:

- **Code review** items `C1`, `C2`, ...: correctness, error handling, contracts, tests.
- **Security** items `X1`, ...: only on a failed security pass. On public repositories the
  details are sent to Hugo privately and the comment only says that the gate failed.
- **Simplify** items `S1`, ...: AI slop to cut (dead code, needless wrappers, impossible-state
  checks, duplicate helpers, comments that restate code, leftover debug logs). Never blocking.

## Read it

The comment starts with `<!-- hermes-pr-review head=<sha> -->` and ends with a hidden JSON block:

```bash
gh api repos/<owner>/<repo>/issues/<pr>/comments --paginate \
  --jq '.[] | select(.body | contains("hermes-pr-review-data")) | .body' |
python3 -c 'import sys,re,json; m=re.findall(r"<!-- hermes-pr-review-data\n(.*?)\n-->", sys.stdin.read(), re.S); print(json.dumps(json.loads(m[-1]), indent=1) if m else "no Hermes review yet")'
```

```json
{
  "version": 1,
  "head": "<full sha the review is about>",
  "round": 1,
  "code_verdict": "passed | changes suggested | changes needed",
  "security_verdict": "pass | fail | not applicable | private",
  "items": [
    {"id": "C1", "kind": "code", "blocking": true, "path": "src/a.ts", "line": 42,
     "problem": "...", "fix": "..."},
    {"id": "S1", "kind": "simplify", "blocking": false, "path": "src/b.ts", "line": 10,
     "problem": "what to cut", "fix": "the shorter version, and why behavior is identical"}
  ]
}
```

Only act on a review whose `head` equals the PR's current head (`gh pr view <pr> --json headRefOid`).
An older head means a newer review is coming.

## Answer it

1. Fix every item with `blocking: true`.
2. Apply each `simplify` item you agree with. Decline one only with a concrete reason
   (for example: the "dead" export is used by a script outside `src/`).
3. Run the repository's normal checks, then push **one** commit:
   `refactor: apply Hermes review (round <n>)`.
4. Reply on the PR with one comment that starts with `<!-- hermes-pr-fix head=<new sha> reviewed=<reviewed sha> -->` and lists
   `Applied: C1, S1, S3` and `Declined: S2 (reason)`. The next review reads it and does not repeat
   declined items.

## Who answers

- **Claude Code or any interactive agent session:** the author answers, as above. Each repository's AGENTS.md has this loop.
- **Hermes cron lanes** (branches like `seo/...`, `news/...`, `feat/...`): the lane's run has ended, so the Hermes job "PR review fixer" answers in its place, with the same rules. It never touches security items, dependencies, CI or deploy config.

## Limits

- At most **2 fix rounds** per pull request. From round 3 the review lists only blocking items and
  no new simplify suggestions, so the loop always ends.
- Never merge, approve, or enable auto-merge. Hugo merges.
- Never force-push over someone else's commits. If the push is rejected, the branch moved: stop.
