# Cloudflare Access policy checklist for `emfi.ics.red`

Control owns the ChipShover, ChipSHOUTER, Scaffold, and XDS110. Treat access to `https://emfi.ics.red/api/control/` as access to dangerous physical hardware.

Before enabling the tunnel:

1. Create a Cloudflare Zero Trust self-hosted application for `emfi.ics.red`.
2. Require identity for the whole hostname, not just selected paths.
3. Allow only the lab operators group or named emails that should operate the rig.
4. Require MFA or an identity provider policy with equivalent assurance.
5. Set a short session duration for operators.
6. Keep Caddy bound to `127.0.0.1` and keep app services bound to `127.0.0.1`.
7. Block direct inbound access to ports `8001`, `8002`, and `8080` at the host firewall.

Suggested policy shape:

```text
Application: EMFI lab remote access
Type: Self-hosted
Hostname: emfi.ics.red
Session duration: 4h or less

Allow policy:
  Include: lab-operators identity group
  Require: MFA

Default action:
  Deny
```

After saving the Access application, verify from a network that is not already trusted:

```bash
curl -I https://emfi.ics.red/
```

The response should redirect to Cloudflare Access login or return an Access denial. It should not return the EMFI View HTML to an anonymous request.
