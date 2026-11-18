# EMFI wiki

This directory is the lightweight project wiki. Keep pages short, operational,
and linked from this index so a new operator can find the right runbook without
reading the whole repo.

## Start here

| Page | Use it for |
|---|---|
| [`../../setup.md`](../../setup.md) | Moving development to a new laptop |
| [`../../INSTALL.md`](../../INSTALL.md) | Building a fresh lab host that owns USB hardware |
| [`../../DOCS.md`](../../DOCS.md) | Running campaigns and troubleshooting the rig |
| [`../remote-access.md`](../remote-access.md) | Cloudflare Tunnel, Caddy, and public hostname layout |
| [`../automation.md`](../automation.md) | Scoped API access for scripts and AI agents |
| [`operator-workflow.md`](./operator-workflow.md) | Day-to-day campaign workflow |
| [`developer-workflow.md`](./developer-workflow.md) | Code, test, push, pull, and deploy loop |
| [`dual-target-campaigns.md`](./dual-target-campaigns.md) | DUT EMFI plus Platform voltage-glitch campaign model |
| [`purple-board-pinout.md`](./purple-board-pinout.md) | Current purple board pinout, Scaffold wiring, and bench-verification gaps |

## Wiki conventions

- Update the relevant page in the same commit as code or ops changes.
- Prefer commands that are copy-pasteable from the lab user's shell.
- Keep secrets out of examples. Use environment variable names instead.
- Link back to source-of-truth docs instead of duplicating long sections.
- Record hardware-specific observations with exact dates when they may change.

## Open wiki pages to add

- ChipWhisperer Husky setup and crowbar wiring. The Control/API scaffold is
  documented in [`dual-target-campaigns.md`](./dual-target-campaigns.md), but
  real hardware setup still needs its own runbook.
- XDS110 flash/debug troubleshooting.
- Campaign analysis recipes.
