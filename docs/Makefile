ROOT := $(abspath $(dir $(lastword $(MAKEFILE_LIST)))/..)
# Use module invocation by default; you can override with SPHINX="sphinx-build".
SPHINX ?= python -m sphinx

.PHONY: html
html:
	$(SPHINX) -b html $(ROOT)/docs $(ROOT)/docs/_build/html
