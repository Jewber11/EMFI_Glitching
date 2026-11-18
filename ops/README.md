# Remote hosting ops examples

This directory contains copy-and-edit examples for exposing the EMFI lab box through a single public hostname:

- `systemd/` - Control/Develop app services and the local Caddy service.
- `caddy/Caddyfile` - local reverse proxy and static View server for `emfi.ics.red`.
- `cloudflare/config.yml` - Cloudflare Tunnel ingress to Caddy.
- `cloudflare/access-policy.md` - Cloudflare Access checklist for the public app.

These files are examples, not drop-in secrets. Replace usernames, paths, tunnel IDs, and policy groups before installing them on a lab machine.

## Security rule

Control owns dangerous hardware. Any public route that can reach Control must be protected by Cloudflare Access or equivalent authentication and authorization. Do not expose ports `8001`, `8002`, or the local Caddy listener directly to the internet.
