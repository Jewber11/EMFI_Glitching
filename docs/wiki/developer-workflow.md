# Developer workflow

The repo is the sync mechanism between the laptop and the lab host.

## Local loop

```bash
git status --short
cd control && PYTHONPATH=src:../protocol ../.venv/bin/python -m pytest
cd ../develop && PYTHONPATH=src:../protocol ../.venv/bin/python -m pytest
cd ../view && npm run check && npm run build
```

Run focused tests while iterating, then broaden before pushing when the touched
area crosses app boundaries.

## Push and pull to the lab

```bash
git push
ssh em-lab 'cd ~/EM-Architecture && git pull --ff-only'
```

Control and Develop are currently run with `uvicorn --reload` on the lab, so
Python code reloads after a pull. View must be rebuilt and copied:

```bash
ssh em-lab 'cd ~/EM-Architecture/view && npm install && npm run build && rm -rf /var/www/emfi-view/* && cp -a build/. /var/www/emfi-view/'
```

## Remote checks

```bash
ssh em-lab 'curl -fsS http://127.0.0.1:8001/healthz'
ssh em-lab 'curl -fsS http://127.0.0.1:8002/healthz'
ssh em-lab 'systemctl status caddy --no-pager'
ssh em-lab 'systemctl status cloudflared --no-pager'
```

Use Caddy and cloudflared as systemd services. Keep the app services localhost
or LAN-bound according to [`../remote-access.md`](../remote-access.md).

## Documentation rule

When code changes behavior, update one of:

- [`../../ROADMAP.md`](../../ROADMAP.md) for feature completion status.
- [`../../DOCS.md`](../../DOCS.md) for operator-facing behavior.
- [`../../setup.md`](../../setup.md) for laptop/lab migration steps.
- This wiki for repeated workflows.
