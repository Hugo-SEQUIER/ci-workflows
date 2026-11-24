# Parameters: none. Run from the repository root.
# What it does: the check, fix and verify commands (AGENTS.md#commands).
# Output: exit code 0 when every step passes.

.PHONY: check fix verify

check:
	uv run --no-project scripts/check.py $(CHECK_ARGS)

fix:
	uv run --no-project scripts/check.py --fix

verify: check
	mkdir -p proof
	cp check-report.json proof/check-report.json
