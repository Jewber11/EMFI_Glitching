"""Host-side experiment driver for this project.

Imported by Control's orchestrator when a campaign references this
project. Implements the three lifecycle hooks below. `ctx` exposes:
  ctx.scaffold   — adapters.scaffold.ScaffoldAdapter
  ctx.shouter    — adapters.chipshouter.ChipShouterAdapter
  ctx.params     — current SweepParams snapshot (dict or namespace)
  ctx.logbook    — control.logbook.Logbook
  ctx.state      — control.state.AppState (read-only references)

Uses ScaffoldAdapter's generic pin methods (set_d_output, set_d_input,
write_d) for I/O setup + the trigger, and the EDGE-EVENT reads
(clear_d_event, read_d_event) for the verdict. Edge events latch a
transition that happened any time during the verdict window, so the
verdict reflects what the target actually did — not just the
instantaneous pin level at the moment we happen to read it.

Pin map (target firmware side):
  D0 = USER_TEST (PA21)       — trigger: rising edge = test loop start
  D1 = USER_HEARTBEAT (PB14)  — edge: toggled = heartbeat alive
  D2 = USER_LED_2 (PB10)      — edge: rising = fault detected
  D3 = USER_LED_3 (PB9)       — edge: falling = campaign complete
"""


def setup(ctx) -> None:
    """Called once before the campaign starts. Configure DUT power,
    trigger mode, etc."""
    sc = ctx.scaffold
    sc.set_d_output(0)   # D0 = USER_TEST trigger
    sc.set_d_input(1)    # D1 = USER_HEARTBEAT
    sc.set_d_input(2)    # D2 = USER_LED_2 (fault, rising edge)
    sc.set_d_input(3)    # D3 = USER_LED_3 (campaign_complete,
                         #                  falling edge)


def attempt(ctx) -> dict:
    """Called once per glitch attempt. Returns
        {"fault": bool, "heartbeat_alive": bool,
         "campaign_complete": bool}
    Reuses the Verdict shape from emfi_protocol.runs."""
    sc = ctx.scaffold
    # Clear edge latches BEFORE the trigger fires.
    sc.clear_d_event(1)
    sc.clear_d_event(2)
    sc.clear_d_event(3)

    # In hardware-trigger modes, the pulse fires autonomously on
    # the D0 rising edge; we just signal the target to start.
    # In software trigger mode, the orchestrator fires the pulse
    # after this attempt() returns. Either way, pulse D0 high to
    # tell the target "start the test loop now".
    sc.write_d(0, 1)
    sc.write_d(0, 0)

    # Wait the verdict window for the target to respond.
    import time
    delay_us = ctx.params.get("delay_us") if hasattr(ctx.params, "get") else getattr(ctx.params, "delay_us", None)
    timeout_s = float(ctx.params.get("verdict_timeout_s", 0.5)) if hasattr(ctx.params, "get") else 0.5
    time.sleep(max(timeout_s, (delay_us or 1) / 1_000_000))

    # Read EDGE EVENTS, not instantaneous pin state.
    # D2 rising = fault detected; D3 falling = campaign end.
    return {
        "fault": sc.read_d_event(2),
        "heartbeat_alive": sc.read_d_event(1),
        "campaign_complete": sc.read_d_event(3),
    }


def teardown(ctx) -> None:
    """Called once after the campaign ends. Power-down DUT, restore
    safe state."""
    ctx.scaffold.write_d(0, 0)
