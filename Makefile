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

install-test:
	uv sync --locked --extra test


unit-test: lint-check
	pytest --durations=10 tests/unit/
	
bump-version:
	uv version $(version) && uv sync
