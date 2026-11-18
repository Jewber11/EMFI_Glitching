# Remote access for `emfi.ics.red`

The EMFI platform was designed for a trusted LAN. Remote access is acceptable only when the public hostname is protected by Cloudflare Access or an equivalent auth layer.

> **Safety warning:** Control owns dangerous hardware: the ChipShover motion stage, ChipSHOUTER EMFI source, Scaffold target IO, and XDS110 programmer. Any route to Control must sit behind Cloudflare Access/auth. Do not expose Control anonymously.

## Target shape

Use one public hostname:

```text
https://emfi.ics.red/              -> View dashboard
https://emfi.ics.red/develop/      -> Develop UI
https://emfi.ics.red/api/control/  -> Control API and WebSocket, proxied to 127.0.0.1:8001
https://emfi.ics.red/api/develop/  -> Develop API and WebSocket, proxied to 127.0.0.1:8002
```

On the lab box:

```text
emfi-control.service -> 127.0.0.1:8001
emfi-develop.service -> 127.0.0.1:8002
Caddy                -> 127.0.0.1:8080 and serves static View from /var/www/emfi-view
cloudflared          -> outbound tunnel from Cloudflare to 127.0.0.1:8080
```

No EMFI app port should listen on `0.0.0.0` for the remote-hosting setup.

## Build View for the public host

View defaults to the same-origin paths `/api/control` and `/api/develop`, so a
normal production build is enough for `emfi.ics.red`:

```bash
cd /home/lab/EM-Architecture/view
npm install
npm run build
sudo mkdir -p /var/www/emfi-view
sudo rsync -a --delete build/ /var/www/emfi-view/
sudo chown -R caddy:caddy /var/www/emfi-view
```

For LAN-only development against direct service ports, override
`VITE_CONTROL_URL` and `VITE_DEVELOP_URL` at build/dev time.

## systemd

Copy and edit the example units:

```bash
sudo cp ops/systemd/emfi-control.service.example /etc/systemd/system/emfi-control.service
sudo cp ops/systemd/emfi-develop.service.example /etc/systemd/system/emfi-develop.service
sudo cp ops/systemd/emfi-caddy.service.example /etc/systemd/system/emfi-caddy.service
```

Edit the copied files for the real user, repo path, Python virtualenv path, and data paths. Then start them:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now emfi-control emfi-develop emfi-caddy
sudo systemctl status emfi-control emfi-develop emfi-caddy
```

The app services bind to `127.0.0.1` by default in these examples. That is intentional.

## Caddy

Install Caddy and copy the example config:

```bash
sudo cp ops/caddy/Caddyfile /etc/caddy/emfi.Caddyfile
sudo systemctl enable --now emfi-caddy
curl -I http://127.0.0.1:8080/
curl -I http://127.0.0.1:8080/api/control/docs
```

Caddy is used here as a local path router. It does not terminate public TLS; Cloudflare handles public TLS and forwards through the tunnel. Caddy supports WebSocket proxying, so `/api/control/ws` and `/api/develop/ws` pass through the same route as HTTP.

## Cloudflare Tunnel

Create and route the tunnel:

```bash
cloudflared tunnel login
cloudflared tunnel create emfi-remote
cloudflared tunnel route dns emfi-remote emfi.ics.red
```

Copy and edit the example config:

```bash
sudo mkdir -p /etc/cloudflared
sudo cp ops/cloudflare/config.yml /etc/cloudflared/config.yml
sudo install -m 0600 ~/.cloudflared/<tunnel-uuid>.json /etc/cloudflared/<tunnel-uuid>.json
sudo cloudflared tunnel ingress validate --config /etc/cloudflared/config.yml
sudo cloudflared tunnel ingress rule https://emfi.ics.red/api/control/docs --config /etc/cloudflared/config.yml
```

Install and start the service:

```bash
sudo cloudflared service install
sudo systemctl enable --now cloudflared
sudo journalctl -u cloudflared -f
```

The example tunnel exposes only `emfi.ics.red` and returns `404` for all other ingress.

## Cloudflare Access

Before leaving the tunnel running, create a Cloudflare Zero Trust Access application for `emfi.ics.red`. Use `ops/cloudflare/access-policy.md` as the policy checklist.

Minimum human policy:

```text
Include: lab operator identity group or named operator emails
Require: MFA
Default: deny
```

Minimum automation policy:

```text
Include: one Cloudflare Access service token per automation client
Default: deny
```

Protect the whole hostname. Do not protect only `/api/control`; the View UI can issue Control commands if it is configured to talk to `/api/control`.

For automation clients, Cloudflare Access is only the outer gate. The EMFI
application bearer token is still required when bearer-token middleware is
enabled in Control and Develop. Configure those tokens with `EMFI_AUTH_TOKENS`;
see `docs/automation.md` for the JSON shape and recommended scopes.

Example service-token request:

```bash
export EMFI_ORIGIN="https://emfi.ics.red"
export CF_ACCESS_CLIENT_ID="service-token-client-id.access"
export CF_ACCESS_CLIENT_SECRET="service-token-client-secret"
export EMFI_AUTOMATION_TOKEN="replace-with-long-random-token"

curl -fsS "$EMFI_ORIGIN/api/control/readyz" \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  -H "Authorization: Bearer $EMFI_AUTOMATION_TOKEN"
```

If the Cloudflare Access service token is invalid, the request should fail at
Cloudflare before it reaches Caddy. If the Access token is valid but the EMFI
bearer token is missing or lacks scope, Control or Develop should return
`401` or `403`.

Store the JSON token config in a root-readable environment file instead of in
the repo:

```bash
sudo install -m 0600 -o root -g root /dev/null /etc/emfi-auth.env
sudoedit /etc/emfi-auth.env
```

Example `/etc/emfi-auth.env`:

```bash
EMFI_AUTH_TOKENS='{"replace-with-long-random-token":{"name":"campaign-agent","scopes":["control:read","target:flash","campaign:preflight","campaign:start","campaign:stop","develop:read","develop:build"]}}'
```

Then add this to both local systemd units for the remote deployment:

```text
EnvironmentFile=/etc/emfi-auth.env
```

## Firewall

Allow outbound HTTPS for `cloudflared`. Block inbound public traffic to local app ports:

```bash
sudo ufw deny 8001/tcp
sudo ufw deny 8002/tcp
sudo ufw deny 8080/tcp
```

If you also need trusted LAN access, add explicit LAN-only allows for the ports you intend to use. Do not add broad `allow` rules for these services.

## Verification

From the lab box:

```bash
curl -I http://127.0.0.1:8001/docs
curl -I http://127.0.0.1:8002/docs
curl -I http://127.0.0.1:8080/
curl -I http://127.0.0.1:8080/api/control/docs
```

From outside the lab network:

```bash
curl -I https://emfi.ics.red/
```

Expected result before login: Cloudflare Access login or denial, not the EMFI application.

After authenticating through Cloudflare Access:

```text
https://emfi.ics.red/ loads View
https://emfi.ics.red/develop/ loads Develop UI
https://emfi.ics.red/api/control/docs loads Control docs
https://emfi.ics.red/api/develop/docs loads Develop API docs
```

The Develop Svelte frontend is built with `DEVELOP_BASE_PATH=/develop` for the
public single-host setup. Keep `/api/develop` for programmatic API access and
OpenAPI docs.

Keep `emfi-control` stopped when the rig is unattended or in an unsafe physical state.
