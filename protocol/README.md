# `emfi-protocol` — shared API contracts

Pydantic v2 models that are the **single source of truth** for the Control ↔ Develop ↔ View wire format.

## Layout

```
emfi_protocol/
  campaigns.py    Campaign, SweepParams, GridParams
  runs.py         AttemptResult, Verdict, Outcome (enum)
  devices.py      DeviceStatus, Position, ArmState
  projects.py     Project, BuildArtifact, AssemblyListing, GlitchTarget
  ws_events.py    WS event envelope + topic constants
openapi/
  control.yaml    generated from control.main:app.openapi()
  develop.yaml    generated from develop.main:app.openapi()
```

## Install (editable)

```bash
pip install -e .
```

Then in Control or Develop:

```python
from emfi_protocol.campaigns import Campaign
from emfi_protocol.runs import AttemptResult, Outcome
```

## Regenerating OpenAPI specs

Run each app once and dump its OpenAPI schema:

```bash
python -c "from control.main import app; import yaml,sys; yaml.safe_dump(app.openapi(), sys.stdout)" \
  > protocol/openapi/control.yaml
python -c "from develop.main import app; import yaml,sys; yaml.safe_dump(app.openapi(), sys.stdout)" \
  > protocol/openapi/develop.yaml
```

The SvelteKit apps then run `openapi-typescript` against these YAMLs to generate type-safe API clients.
