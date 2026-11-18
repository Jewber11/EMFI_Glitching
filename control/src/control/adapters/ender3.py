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
            self.command('M84 X Y Z S12000')
            self.command('G21')
            self.command('G90')
            self.command('M999')
        except Exception:
            self.serial.close()
            raise

    def command(self, command, timeout=30):
        result = self._exchange(command, timeout=timeout)
        if command == 'M999':
            # Some Marlin builds emit both a resend response and an extra ok.
            # Drain through the next serial timeout before issuing a command.
            deadline = time.monotonic() + 3
            while time.monotonic() < deadline and self.serial.readline():
                pass
        return result

    def _exchange(self, command, timeout=30, tolerate_stale_stop=False):
        self.serial.write((command + '\r\n').encode('ascii'))
        deadline = time.monotonic() + timeout
        lines = []
        while time.monotonic() < deadline:
            line = self.serial.readline().decode('utf-8', 'replace').strip()
            if line:
                lines.append(line)
                if line.lower().startswith(('error:', '!!')):
                    if tolerate_stale_stop and 'stop called because of bltouch' in line.lower():
                        continue
                    raise RuntimeError(f'Marlin {command}: ' + '\n'.join(lines))
                if line.lower().startswith('ok'):
                    return '\n'.join(lines)
        raise TimeoutError(f'Marlin timeout: {command}; response: ' + ('\n'.join(lines) or '(none)'))

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
        try:
            self.command('G28 X Y', timeout=180)
            self.command('M400', timeout=180)
            # Match this Ender-3 S1 Pro's probe-centered G28 XY position.
            self.command('G90')
            self.command('G1 X141.800 Y150.500 F3000')
            self.command('M400', timeout=120)
        except RuntimeError as error:
            if 'stop called because of bltouch' in str(error).lower():
                try:
                    self.command('M999')
                except (RuntimeError, TimeoutError, serial.SerialException) as reset_error:
                    raise RuntimeError(f'{error}\nM999 recovery failed: {reset_error}') from error
            raise
        self.command('M999')

    def move_relative(self, axis, distance):
        self.command('G91')
        try:
            self.command(f'G1 {axis}{distance:.3f} F3000')
            self.command('M400', timeout=120)
        finally:
            self.command('G90')

    def close(self):
        self.serial.close()


class Ender3Adapter(ChipShoverAdapter):
    name = 'ender3'

    def move_relative(self, axis, distance):
        self._require_connected()
        axis = axis.upper()
        if axis not in ('X', 'Y', 'Z'):
            raise ValueError(f'Invalid axis: {axis}')
        delta = [0.0, 0.0, 0.0]
        delta['XYZ'.index(axis)] = distance
        machine_delta = self._user_delta_to_machine(*delta)
        machine_axis = 'XYZ'[next((i for i, value in enumerate(machine_delta) if value), 'XYZ'.index(axis))]
        self._impl.move_relative(machine_axis, machine_delta['XYZ'.index(machine_axis)])

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
