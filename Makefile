lint-check:
	ruff check --no-fix
	ruff format --check

lint:
	ruff check --fix
	ruff format

bundle:
	$(eval ARCH := $(shell uname -m | sed 's/aarch64/arm64/;s/x86_64/amd64/'))
	$(eval TAR_NAME := rml-$(shell uname -s | tr '[:upper:]' '[:lower:]')-$(ARCH).tar.gz)
	pyinstaller src/rml/__init__.py --name rml --noconfirm
	tar -czf dist/$(TAR_NAME) -C dist rml/

install:
	uv sync --locked

install-test:
	uv sync --locked --extra test


unit-test: lint-check
	pytest --durations=10 tests/unit/
	
