# UK Net Worth Benchmarker — common dev tasks
#
# Usage:
#   make install     install dependencies (pip install -r requirements.txt)
#   make test        run the full pytest suite
#   make test-quick  pytest with quiet output (line-format failures only)
#   make compile     py_compile sanity check on every source file
#   make run         start the Streamlit app on http://localhost:8501
#   make check       compile + test (what CI runs)
#   make data        refresh was_data.csv + was_asset_class.csv from scripts
#   make help        show this list
#
# Cross-platform note: most targets use python directly (not shell-specific
# commands) so they work on Windows, macOS, and Linux. The 'run' target uses
# the streamlit CLI which behaves identically on all platforms.

PYTHON ?= python

.DEFAULT_GOAL := help

.PHONY: help install test test-quick compile run check data clean

help:
	@echo "UK Net Worth Benchmarker - common dev tasks"
	@echo ""
	@echo "  make install     install dependencies"
	@echo "  make test        run the full pytest suite"
	@echo "  make test-quick  pytest with terse output"
	@echo "  make compile     py_compile sanity check on every source file"
	@echo "  make run         start the Streamlit app on http://localhost:8501"
	@echo "  make check       compile + test (matches CI)"
	@echo "  make data        refresh was_data.csv + was_asset_class.csv"
	@echo "  make clean       remove __pycache__ and .pytest_cache"

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest tests/ -v

test-quick:
	$(PYTHON) -m pytest tests/ -q --tb=line

compile:
	$(PYTHON) -m py_compile app.py
	$(PYTHON) -m py_compile utils/inference.py
	$(PYTHON) -m py_compile utils/data_loader.py
	$(PYTHON) -m py_compile utils/monte_carlo.py
	$(PYTHON) -m py_compile utils/uk_tax.py
	$(PYTHON) -m py_compile charts/__init__.py
	@echo "All source files compile cleanly."

run:
	$(PYTHON) -m streamlit run app.py

check: compile test-quick
	@echo "All checks passed."

data:
	$(PYTHON) scripts/update_was_data.py
	$(PYTHON) scripts/update_asset_class_data.py
	@echo ""
	@echo "Data refreshed. Run 'make test' to verify nothing broke."

clean:
	$(PYTHON) -c "import shutil, pathlib; \
		[shutil.rmtree(p, ignore_errors=True) for p in pathlib.Path('.').rglob('__pycache__')]; \
		shutil.rmtree('.pytest_cache', ignore_errors=True); \
		print('Cleaned __pycache__ and .pytest_cache')"
