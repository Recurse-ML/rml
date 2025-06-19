UV_VERSION=0.6.16

lint-check:
	ruff check --no-fix
	ruff format --check

lint:
	ruff check --fix
	ruff format

bundle:
	bash -c '\
	  detect_arch() { \
	    arch=$$(uname -m | tr "[:upper:]" "[:lower:]"); \
	    if [ "$$arch" = "aarch64" ] || [ "$$arch" = "arm64" ]; then \
	      echo arm64; \
	    elif [ "$$arch" = "x86_64" ] || [ "$$arch" = "amd64" ]; then \
	      echo amd64; \
	    fi; \
	  }; \
	  ARCH=$$(detect_arch); \
	  OS=$$(uname -s | tr "[:upper:]" "[:lower:]"); \
	  TAR_NAME=rml-$$OS-$$ARCH.tar.gz; \
	  pyinstaller src/rml/__init__.py --name rml --noconfirm; \
	  tar -czf dist/$$TAR_NAME -C dist rml/;'

install:
	uv sync --locked

install-uv:
	curl --proto '=https' --tlsv1.2 -LsSf https://github.com/astral-sh/uv/releases/download/$(UV_VERSION)/uv-installer.sh | sh

install-test:
	uv sync --locked --extra test

install-dev:
	uv sync --locked --extra test --extra dev
	pre-commit install
	pre-commit autoupdate

unit-test: lint-check
	pytest --durations=10 tests/unit/

test: unit-test

bump-version:
	@if [ -z "$(version)" ]; then \
		echo "Error: version argument is required. Usage: make bump-version version=X.Y.Z"; \
		exit 1; \
	fi
	uv version $(version) && uv sync