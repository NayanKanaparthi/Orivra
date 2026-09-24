# MailWeave developer commands. CI runs exactly these.
.PHONY: install lint format format-check types test guards gate acceptance acceptance-plan check

install:
	uv sync --all-packages --extra dev

lint:
	uv run ruff check .

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

types:
	uv run mypy

test:
	uv run pytest -q -m "not network"

guards:
	uv run python -m tools.guards

gate:
	uv run python tools/rubric_status.py --check

# M2's acceptance evidence. `acceptance-plan` needs nothing and prints what each of M2's
# four lines claims, what runs here and what each blocked half is waiting for;
# `acceptance` runs the runnable half and reports per item. Neither is a verdict: only a
# reviewer who did not write the code may move a rubric criterion (see `gate`).
acceptance-plan:
	uv run python -m mailweave_harness.acceptance --plan

acceptance:
	uv run python -m mailweave_harness.acceptance --run

# CI runs `ruff format --check` as its own step; folding it in here means the one
# command reviewers are told to run sees the same drift CI does (R-ARCH-007).
check: lint format-check types test guards gate
	@uv run python -m mailweave_harness.acceptance --check
	@echo "all local gates passed"
