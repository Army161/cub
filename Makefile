UV ?= uv

.PHONY: setup run test lint fmt ci killall

setup:
	$(UV) sync --extra dev

run:
	$(UV) run cub-bot

test:
	$(UV) run pytest

lint:
	$(UV) run ruff check src tests

fmt:
	$(UV) run ruff check src tests --fix

ci: lint test

killall:
	$(UV) run cub-killall
