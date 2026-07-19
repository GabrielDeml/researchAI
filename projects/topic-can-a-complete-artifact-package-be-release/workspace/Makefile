.PHONY: reproduce

VENV_PYTHON := $(shell command -v python3.12 2>/dev/null || command -v python3)

.venv/bin/python:
	$(VENV_PYTHON) -m venv .venv

reproduce: .venv/bin/python requirements.lock
	.venv/bin/pip install --disable-pip-version-check -r requirements.lock
	MPLBACKEND=Agg .venv/bin/python -m src.run_experiment --output results
