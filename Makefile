lint-check:
	ruff check --no-fix
	ruff format --check

lint:
	ruff check --fix
	ruff format

bundle:
	pyinstaller src/rml/__init__.py --name rml
	tar -czf dist/rml.tar.gz -C dist rml/

install:
	uv sync --locked

install-test:
	uv sync --locked --extra test


unit-test: lint-check
	pytest --durations=10 tests/unit/
	
