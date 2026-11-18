"""FaultyCat v3 EMFI adapter using the vendor host protocol."""
import time
from control.adapters.base import BaseAdapter


class FaultyCatAdapter(BaseAdapter):
    name = 'faultycat'

    def __init__(self):
        self._impl = None
        self._port = None
        self._last_error = None
        self.last_fault = None
        self._width_us = 1
        self._armed = False

    def connect(self, port=None):
        if self.connected:
            raise RuntimeError('FaultyCat already connected')
        import faultycat
        cat = faultycat.connect(emfi_port=port, scanner=False, uart=False)
        if cat.emfi is None:
            cat.close()
            raise RuntimeError('FaultyCat EMFI interface not found')
        try:
            cat.emfi.trigger = 'immediate'
            cat.emfi.disarm()
        except Exception:
            cat.close()
            raise
        self._impl = cat
        self._port = port or getattr(cat.emfi._c, 'port', None)

    @property
    def connected(self):
        return self._impl is not None

    def _require_connected(self):
        if not self.connected:
            raise RuntimeError('FaultyCat is not connected')

    def disconnect(self):
        if self.connected:
            try:
                self.disarm_safe()
            finally:
                self._impl.close()
                self._impl = None
                self._port = None

    def set_pulse_width(self, pulse_width_ns):
        width = float(pulse_width_ns) / 1000
        if not width.is_integer() or not 1 <= width <= 50:
            raise ValueError('FaultyCat width must be a whole number of microseconds from 1 to 50')
        self._width_us = int(width)
        return self._width_us * 1000

    def configure(self, voltage, pulse_width_ns, pulse_repeat=1, pulse_deadtime_ms=10, arm_timeout_min=1, mute=True):
        self._require_connected()
        if pulse_repeat != 1:
            raise ValueError('FaultyCat adapter supports one pulse per attempt')
        self.set_pulse_width(pulse_width_ns)

    def configure_hardware_trigger(self, **kwargs):
        raise NotImplementedError('FaultyCat external trigger campaigns are not implemented')

    def arm(self, clear_faults=False, timeout_s=5):
        self._require_connected()
        self._armed = True

    def disarm(self):
        self._require_connected()
        self._armed = False
        self._impl.emfi.disarm()

    def disarm_safe(self):
        self._armed = False
        if self.connected:
            try:
                self._impl.emfi.disarm()
            except Exception:
                pass

    def pulse(self):
        self._require_connected()
        if not self._armed:
            raise RuntimeError('FaultyCat is disarmed')
        from faultycmd.protocols.emfi import EmfiState
        engine = self._impl.emfi
        engine.width_us = self._width_us
        try:
            engine.arm()
            self._wait(EmfiState.CHARGED)
            engine.fire()
            self._wait(EmfiState.FIRED)
        except Exception:
            self.disarm_safe()
            raise

    def _wait(self, expected):
        from faultycmd.protocols.emfi import EmfiState
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            status = self._impl.emfi.status
            if status.state == expected:
                return
            if status.state == EmfiState.ERROR:
                raise RuntimeError(f'FaultyCat error: {status.err.name}')
            time.sleep(0.01)
        raise TimeoutError(f'FaultyCat timeout waiting for {expected.name}')

    def get_state(self):
        self._require_connected()
        return 'armed' if self._armed else 'disarmed'

    def get_fault_active(self):
        self._require_connected()
        from faultycmd.protocols.emfi import EmfiState, EmfiErr
        status = self._impl.emfi.status
        if status.state == EmfiState.ERROR or status.err != EmfiErr.NONE:
            return [status.err.name]
        return []

    def get_faults(self):
        return {'last_fault': self.last_fault, 'current': self.get_fault_active() if self.connected else [], 'connected': self.connected}

    def status(self):
        return {**super().status(), 'armed': self._armed, 'state': self.get_state() if self.connected else None, 'faults': [], 'last_fault': self.last_fault}
