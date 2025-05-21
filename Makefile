lint-check:
	.venv/bin/ruff check --no-fix
	.venv/bin/ruff format --check

lint:
	# TODO: change CI to use env/bin
	.venv/bin/ruff check --fix
	.venv/bin/ruff format

bundle:
	pyinstaller src/rml/__init__.py --name rml
	tar -czf dist/rml.tar.gz -C dist rml/

install:
	uv sync --locked

install-test:
	uv sync --locked --extra test


unit-test: lint-check
	pytest --durations=10 tests/unit/
	
