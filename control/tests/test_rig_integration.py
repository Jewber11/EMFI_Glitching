"""Campaign integration with a simulated FaultyCat and Marlin stage."""
import asyncio
from types import SimpleNamespace

import faultycat

from control.adapters.faultycat import FaultyCatAdapter
from control.logbook import Logbook
from control.orchestrator import Orchestrator, _grid_points
from control.routers.campaigns import _preflight
from control.safety import ArmGate, RateLimiter, StopFlag
from control.state import AppState, DeviceStatus
from control.workers import WorkerRegistry
from emfi_protocol.campaigns import Campaign


class Stage:
    connected = True
    position = (0, 0, 0)

    def move_absolute_logical(self, x, y, z):
        self.position = (x, y, z)

    def get_position(self):
        return self.position

    def machine_to_logical(self, *xyz):
        return xyz


class Config:
    def get(self, *args, default=None):
        return default


def campaign():
    return Campaign(name='test', project_id='_standalone', grid={
        'origin': [0, 0], 'top_right': [1, 0], 'step_size_mm': 1,
        'z_min_mm': 0, 'z_max_mm': 0, 'z_step_mm': 1,
    }, sweep={'attempts_per_point': 1}, shouter_pulse_width_ns=5000)


def test_preflight_without_scaffold():
    state = AppState(origin_set=True, devices={
        name: DeviceStatus(name=name, connected=True)
        for name in ('chipshover', 'chipshouter')
    })
    ctx = SimpleNamespace(state=state, config=Config(), campaigns={}, flashed_firmware=None)
    check = _preflight(campaign(), ctx)
    assert check.ok, check.blockers
    assert check.total_attempts == 2
    assert any('unobserved' in warning for warning in check.warnings)


def test_grid_never_overshoots_corner():
    points = list(_grid_points({'origin': [0, 0], 'top_right': [1.8, 0],
        'step_size_mm': 1, 'z_min_mm': 0, 'z_max_mm': 0.8, 'z_step_mm': 1}))
    assert [p[:3] for p in points] == [(0, 0, 0), (1, 0, 0)]


def test_complete_campaign_with_vendor_simulator(tmp_path):
    async def run():
        cat = FaultyCatAdapter()
        cat._impl = faultycat.connect(simulator=True, scanner=False, uart=False)
        cat._impl.emfi.trigger = 'immediate'
        state = AppState()
        gate = ArmGate()
        gate.arm()
        workers = WorkerRegistry()
        events = []
        engine = Orchestrator(state, gate, StopFlag(), RateLimiter('pulse', 0),
            Logbook(tmp_path), Stage(), cat, SimpleNamespace(connected=False),
            lambda topic, payload: events.append((topic, payload)), workers)
        try:
            result = await asyncio.wait_for(engine.run_campaign(campaign()), timeout=4)
            assert result['completed'] == 2
            assert state.counters.attempts == 2
            assert state.counters.unobserved == 2
            assert state.counters.hangs == 0
            assert [payload['outcome'] for topic, payload in events if topic == 'attempt'] == ['unobserved', 'unobserved']
            assert not cat._armed
        finally:
            cat.disconnect()
            workers.shutdown_all()
    asyncio.run(run())


def test_api_startup_and_unknown_verdict(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from control.main import create_app
    monkeypatch.setenv('XDG_CONFIG_HOME', str(tmp_path / 'config'))
    monkeypatch.setenv('XDG_STATE_HOME', str(tmp_path / 'state'))
    monkeypatch.setenv('CONTROL_LOG_DIR', str(tmp_path / 'logs'))
    with TestClient(create_app()) as client:
        assert client.get('/healthz').json()['ok']
        assert client.get('/devices').status_code == 200
        assert client.get('/arm_state').json()['armed'] is False
        response = client.post('/campaigns/preflight', json=campaign().model_dump(mode='json'))
        assert response.status_code == 200
        assert not response.json()['ok']
        assert any('origin' in error for error in response.json()['blockers'])


def test_target_uart_classifies_and_clears(monkeypatch):
    import serial
    from control.orchestrator import _default_host_script, ParamsView

    class FakeUART:
        in_waiting = 0
        def __init__(self, *args, **kwargs):
            self.reads = [b'ESCAPED\n']
            self.cleared = False
            self.closed = False
        def reset_input_buffer(self):
            self.cleared = True
        def read(self, count):
            return self.reads.pop(0) if self.reads else b''
        def close(self):
            self.closed = True

    monkeypatch.setattr(serial, 'Serial', FakeUART)
    host = _default_host_script(None, {'target_serial_port': '/dev/mock', 'target_glitch_text': 'escaped'})
    ctx = SimpleNamespace(params=ParamsView({'verdict_timeout_s': .001}))
    host.setup(ctx)
    port = host.port
    host.prepare(ctx)
    assert port.cleared
    assert host.attempt(ctx)['outcome'] == 'glitch'
    host.teardown(ctx)
    assert port.closed


def test_discovery_connects_and_publishes_rig(monkeypatch):
    from control.main import _discovery_loop
    from control.workers import WorkerRegistry
    class Adapter:
        def __init__(self, discovered_port):
            self.connected = False
            self._port = None
            self.discovered_port = discovered_port
        def connect(self, port):
            self._port = port or self.discovered_port
            self.connected = True
        def disconnect(self):
            self.connected = False
            self._port = None
    async def run():
        ports = [
            {'device': '/dev/printer', 'guess': 'chipshover'},
            {'device': '/dev/cat', 'guess': 'chipshouter'},
        ]
        monkeypatch.setattr('control.main.list_ports', lambda _: ports)
        adapters = {'chipshover': Adapter('/dev/printer'), 'chipshouter': Adapter('/dev/cat')}
        state = AppState(devices={name: DeviceStatus(name=name) for name in adapters})
        workers = WorkerRegistry()
        events = []
        ctx = SimpleNamespace(config=Config(), adapter_for=adapters.get, workers=workers,
            manual_disconnects=set(), state=state,
            broadcast=lambda topic, payload: events.append((topic, payload)),
            broadcast_state=lambda: None)
        task = asyncio.create_task(_discovery_loop(ctx))
        try:
            for _ in range(100):
                if all(d.connected for d in state.devices.values()):
                    break
                await asyncio.sleep(.01)
            assert state.devices['chipshover'].port == '/dev/printer'
            assert state.devices['chipshouter'].port == '/dev/cat'
            assert len(events) == 2
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            workers.shutdown_all()
    asyncio.run(run())
