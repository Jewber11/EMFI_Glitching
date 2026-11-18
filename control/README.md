# Control — hardware singleton service

FastAPI service owning all physical hardware: ChipShover (XY), ChipSHOUTER (EMFI source), Ledger Donjon Scaffold (target IO + pulse gen), and the XDS110 programmer for the MSPM0L2228 target.

See [`SPEC.md`](./SPEC.md) for the full API contract and safety model.

## Setup

```bash
pip install -e ../protocol
pip install -e .

# Pre-install hardware libraries that aren't on PyPI in a way that's easy to pin:
pip install chipshover chipshouter donjon-scaffold pyserial
```

External binaries the adapters shell out to:

- **OpenOCD** (≥ 0.12) for debugger-attach mode
- **TI dslite / UniFlash CLI** for fast production flashing

## Run

```bash
uvicorn control.main:app --host 0.0.0.0 --port 8001 --reload
```

API docs at `http://lab-box:8001/docs`.

## Data paths

```
~/.config/emfi-control/config.json           # device discovery + safety params
~/.local/share/emfi-control/sessions/
  logbook-YYYYMMDD.jsonl                     # canonical, append-only
  index.sqlite                               # query mirror
```

## Tests

```bash
pytest tests/
```

Hardware-touching tests are excluded from the default run; only the pure-Python carry-forward modules (safety, workers, state, logbook) are covered. Run hardware tests manually with `pytest -m hw`.
