"""Ender 3 Marlin motion adapter, retaining the shared coordinate transforms."""
import re
import time
import serial
from control.adapters.chipshover import ChipShoverAdapter


class _Marlin:
    def __init__(self, port):
        self.serial = serial.Serial(port, 115200, timeout=1, write_timeout=2)
        try:
            time.sleep(2)
            self.serial.reset_input_buffer()
            self.command('G21')
            self.command('G90')
        except Exception:
            self.serial.close()
            raise

    def command(self, command, timeout=30):
        self.serial.write((command + '\n').encode('ascii'))
        deadline = time.monotonic() + timeout
        lines = []
        while time.monotonic() < deadline:
            line = self.serial.readline().decode('utf-8', 'replace').strip()
            if line:
                lines.append(line)
                if line.lower().startswith(('error:', '!!')):
                    raise RuntimeError('Marlin: ' + line)
                if line.lower().startswith('ok'):
                    return '\n'.join(lines)
        raise TimeoutError(f'Marlin timeout: {command}')

    def get_position(self):
        response = self.command('M114')
        match = re.search(r'X:\s*(-?[\d.]+)\s+Y:\s*(-?[\d.]+)\s+Z:\s*(-?[\d.]+)', response, re.I)
        if not match:
            raise RuntimeError(f'Invalid Marlin position: {response}')
        return tuple(map(float, match.groups()))

    def move(self, x, y, z):
        self.command('G90')
        self.command(f'G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F3000')
        self.command('M400', timeout=120)

    def home(self):
        self.command('G28', timeout=180)
        self.command('M400', timeout=180)

    def close(self):
        self.serial.close()


class Ender3Adapter(ChipShoverAdapter):
    name = 'ender3'

    def connect(self, port=None):
        if not port:
            raise ValueError('Ender 3: no serial port specified')
        if self.connected:
            raise RuntimeError('Ender 3 already connected')
        self._origin_machine = (0.0, 0.0, 0.0)
        self._origin_set = False
        self._impl = _Marlin(port)
        self._port = port
        self._last_error = None

    def disconnect(self):
        try:
            super().disconnect()
        finally:
            self._origin_machine = (0.0, 0.0, 0.0)
            self._origin_set = False
