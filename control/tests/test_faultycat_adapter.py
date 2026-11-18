"""Vendor simulator checks for FaultyCat adapter."""
import pytest
import faultycat
from faultycmd.protocols.emfi import EmfiState
from control.adapters.faultycat import FaultyCatAdapter


def test_simulated_pulse_and_disarm():
    adapter = FaultyCatAdapter()
    adapter._impl = faultycat.connect(simulator=True, scanner=False, uart=False)
    adapter._impl.emfi.trigger = 'immediate'
    try:
        adapter.set_pulse_width(5000)
        adapter.arm()
        adapter.pulse()
        assert adapter._impl.emfi.status.state == EmfiState.FIRED
        adapter.disarm()
        with pytest.raises(RuntimeError, match='disarmed'):
            adapter.pulse()
    finally:
        adapter.disconnect()


@pytest.mark.parametrize('width', [80, 1500, 51000])
def test_rejects_unsupported_width(width):
    with pytest.raises(ValueError):
        FaultyCatAdapter().set_pulse_width(width)
