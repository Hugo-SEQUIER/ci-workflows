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

## Checks

```yaml
jobs:
  check:
    uses: Hugo-SEQUIER/ci-workflows/.github/workflows/check.yml@v1
    with:
      runs-on: '["self-hosted","<repo label>"]'
      command: just check
      uv-version: "0.12.21"
      node-version: "24"
      bun-version: "1.4.2"
      report: check-report.sarif
```

Installs the toolchains whose version the caller sets (uv, Node, Bun) and runs the project's check
command in `working-directory` (default: the repository root). The checks themselves live in the
project. When `report` is set, the file is kept as the `check-report` artifact of the run, also
when the command fails. A service the project needs, such as Postgres, stays in a job of the
project's own workflow.

## Checks on Colab

```yaml
jobs:
  check:
    uses: Hugo-SEQUIER/ci-workflows/.github/workflows/check.yml@v1
    with:
      runs-on: '["self-hosted","<repo label>"]'
      command: make check
      colab: true        # colab-gpu: L4 (default), T4 or CPU; colab-min-minutes: 3 (default)
```

With `colab: true` a slow check runs on a fresh Google Colab VM instead of the runner: an L4
machine has 12 cores and 52 GB, against the 3 cores a runner gets on the host, and is billed
about 2.3 compute units an hour of VM time (T4 and CPU have 2 cores). The VM clones the commit the
runner would test (on a pull request, its merge with the base) with the job's `GITHUB_TOKEN`,
installs the toolchains the job names (uv, Node, Bun), runs the command and sends back its log,
exit code and `report`. The VM is stopped after every job.

Colab only takes checks that are worth it. Each run on the runner records how long the check
took, and Colab takes it once the median of its runner times over the last 30 days is at least
`colab-min-minutes` (3 by default; 0 sends it to Colab every time). A new check therefore runs on
the runner 3 times first. A VM costs about 40 seconds of start, setup and stop, so a check of a
minute or less is faster on the runner.

The check runs on the runner as before, with a notice in the run that says why, whenever Colab
does not take it: a light check, no Colab access on the runner (GitHub-hosted runners, so fork
pull requests too), no L4 free within 30 seconds (then Colab is skipped for 10 minutes), fewer
than 40 compute units left, 4 VMs already busy, the repository's 240 VM-minutes of the day used,
a setting the VM does not handle (such as `node-version: lts/*`), or a VM that fails to start,
set up or answer. A failing check never falls back: it fails like on the runner. A job with
`colab: true` gets 40 minutes instead of 20, room for a late fallback. The VM has no Docker and
no project services, so a job that needs Postgres keeps its own job.

The host side lives in `colab/`: `colab-ci-run` (the broker), `colab_vm.py` (starts and releases
a VM by a notebook hash the broker chose, so a VM placed after a timeout or a cancel is still
released), `vm-job.sh` (runs on the VM) and `install.sh`. The Colab login belongs to the
`colabci` user; runner users (group `colab-ci-users`) may only start `colab-ci-run` as `colabci`
through sudo, with the job on stdin, so a runner never reads the login, and each may only send
jobs for its own repository (`/etc/colab-ci/runners.json`). `colab-ci-reaper.timer` releases any
VM a dead job left behind. Install or update on the host, then log in once:

```bash
sudo colab/install.sh
sudo -u colabci env HOME=/var/lib/colab-ci PYTHON_KEYRING_BACKEND=keyrings.alt.file.PlaintextKeyring \
  OAUTHLIB_RELAX_TOKEN_SCOPE=1 /opt/colab-ci/venv/bin/colab whoami   # prints a URL, paste the code
```

A new runner user joins `colab-ci-users` and `runners.json` when `install.sh` runs again; its
runner sees the group after its next restart. Until then its checks run on the runner.

## Merge report

```yaml
jobs:
  merge-report:
    if: github.event_name == 'push'
    uses: Hugo-SEQUIER/ci-workflows/.github/workflows/merge-report.yml@v1
    permissions:
      contents: read
      pull-requests: read
    with:
      runs-on: '["self-hosted","<repo label>"]'
      cladeo-url: ${{ vars.CLADEO_URL }}
    secrets:
      CLADEO_KEY: ${{ secrets.CLADEO_KEY }}
```

On a push to the default branch, asks GitHub which pull request was merged as the pushed commit
(squash, merge or rebase) and sends `{"repository", "pull_request_number", "merged_commit"}` to
Cladeo's `POST /v1/merge-reports`, so the task of that pull request moves to done. A push that
merged no pull request sends nothing. Needs the repository variable `CLADEO_URL` and the secret
`CLADEO_KEY` (a Cladeo agent key); without them the job fails and names what is missing. The key
is never printed. The caller job grants `pull-requests: read`, which the lookup needs.

## Deployment report

```yaml
jobs:
  deployment-report-stg:
    needs: deploy-stg
    if: always() && needs.deploy-stg.result != 'skipped'
    uses: Hugo-SEQUIER/ci-workflows/.github/workflows/deployment-report.yml@v1
    with:
      runs-on: '["self-hosted","<repo label>"]'
      cladeo-url: ${{ vars.CLADEO_URL }}
      project: <Cladeo project key>
      environment: stg
      deploy-result: ${{ needs.deploy-stg.result }}
      url: https://stg.example.com
    secrets:
      CLADEO_KEY: ${{ secrets.CLADEO_KEY }}
```

Runs after the project's own deploy job, whether it passed or failed, and sends Cladeo's
`POST /v1/deployment-reports`: the project, the environment, the deployed commit, `succeeded` when
the deploy job's result is `success` and `failed` otherwise, and the URL. `commits` lists the
commits between the last successful deployment of that environment, read from Cladeo's
`GET /v1/deployments/last-success`, and the deployed commit (`git rev-list`, at most 1,000, on a
clone with the whole history). The first deployment of an environment, or a last commit this
history lacks, sends every commit up to the deployed one (at most 1,000), because that deployment
shipped them all. Cladeo links the
report to each task whose merge commit it contains. One call per environment. Pull requests send
nothing, so a fork cannot use the key; the key is never printed.

## Project template

`copier.yml` and `template/` make a project ready for the factory: the `make check`, `make fix` and
`make verify` commands (`scripts/check.py` holds the checks, their fixes and the tool versions),
the Ruff configuration, Biome for TypeScript, ast-grep checks in `checks/shared/` (from the
template) and `checks/project/` (the project's own), the CI caller of the check, security and stale-references workflows (with the deployment report as a commented example),
and an `AGENTS.md` that routes. Python and TypeScript; uv is needed, and Bun for TypeScript.

```bash
uvx copier copy gh:Hugo-SEQUIER/ci-workflows <folder>   # asks the name, the runner label, TypeScript
uvx copier update                                       # in the project: the newest template version
```

`make check` also runs four setup checks, which Cladeo's setup path asks for before the setup
task of a project can enter review (docs/factory/CHECKS.md in Hugo-SEQUIER/systems):

| Check | Passes when |
|---|---|
| `setup-template` | `.copier-answers.yml` names this template (`_src_path`) at a fixed tag (`_commit`, such as `v1.2.0`) |
| `setup-commands` | The `Makefile` has the `check`, `fix` and `verify` targets |
| `setup-workflows` | `.github/workflows/ci.yml` calls the shared `check.yml` and `security.yml` |
| `setup-agents-md` | No line of `AGENTS.md` says "do not", "never", "always" or "must", unless it ends with `<!-- judgment: why -->` |

A project copied from a local folder or an untagged commit fails `setup-template` until
`uvx copier update` from `gh:Hugo-SEQUIER/ci-workflows` records a fixed tag.

`copier update` merges the template's changes into the project's own edits; a line both changed
shows as a git conflict (`<<<<<<< before updating`), and `make check` fails until it is resolved.
The version a project has is `_commit` in its `.copier-answers.yml`.

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

A change to `template/` also gets a fixed, annotated version tag, which `copier update` reads:
`git tag -a v1.<n>.0 -m "template 1.<n>.0" && git push origin v1.<n>.0`. The moving `v1` stays a
lightweight tag. When both tags are on one commit, git names the commit by the annotated one, so a
project records `v1.<n>.0` and not `v1`; a project that recorded the moving `v1` could not be
updated, because `v1` would no longer point at the version it was made from.
