# Operator workflow

This is the short runbook for a normal campaign day.

## Before touching the UI

1. Confirm the ChipSHOUTER tip has physical clearance over the target.
2. Confirm DUT and platform power wiring matches the board pinout in
   `targets/` or the checked-in target docs.
3. Confirm the emergency stop path is reachable.
4. Open View through `https://emfi.ics.red/` or the lab LAN URL.
5. Confirm Control and Develop health cards are green.

## Campaign flow

1. Build or select the firmware project in Develop.
2. Flash the DUT from View or Control.
3. Select a campaign preset or configure grid, delay, width, voltage, and
   trigger mode manually.
4. Run preflight and fix every blocking item.
5. Arm only when the rig is physically safe.
6. Start the campaign and watch the live counters, position, and heatmap.
7. Stop immediately on unexpected movement, unexpected power state, or repeated
   communication faults.

## After a campaign

1. Export interesting runs from the Runs page.
2. Add notes or tags if the campaign produced useful behavior. Tags are useful
   for later filtering in the Runs page.
3. Use the Heatmap page drill-down to inspect attempts for a selected cell and
   compare the delay/width parameter distribution before rerunning anything.
4. Leave the rig disarmed and DUT/platform power in the intended state.
5. Check the Control audit JSONL when investigating who or what triggered a
   dangerous action:

   ```bash
   ssh em-lab 'tail -n 20 ~/.local/share/emfi-control/audit/audit-$(date -u +%Y%m%d).jsonl'
   ```

## Safety reminders

- Raw `/shouter/*`, `/motion/*`, Scaffold power, target flash, and campaign
  start/stop routes are audited.
- Autonomous agents should use the preflight and campaign routes, not direct raw
  pulse or motion routes.
- A public route to Control must stay behind Cloudflare Access plus app bearer
  tokens before unattended automation is enabled.
