# verifyface — Developer: Kaustav Kanti Ray
.PHONY: help install test cov lint fmt build check clean demo serve publish-test publish

help:
	@echo "verifyface — Developer: Kaustav Kanti Ray"
	@echo ""
	@echo "  make install       install in editable mode with dev extras"
	@echo "  make test          run the test suite"
	@echo "  make cov           tests with coverage"
	@echo "  make lint          ruff + mypy"
	@echo "  make build         build sdist and wheel into dist/"
	@echo "  make check         validate the built distributions"
	@echo "  make serve         start the browser app on :8000"
	@echo "  make demo          live camera demo"
	@echo "  make clean         remove build artefacts"

install:
	pip install -e ".[dev]"

test:
	pytest -q

cov:
	pytest -q --cov=verifyface --cov-report=term-missing

lint:
	ruff check src tests examples
	mypy src || true

fmt:
	ruff format src tests examples

build: clean
	python -m build

check:
	python -m twine check dist/*

serve:
	python -m verifyface serve --port 8000

demo:
	python -m verifyface demo

publish-test: build check
	python -m twine upload --repository testpypi dist/*

publish: build check
	python -m twine upload dist/*

clean:
	rm -rf build dist *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
