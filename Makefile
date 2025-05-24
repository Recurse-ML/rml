lint-check:
	ruff check --no-fix
	ruff format --check

lint:
	ruff check --fix
	ruff format

bundle:
	$(eval OUT_NAME := rml-$(shell uname -s | tr '[:upper:]' '[:lower:]')-$(shell uname -m))
	pyinstaller src/rml/__init__.py --name $(OUT_NAME) --noconfirm
	tar -czf dist/$(OUT_NAME).tar.gz -C dist rml/

install:
	uv sync --locked

install-test:
	uv sync --locked --extra test


unit-test: lint-check
	pytest --durations=10 tests/unit/
	
