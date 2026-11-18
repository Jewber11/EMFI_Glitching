# View — unified dashboard

Pure SvelteKit static app. Talks to Control (port 8001) and Develop (port 8002) over HTTP + WebSocket. No backend of its own.

See [`SPEC.md`](./SPEC.md) for pages, components, and stores.

## Setup

```bash
npm install
```

## Run

```bash
# Dev with hot reload (proxies to Control/Develop on 8001/8002)
npm run dev -- --port 8003

# Production build (static; serve with any HTTP server)
npm run build
npm run preview -- --port 8003
```

## Endpoints it consumes

- Control: `http://lab-box:8001/` + `ws://lab-box:8001/ws`
- Develop: `http://lab-box:8002/` + `ws://lab-box:8002/ws`

URLs are configurable via `src/lib/config.ts`.

## Type-safe API clients

Generated from `protocol/openapi/{control,develop}.yaml` via `openapi-typescript`:

```bash
npx openapi-typescript ../protocol/openapi/control.yaml -o src/lib/api/control.types.ts
npx openapi-typescript ../protocol/openapi/develop.yaml -o src/lib/api/develop.types.ts
```

Run after either of the Python apps changes its OpenAPI schema.
