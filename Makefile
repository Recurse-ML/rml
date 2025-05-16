BUILD_DIR=./build
EXEC_NAME=rml

install:
	pip install -e .

install-test: install
	pip install -e .[test]


lint-check:
	ruff check --no-fix
	ruff format --check

lint:
	ruff check --fix
	ruff format
build:
	mkdir -p $(BUILD_DIR)
	pyinstaller src/rml/__init__.py --workpath $(BUILD_DIR) --name $(EXEC_NAME)

bundle: build
	tar -czf dist/rml.tar.gz -C dist rml/

clean:
	rm -rf $(BUILD_DIR)
	rm -rf dist/
