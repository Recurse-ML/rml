bundle:
	pyinstaller src/rml/__init__.py --name rml
	tar -czf dist/rml.tar.gz -C dist rml/
