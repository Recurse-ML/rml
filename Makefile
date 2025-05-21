lint-check:
	ruff check --no-fix
	ruff format --check

lint:
	ruff check --fix
	ruff format

bundle:
	pyinstaller src/rml/__init__.py --name rml
	tar -czf dist/rml.tar.gz -C dist rml/
