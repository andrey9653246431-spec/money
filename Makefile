.PHONY: install check test build avatar

install:
	python -m pip install -e ".[dev]"

check:
	ruff check .
	ruff format --check .
	pytest
	dbp-design validate --input examples/posts.json

test:
	pytest

build:
	dbp-design build --input examples/posts.json --out dist

avatar:
	dbp-design avatar --out dist/avatar.png
