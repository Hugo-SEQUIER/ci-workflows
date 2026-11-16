# ci-workflows

Shared GitHub workflows for Hugo-SEQUIER's repositories. Jobs run on the runner the caller
names in `runs-on`, normally the repository's own self-hosted runner on Hugo's server.

## Security checks

```yaml
jobs:
  security:
    uses: Hugo-SEQUIER/ci-workflows/.github/workflows/security.yml@v1
    with:
      runs-on: '["self-hosted","<repo label>"]'
```

- **secrets (gitleaks):** scans only the commits the push or pull request adds. Blocking.
  Silence a false positive with `.gitleaksignore` (fingerprint per line) in the calling repository.
- **dependencies (osv-scanner):** scans every lockfile. A pull request fails only when it adds a
  vulnerable dependency the base branch did not have. Older findings appear in the run summary
  and do not block. Accept a known risk with an `osv-scanner.toml` `[[IgnoredVulns]]` entry
  that has a `reason`.

Tool versions and SHA-256 checksums are pinned in `scripts/install-tool.sh`.

## Stale references

```yaml
jobs:
  stale-refs:
    uses: Hugo-SEQUIER/ci-workflows/.github/workflows/stale-refs.yml@v1
    with:
      runs-on: '["self-hosted","<repo label>"]'
```

Flags a test or doc line that still uses a name, CSS class, route or UI string the pull request
removed from the code, for example an e2e test that still clicks a deleted button. Only what the
pull request removed is checked, so older drift is never reported. It reads git objects only and
never runs the repository's code. Findings are warnings until the caller sets `fail: true`.
Silence one line with `stale-refs: ignore`; changelogs and decision logs are skipped.

## Runners

One runner per repository, each as its own Linux user (`gha-<label>`, no sudo, no Docker group),
with systemd limits (`Nice=10`, `MemoryMax=4G`, `CPUQuota=300%`) so CI never starves production
services on the same host. Public repositories require approval for outside contributors' workflow
runs, and route fork pull requests to GitHub-hosted runners.

## Review loop

[docs/review-loop.md](docs/review-loop.md): how author agents read the Hermes review comment and answer it.

## Releasing a change

The `v1` tag moves: commit to `main`, test from one repository with `@main` and `ci-ref: main`,
then `git tag -f v1 && git push -f origin v1`. A breaking change gets `v2`.
