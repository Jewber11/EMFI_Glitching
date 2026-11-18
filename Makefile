SHELL := /usr/bin/env bash

CONTROL_PORT ?= 8001
DEVELOP_PORT ?= 8002
GATEWAY_PORT ?= 8080

.PHONY: help test test-control test-develop check-view check-develop status logs-control logs-develop logs-gateway

help:
	@printf '%s\n' \
		'EMFI operator commands' \
		'' \
		'  make test           Run backend tests and frontend checks when deps exist' \
		'  make test-control   Run Control tests' \
		'  make test-develop   Run Develop tests' \
		'  make check-view     Run Svelte check for View' \
		'  make check-develop  Run Svelte check for Develop frontend' \
		'  make status         Show local HTTP health for expected service ports' \
		'  make logs-control   Tail Control service logs on a systemd lab host' \
		'  make logs-develop   Tail Develop service logs on a systemd lab host' \
		'  make logs-gateway   Tail Caddy gateway logs on a systemd lab host'

test: test-control test-develop check-view check-develop

test-control:
	cd control && \
	if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest; \
	else python3 -m pytest; fi

test-develop:
	cd develop && \
	if [ -x .venv/bin/python ]; then .venv/bin/python -m pytest; \
	else python3 -m pytest; fi

check-view:
	cd view && npm run check

check-develop:
	cd develop/frontend && npm run check

status:
	@for spec in control:$(CONTROL_PORT) develop:$(DEVELOP_PORT) gateway:$(GATEWAY_PORT); do \
		name="$${spec%%:*}"; port="$${spec##*:}"; \
		printf '%-8s ' "$$name"; \
		if curl -fsS "http://127.0.0.1:$$port/healthz" >/dev/null 2>&1; then \
			printf 'healthy on :%s\n' "$$port"; \
		elif curl -fsS "http://127.0.0.1:$$port/" >/dev/null 2>&1; then \
			printf 'responding on :%s\n' "$$port"; \
		else \
			printf 'not responding on :%s\n' "$$port"; \
		fi; \
	done

logs-control:
	journalctl -u emfi-control.service -f

logs-develop:
	journalctl -u emfi-develop.service -f

logs-gateway:
	journalctl -u emfi-caddy.service -f
