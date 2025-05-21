lint-check:
	env/bin/ruff check --no-fix
	env/bin/ruff format --check

lint:
	env/bin/ruff check --fix
	env/bin/ruff format

bundle:
	pyinstaller src/rml/__init__.py --name rml
	tar -czf dist/rml.tar.gz -C dist rml/

install:
	uv sync --locked

install-test:
	uv sync --locked --extra test


unit-test: lint-check
	pytest --durations=10 tests/unit/
	
