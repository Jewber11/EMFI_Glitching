"""Exercise Marlin command framing and position parsing without a printer."""
from control.adapters.ender3 import Ender3Adapter


class FakeSerial:
    def __init__(self, *args, **kwargs):
        self.commands = []
        self.lines = []
        self.closed = False

    def reset_input_buffer(self):
        pass

    def write(self, data):
        command = data.decode().strip()
        self.commands.append(command)
        self.lines = ([b'X:10.00 Y:20.00 Z:3.00 E:0.00\n'] if command == 'M114' else []) + [b'ok\n']

    def readline(self):
        return self.lines.pop(0)

    def close(self):
        self.closed = True


def test_ender_marlin_motion(monkeypatch):
    monkeypatch.setattr('control.adapters.ender3.serial.Serial', FakeSerial)
    monkeypatch.setattr('control.adapters.ender3.time.sleep', lambda _: None)
    stage = Ender3Adapter()
    stage.connect('/dev/test')
    serial = stage._impl.serial
    assert stage.get_position() == (10, 20, 3)
    stage.set_origin()
    stage.move_absolute_logical(1, 2, 3)
    assert 'G1 X11.000 Y22.000 Z6.000 F3000' in serial.commands
    assert serial.commands[-1] == 'M400'
    stage.home()
    assert not stage.origin_set
    stage.set_origin()
    stage.disconnect()
    assert not stage.origin_set
    assert serial.closed
