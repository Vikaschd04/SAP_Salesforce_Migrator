.PHONY: install ping ingest run report demo test clean

PYTHON ?= .venv/bin/python

setup:
	python3 -m venv .venv
	.venv/bin/pip install -r requirements.txt

install: setup

ping:
	$(PYTHON) -m src.main ping

ingest:
	$(PYTHON) -m src.main ingest --input demo_hybris

run:
	$(PYTHON) -m src.main run --input demo_hybris --output demo_output

report:
	$(PYTHON) -m src.main report --output demo_output

demo:
	$(PYTHON) -m src.main run --input demo_hybris --output demo_output
	$(PYTHON) -m src.main report --output demo_output

demo-offline:
	$(PYTHON) -m src.main run --input demo_hybris --output demo_output --offline
	$(PYTHON) -m src.main report --output demo_output

test:
	$(PYTHON) -m pytest tests/ -q

clean:
	rm -rf demo_output/* cache/* __pycache__ src/__pycache__ tests/__pycache__
