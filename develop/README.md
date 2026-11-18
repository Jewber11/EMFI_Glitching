# Develop — firmware projects + builds + agent

FastAPI service that manages firmware projects on disk, builds them, parses the resulting assembly, and exposes a Claude Code agent for AI-assisted firmware authoring. Bundles its own SvelteKit UI so it's usable standalone.

See [`SPEC.md`](./SPEC.md) for the full API contract and project model.

## Setup

```bash
pip install -e ../protocol
pip install -e .

# Backend deps
pip install pyelftools capstone

# Frontend deps
cd frontend && npm install
```

## Toolchain dependencies (install on the lab box)

```bash
# C / TI ecosystem
sudo apt install gcc-arm-none-eabi binutils-arm-none-eabi gdb-multiarch make

# Rust / b01lers eCTF HAL
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
rustup target add thumbv8m.main-none-eabi

# Agent (Claude Code CLI)
# Install via npm: npm i -g @anthropic-ai/claude-code (or per upstream instructions)

# Git (for project versioning)
sudo apt install git
```

## Run

```bash
# Dev: hot-reload frontend
cd frontend && npm run dev    # http://localhost:5173

# Backend (always-on)
uvicorn develop.main:app --host 0.0.0.0 --port 8002 --reload
```

In production, the frontend is built (`npm run build`) and served via FastAPI StaticFiles at `http://lab-box:8002/`.

## Data

Projects live under `~/emfi-projects/<project-id>/`. Each is a git repo. See [`SPEC.md`](./SPEC.md) for the on-disk layout.
