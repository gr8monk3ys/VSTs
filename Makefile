.PHONY: check

# Everything CI gates on: manifest schema, ruff lint/format, syntax, CLI smoke, pytest.
check:
	uv run python scripts/verify.py
