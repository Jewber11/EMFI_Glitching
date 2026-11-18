"""Exercise Marlin command framing and position parsing without a printer."""
import pytest

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
        return self.lines.pop(0) if self.lines else b''

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


def test_home_reports_printer_error(monkeypatch):
    monkeypatch.setattr('control.adapters.ender3.serial.Serial', FakeSerial)
    monkeypatch.setattr('control.adapters.ender3.time.sleep', lambda _: None)
    stage = Ender3Adapter()
    stage.connect('/dev/test')
    serial = stage._impl.serial
    original_write = serial.write

    def write(data):
        original_write(data)
        if data == b'G28 X Y\r\n':
            serial.lines = [b'echo:busy: processing\n', b'Error:Homing failed\n']

    serial.write = write
    with pytest.raises(RuntimeError, match=r'(?s)Marlin G28 X Y:.*busy: processing.*Error:Homing failed'):
        stage.home()
    assert serial.commands[-1] == 'G28 X Y'


def test_bltouch_stop_recovers_before_next_command(monkeypatch):
    monkeypatch.setattr('control.adapters.ender3.serial.Serial', FakeSerial)
    monkeypatch.setattr('control.adapters.ender3.time.sleep', lambda _: None)
    stage = Ender3Adapter()
    stage.connect('/dev/test')
    serial = stage._impl.serial
    original_write = serial.write

    def write(data):
        original_write(data)
        if data == b'G28 X Y\r\n':
            serial.lines = [b'Error:!! STOP called because of BLTouch error - restart with M999\n']

    serial.write = write
    with pytest.raises(RuntimeError, match='STOP called because of BLTouch'):
        stage.home()
    stage._impl.command('G90')
    assert serial.commands[-2:] == ['M999', 'G90']


def test_original_initialization_and_homing_sequence(monkeypatch):
    monkeypatch.setattr('control.adapters.ender3.serial.Serial', FakeSerial)
    monkeypatch.setattr('control.adapters.ender3.time.sleep', lambda _: None)
    stage = Ender3Adapter()
    stage.connect('/dev/test')
    stage.home()
    assert stage._impl.serial.commands == [
        'M84 X Y Z S12000', 'G21', 'G90', 'M999', 'G28 X Y', 'M400',
        'G90', 'G1 X141.800 Y150.500 F3000', 'M400', 'M999',
    ]


def test_relative_move_uses_original_sequence(monkeypatch):
    monkeypatch.setattr('control.adapters.ender3.serial.Serial', FakeSerial)
    monkeypatch.setattr('control.adapters.ender3.time.sleep', lambda _: None)
    stage = Ender3Adapter()
    stage.connect('/dev/test')
    serial = stage._impl.serial
    stage.move_relative('X', 1)
    assert serial.commands[-4:] == ['G91', 'G1 X1.000 F3000', 'M400', 'G90']
