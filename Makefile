export PYTHONPATH := packages
PY ?= /home/azuramaru/.hermes/tools/python-3.14.7+20260901-linux-x64/bin/python3

.PHONY: test hygiene init area-payload

test:
	PYTHONPATH=packages $(PY) tests/test_auto_cb.py

hygiene:
	$(PY) scripts/public-hygiene-gate.py --repo-root .

init:
	PYTHONPATH=packages $(PY) -m auto_cb.cli init

area-payload:
	PYTHONPATH=packages $(PY) -m auto_cb.cli area-payload --country $${CC:-sg}
