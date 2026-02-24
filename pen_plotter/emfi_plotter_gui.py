#!/usr/bin/env python3
"""
EMFI Plotter Control GUI  v2
All-in-one interface for FaultyCat EMFI scanning with a pen plotter (GRBL).
Uses plotter.py for XY motion + spindle (Z), and a separate serial port for FaultyCat.

Changes v2:
  - Default plotter port /dev/ttyUSB0, FaultyCat /dev/ttyUSB1 (both ttyUSB)
  - All step/jog inputs are text Entry boxes (no sliders)
  - Z config: z_start + z_max + z_step  →  multi-height brute-force sweep
  - Predicted scan time + live ETA shown during scan
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import time
import serial
import serial.tools.list_ports
import json
import os
import math
import numpy as np
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

# ──────────────────────────────────────────────────────────────────────────────
# Plotter wrapper
# ──────────────────────────────────────────────────────────────────────────────

class Plotter:
    STATUS_FILE = "/tmp/emfi_plotter_status.json"

    def __init__(self, port, baud=115200, unlock=True):
        if not os.path.exists(port):
            raise FileNotFoundError(f"Serial device {port} not found")
        self.ser = serial.Serial(port, baudrate=baud, timeout=1, write_timeout=1)
        self.ser.write(b"\r\n\r\n")
        time.sleep(2)
        self.ser.reset_input_buffer()
        if unlock:
            self.send_line("$X")
        self.state = {"x": 0.0, "y": 0.0, "z": 0.0}
        if os.path.exists(self.STATUS_FILE):
            try:
                with open(self.STATUS_FILE) as f:
                    self.state = json.load(f)
            except Exception:
                pass

    def save_state(self):
        with open(self.STATUS_FILE, "w") as f:
            json.dump(self.state, f)

    def send_line(self, line, wait_ok=True, max_lines=100):
        self.ser.write((line + "\n").encode())
        if not wait_ok:
            return []
        lines = []
        for _ in range(max_lines):
            resp = self.ser.readline().decode(errors="ignore").strip()
            if not resp:
                continue
            lines.append(resp)
            if resp.lower() == "ok":
                return lines
            if resp.lower().startswith(("error", "alarm")):
                raise RuntimeError(f"GRBL: {resp}")
        raise TimeoutError("No valid response from GRBL")

    def get_position(self):
        return self.state.copy()

    def move(self, x=None, y=None, feed=1000):
        self.send_line("G91")
        cmd = "G1"
        if x is not None:
            cmd += f" X{x:.4f}"
            self.state["x"] += x
        if y is not None:
            cmd += f" Y{y:.4f}"
            self.state["y"] += y
        cmd += f" F{feed}"
        self.send_line(cmd)
        self.send_line("G90")
        self.save_state()

    def move_absolute(self, x=None, y=None, feed=1000):
        self.send_line("G90")
        cmd = "G1"
        if x is not None:
            cmd += f" X{x:.4f}"
            self.state["x"] = float(x)
        if y is not None:
            cmd += f" Y{y:.4f}"
            self.state["y"] = float(y)
        cmd += f" F{feed}"
        self.send_line(cmd)
        self.save_state()

    def set_spindle(self, speed=0, clockwise=True):
        if speed <= 0:
            self.send_line("M5")
            self.state["z"] = 0.0
        else:
            dir_cmd = "M3" if clockwise else "M4"
            self.send_line(f"{dir_cmd} S{int(speed)}")
            self.state["z"] = float(speed)
        self.save_state()

    def set_home(self):
        self.state["x"] = 0.0
        self.state["y"] = 0.0
        self.save_state()

    def close(self):
        self.ser.close()


# ──────────────────────────────────────────────────────────────────────────────
# FaultyCat serial helper
# ──────────────────────────────────────────────────────────────────────────────

class FaultyCat:
    def __init__(self, port, baud=115200):
        self.ser = serial.Serial(port, baudrate=baud, timeout=1)
        time.sleep(0.5)
        self.ser.reset_input_buffer()

    def send(self, cmd):
        self.ser.write((cmd.strip() + "\r\n").encode())
        time.sleep(0.05)
        resp = b""
        deadline = time.time() + 0.3
        while time.time() < deadline:
            if self.ser.in_waiting:
                resp += self.ser.read(self.ser.in_waiting)
            time.sleep(0.01)
        return resp.decode(errors="ignore").strip()

    def arm(self):    return self.send("arm")
    def disarm(self): return self.send("disarm")
    def pulse(self):  return self.send("pulse")
    def close(self):  self.ser.close()


# ──────────────────────────────────────────────────────────────────────────────
# Scan path helpers
# ──────────────────────────────────────────────────────────────────────────────

def generate_snake_path(x_min, x_max, y_min, y_max, step_x, step_y):
    """Boustrophedon XY path starting at (x_min, y_min)."""
    step_x = max(step_x, 0.001)
    step_y = max(step_y, 0.001)
    nx = max(1, int(round((x_max - x_min) / step_x)) + 1)
    ny = max(1, int(round((y_max - y_min) / step_y)) + 1)
    x_vals = [x_min + i * step_x for i in range(nx)]
    y_vals = [y_min + j * step_y for j in range(ny)]
    points = []
    for j, y in enumerate(y_vals):
        row = x_vals if j % 2 == 0 else list(reversed(x_vals))
        for x in row:
            points.append((round(x, 4), round(y, 4)))
    return points


def build_z_levels(z_start, z_max, z_step):
    """Return sorted list of spindle-speed Z values from z_start up to z_max."""
    z_step = max(z_step, 0.001)
    levels = []
    z = z_start
    while z <= z_max + 1e-9:
        levels.append(round(z, 4))
        z += z_step
    if not levels:
        levels = [z_start]
    return levels


def estimate_scan_time(xy_points, z_levels, feed_mm_per_min,
                        pulses_per_loc, pulse_delay, settle_delay):
    """Estimate total scan duration in seconds."""
    if not xy_points or not z_levels:
        return 0.0
    feed_mms = max(feed_mm_per_min / 60.0, 0.001)
    total_dist = sum(
        math.hypot(xy_points[i][0] - xy_points[i-1][0],
                   xy_points[i][1] - xy_points[i-1][1])
        for i in range(1, len(xy_points))
    )
    n_pts = len(xy_points)
    n_z   = len(z_levels)
    move_time   = (total_dist * n_z) / feed_mms
    pulse_time  = n_pts * n_z * pulses_per_loc * pulse_delay
    settle_time = n_pts * n_z * settle_delay
    return move_time + pulse_time + settle_time


def format_duration(seconds):
    seconds = int(max(0, seconds))
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    if h:
        return f"{h}h {m:02d}m {s:02d}s"
    if m:
        return f"{m}m {s:02d}s"
    return f"{s}s"


# ──────────────────────────────────────────────────────────────────────────────
# GUI
# ──────────────────────────────────────────────────────────────────────────────

STATE_FILE = os.path.expanduser("~/.emfi_plotter_gui.json")

BG_DARK  = "#1e1e2e"
BG_MID   = "#2a2a3e"
FG       = "#cdd6f4"
GREEN    = "#a6e3a1"
YELLOW   = "#f9e2af"
CYAN     = "#89dceb"


class EMFIPlotterGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EMFI Plotter Control  v2")
        self.root.configure(bg=BG_DARK)
        self.root.geometry("1440x880")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.plotter = None
        self.faultycat = None

        self.scanning = False
        self.scan_thread = None
        self.scan_data = []
        self.scan_start_time = None

        self.corner_bl = None
        self.corner_tr = None

        # ── Tk variables ──────────────────────────────────────────────────────
        self.plotter_port    = tk.StringVar(value="/dev/ttyUSB0")
        self.plotter_baud    = tk.IntVar(value=115200)
        self.fc_port         = tk.StringVar(value="/dev/ttyUSB1")
        self.fc_baud         = tk.IntVar(value=115200)

        self.step_x          = tk.DoubleVar(value=0.5)
        self.step_y          = tk.DoubleVar(value=0.5)
        self.z_start         = tk.DoubleVar(value=10.0)
        self.z_max           = tk.DoubleVar(value=40.0)
        self.z_step          = tk.DoubleVar(value=10.0)
        self.feed_rate       = tk.IntVar(value=1000)
        self.pulses_per_loc  = tk.IntVar(value=5)
        self.pulse_delay     = tk.DoubleVar(value=0.05)
        self.settle_delay    = tk.DoubleVar(value=0.10)

        self.move_step       = tk.DoubleVar(value=0.5)
        self.z_manual        = tk.DoubleVar(value=20.0)

        self._build_ui()
        self._load_state()
        self._refresh_position()

    # ══════════════════════════════════════════════════════════════════════════
    # UI construction
    # ══════════════════════════════════════════════════════════════════════════

    def _build_ui(self):
        self.status_bar = tk.Label(
            self.root, text="Disconnected — configure connections below",
            bg=BG_MID, fg=YELLOW, anchor="w", padx=8, font=("Courier", 9))
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL, bg=BG_DARK,
                               sashwidth=4, sashrelief=tk.RAISED)
        pane.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        left  = tk.Frame(pane, bg=BG_DARK, width=480)
        right = tk.Frame(pane, bg=BG_DARK)
        pane.add(left,  minsize=440)
        pane.add(right, minsize=560)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill=tk.BOTH, expand=True)
        t1 = ttk.Frame(nb); t2 = ttk.Frame(nb); t3 = ttk.Frame(nb)
        nb.add(t1, text="  Connections  ")
        nb.add(t2, text="  Manual Control  ")
        nb.add(t3, text="  Scan Config  ")
        self._build_connections(t1)
        self._build_manual(t2)
        self._build_scan_config(t3)

    # ── Connections ───────────────────────────────────────────────────────────

    def _build_connections(self, parent):
        detected = [p.device for p in serial.tools.list_ports.comports()]
        usb_ports = [p for p in detected if "ttyUSB" in p or "ttyACM" in p or "COM" in p]
        fallback = usb_ports or ["/dev/ttyUSB0", "/dev/ttyUSB1"]

        # -- Plotter --
        pf = ttk.LabelFrame(parent, text="Plotter (GRBL)  —  /dev/ttyUSB0", padding=6)
        pf.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(pf, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Combobox(pf, textvariable=self.plotter_port, values=fallback, width=20).grid(row=0, column=1, padx=4)
        ttk.Label(pf, text="Baud:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(pf, textvariable=self.plotter_baud, width=12).grid(row=1, column=1, padx=4, sticky=tk.W)
        br = tk.Frame(pf); br.grid(row=2, column=0, columnspan=2, pady=4)
        self.btn_conn_plotter = ttk.Button(br, text="Connect",    command=self.connect_plotter)
        self.btn_disc_plotter = ttk.Button(br, text="Disconnect", command=self.disconnect_plotter, state=tk.DISABLED)
        self.btn_conn_plotter.pack(side=tk.LEFT, padx=3)
        self.btn_disc_plotter.pack(side=tk.LEFT, padx=3)
        self.lbl_plotter_status = ttk.Label(pf, text="● Disconnected", foreground="red")
        self.lbl_plotter_status.grid(row=3, column=0, columnspan=2)

        # -- FaultyCat --
        ff = ttk.LabelFrame(parent, text="FaultyCat EMFI  —  /dev/ttyUSB1", padding=6)
        ff.pack(fill=tk.X, padx=8, pady=6)
        ttk.Label(ff, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Combobox(ff, textvariable=self.fc_port, values=fallback, width=20).grid(row=0, column=1, padx=4)
        ttk.Label(ff, text="Baud:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(ff, textvariable=self.fc_baud, width=12).grid(row=1, column=1, padx=4, sticky=tk.W)
        fr = tk.Frame(ff); fr.grid(row=2, column=0, columnspan=2, pady=4)
        self.btn_conn_fc      = ttk.Button(fr, text="Connect",    command=self.connect_faultycat)
        self.btn_disc_fc      = ttk.Button(fr, text="Disconnect", command=self.disconnect_faultycat, state=tk.DISABLED)
        self.btn_arm_fc       = ttk.Button(fr, text="Arm ⚡",     command=self.arm_faultycat,        state=tk.DISABLED)
        self.btn_disarm_fc    = ttk.Button(fr, text="Disarm",     command=self.disarm_faultycat,     state=tk.DISABLED)
        self.btn_manual_pulse = ttk.Button(fr, text="Pulse ⚡",   command=self.manual_pulse,         state=tk.DISABLED)
        for b in (self.btn_conn_fc, self.btn_disc_fc, self.btn_arm_fc,
                  self.btn_disarm_fc, self.btn_manual_pulse):
            b.pack(side=tk.LEFT, padx=2)
        self.lbl_fc_status = ttk.Label(ff, text="● Not Connected", foreground="gray")
        self.lbl_fc_status.grid(row=3, column=0, columnspan=2)

        # -- Serial log --
        lf = ttk.LabelFrame(parent, text="Serial Log", padding=4)
        lf.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        self.serial_log = scrolledtext.ScrolledText(
            lf, height=10, font=("Courier", 8), bg="#0d0d1a", fg="#a6e3a1", state=tk.DISABLED)
        self.serial_log.pack(fill=tk.BOTH, expand=True)

    # ── Manual Control ────────────────────────────────────────────────────────

    def _build_manual(self, parent):
        # Position
        pf = ttk.LabelFrame(parent, text="Current Position", padding=6)
        pf.pack(fill=tk.X, padx=8, pady=6)
        self.lbl_pos = ttk.Label(pf, text="X: ---   Y: ---   Z(spindle): ---",
                                  font=("Courier", 11, "bold"))
        self.lbl_pos.pack()

        # XY jog — entry box only
        jf = ttk.LabelFrame(parent, text="XY Jog", padding=8)
        jf.pack(fill=tk.X, padx=8, pady=4)

        sr = tk.Frame(jf); sr.pack(fill=tk.X, pady=(0, 6))
        ttk.Label(sr, text="Step size (mm):").pack(side=tk.LEFT)
        ttk.Entry(sr, textvariable=self.move_step, width=8).pack(side=tk.LEFT, padx=6)
        ttk.Label(sr, text="← type value, then click arrow",
                  foreground="gray", font=("TkDefaultFont", 7)).pack(side=tk.LEFT)

        pad = tk.Frame(jf); pad.pack()
        ttk.Button(pad, text="▲ Y+", width=8,
                   command=lambda: self._jog(y=self._ms())).grid(row=0, column=1, padx=3, pady=3)
        ttk.Button(pad, text="◄ X-", width=8,
                   command=lambda: self._jog(x=-self._ms())).grid(row=1, column=0, padx=3, pady=3)
        ttk.Button(pad, text="Set Home", width=8,
                   command=self._set_home).grid(row=1, column=1, padx=3, pady=3)
        ttk.Button(pad, text="X+ ►", width=8,
                   command=lambda: self._jog(x=self._ms())).grid(row=1, column=2, padx=3, pady=3)
        ttk.Button(pad, text="▼ Y-", width=8,
                   command=lambda: self._jog(y=-self._ms())).grid(row=2, column=1, padx=3, pady=3)

        # Z / Spindle — entry box
        zf = ttk.LabelFrame(parent, text="Z / Spindle Speed  (plotter.set_spindle)", padding=8)
        zf.pack(fill=tk.X, padx=8, pady=4)
        zr = tk.Frame(zf); zr.pack(fill=tk.X)
        ttk.Label(zr, text="Speed:").pack(side=tk.LEFT)
        ttk.Entry(zr, textvariable=self.z_manual, width=8).pack(side=tk.LEFT, padx=6)
        ttk.Button(zr, text="Set Z", command=lambda: self._set_spindle(self.z_manual.get())).pack(side=tk.LEFT, padx=4)
        ttk.Button(zr, text="Stop Spindle (M5)", command=lambda: self._set_spindle(0)).pack(side=tk.LEFT, padx=4)

        # Chip corners
        cf = ttk.LabelFrame(parent, text="Chip Corner Capture", padding=8)
        cf.pack(fill=tk.X, padx=8, pady=4)
        ttk.Button(cf, text="📌 Set Bottom-Left (BL) — captures current pos",
                   command=self.set_corner_bl).pack(fill=tk.X, pady=2)
        self.lbl_bl = ttk.Label(cf, text="BL: not set", foreground="gray"); self.lbl_bl.pack()
        ttk.Button(cf, text="📌 Set Top-Right (TR) — captures current pos",
                   command=self.set_corner_tr).pack(fill=tk.X, pady=2)
        self.lbl_tr = ttk.Label(cf, text="TR: not set", foreground="gray"); self.lbl_tr.pack()
        nav = tk.Frame(cf); nav.pack(pady=4)
        ttk.Button(nav, text="Go BL", command=self.go_bl).pack(side=tk.LEFT, padx=6)
        ttk.Button(nav, text="Go TR", command=self.go_tr).pack(side=tk.LEFT, padx=6)
        self.lbl_area = ttk.Label(cf, text="Area: --", foreground="black"); self.lbl_area.pack()

    def _ms(self):
        try: return float(self.move_step.get())
        except: return 0.5

    # ── Scan Config ───────────────────────────────────────────────────────────

    def _build_scan_config(self, parent):
        # XY + timing params
        sf = ttk.LabelFrame(parent, text="XY Scan Parameters", padding=10)
        sf.pack(fill=tk.X, padx=8, pady=6)
        sf.columnconfigure(2, weight=1)

        rows = [
            ("Step X (mm):",         self.step_x,         "XY grid step along X"),
            ("Step Y (mm):",         self.step_y,         "XY grid step along Y"),
            ("Feed rate (mm/min):",  self.feed_rate,      "movement speed"),
            ("Pulses per location:", self.pulses_per_loc, "N pulses before moving"),
            ("Pulse delay (s):",     self.pulse_delay,    "delay between pulses at same spot"),
            ("Settle delay (s):",    self.settle_delay,   "wait after each move before pulsing"),
        ]
        for i, (lbl, var, tip) in enumerate(rows):
            ttk.Label(sf, text=lbl).grid(row=i, column=0, sticky=tk.W, pady=3)
            ttk.Entry(sf, textvariable=var, width=10).grid(row=i, column=1, padx=6, sticky=tk.W)
            ttk.Label(sf, text=tip, foreground="gray",
                      font=("TkDefaultFont", 7)).grid(row=i, column=2, sticky=tk.W, padx=2)

        # Z height sweep
        zf = ttk.LabelFrame(parent,
                             text="Z / Spindle Height Sweep  (brute-force chip distance)",
                             padding=10)
        zf.pack(fill=tk.X, padx=8, pady=4)
        zf.columnconfigure(2, weight=1)

        z_rows = [
            ("Z start (spindle speed):", self.z_start, "lowest / closest to chip"),
            ("Z max  (spindle speed):",  self.z_max,   "highest / farthest from chip"),
            ("Z step (increment):",      self.z_step,  "step size between Z layers"),
        ]
        for i, (lbl, var, tip) in enumerate(z_rows):
            ttk.Label(zf, text=lbl).grid(row=i, column=0, sticky=tk.W, pady=3)
            ttk.Entry(zf, textvariable=var, width=10).grid(row=i, column=1, padx=6, sticky=tk.W)
            ttk.Label(zf, text=tip, foreground="gray",
                      font=("TkDefaultFont", 7)).grid(row=i, column=2, sticky=tk.W, padx=2)

        self.lbl_z_layers = ttk.Label(zf, text="Z layers: --", foreground="black")
        self.lbl_z_layers.grid(row=len(z_rows), column=0, columnspan=3, pady=3)

        # Bind recalc
        for v in (self.step_x, self.step_y, self.z_start, self.z_max, self.z_step,
                  self.feed_rate, self.pulses_per_loc, self.pulse_delay, self.settle_delay):
            v.trace_add("write", lambda *_: self.root.after(150, self._update_estimates))

        # Summary / prediction
        ef = ttk.LabelFrame(parent, text="Scan Summary & Predicted Time", padding=8)
        ef.pack(fill=tk.X, padx=8, pady=4)
        self.lbl_summary = ttk.Label(ef,
                                      text="Set corners and parameters to see estimate.",
                                      font=("Courier", 9), justify=tk.LEFT, foreground="black")
        self.lbl_summary.pack(anchor=tk.W)
        ttk.Button(ef, text="🔄 Recalculate", command=self._update_estimates).pack(pady=2)

        # Scan control
        ctrl_f = ttk.LabelFrame(parent, text="Scan Control", padding=8)
        ctrl_f.pack(fill=tk.X, padx=8, pady=4)
        cr = tk.Frame(ctrl_f); cr.pack(fill=tk.X)
        self.btn_start_scan = ttk.Button(cr, text="▶ Start Scan",   command=self.start_scan)
        self.btn_stop_scan  = ttk.Button(cr, text="■ Stop Scan",    command=self.stop_scan,   state=tk.DISABLED)
        self.btn_reset_data = ttk.Button(cr, text="🔁 Reset Data",   command=self.reset_data)
        self.btn_heatmap    = ttk.Button(cr, text="📊 Show Heatmap", command=self.show_heatmap)
        for b in (self.btn_start_scan, self.btn_stop_scan, self.btn_reset_data, self.btn_heatmap):
            b.pack(side=tk.LEFT, padx=3)

        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(ctrl_f, variable=self.progress_var,
                                             maximum=100, length=420)
        self.progress_bar.pack(fill=tk.X, padx=4, pady=6)
        self.lbl_progress = ttk.Label(ctrl_f, text="Idle", foreground="black")
        self.lbl_progress.pack()
        self.lbl_eta = ttk.Label(ctrl_f, text="", foreground="black", font=("Courier", 9))
        self.lbl_eta.pack()

        # Live stats
        stf = ttk.LabelFrame(parent, text="Live Stats", padding=6)
        stf.pack(fill=tk.X, padx=8, pady=4)
        self.lbl_stats = ttk.Label(stf, text="No scan data yet.",
                                    font=("Courier", 9), justify=tk.LEFT)
        self.lbl_stats.pack(anchor=tk.W)

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right(self, parent):
        fig_frame = ttk.LabelFrame(parent, text="Scan Path Preview & Live Heatmap", padding=4)
        fig_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        self.fig = Figure(figsize=(8, 7), facecolor=BG_DARK)
        self.ax  = self.fig.add_subplot(111, facecolor=BG_MID)
        self._style_ax(self.ax, "Snake Scan Path")
        self.canvas = FigureCanvasTkAgg(self.fig, fig_frame)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        self._draw_path_preview()

        lf = ttk.LabelFrame(parent, text="Scan Log", padding=4)
        lf.pack(fill=tk.X, padx=4, pady=(0, 4))
        self.scan_log = scrolledtext.ScrolledText(
            lf, height=6, font=("Courier", 8),
            bg="#0d0d1a", fg="#cdd6f4", state=tk.DISABLED)
        self.scan_log.pack(fill=tk.BOTH, expand=True)

    def _style_ax(self, ax, title=""):
        ax.set_facecolor(BG_MID)
        ax.tick_params(colors=FG)
        ax.set_xlabel("X (mm)", color=FG)
        ax.set_ylabel("Y (mm)", color=FG)
        ax.set_title(title, color=FG)
        for sp in ax.spines.values():
            sp.set_edgecolor(FG)

    # ══════════════════════════════════════════════════════════════════════════
    # Connections
    # ══════════════════════════════════════════════════════════════════════════

    def connect_plotter(self):
        try:
            self.plotter = Plotter(self.plotter_port.get(), self.plotter_baud.get())
            self.lbl_plotter_status.config(text="● Connected", foreground="green")
            self.btn_conn_plotter.config(state=tk.DISABLED)
            self.btn_disc_plotter.config(state=tk.NORMAL)
            self._log_serial(f"Plotter connected on {self.plotter_port.get()}")
            self._set_status(f"Plotter connected on {self.plotter_port.get()}")
        except Exception as e:
            messagebox.showerror("Plotter Connection Error", str(e))

    def disconnect_plotter(self):
        if self.plotter:
            try: self.plotter.close()
            except: pass
            self.plotter = None
        self.lbl_plotter_status.config(text="● Disconnected", foreground="red")
        self.btn_conn_plotter.config(state=tk.NORMAL)
        self.btn_disc_plotter.config(state=tk.DISABLED)
        self._log_serial("Plotter disconnected")

    def connect_faultycat(self):
        try:
            self.faultycat = FaultyCat(self.fc_port.get(), self.fc_baud.get())
            self.lbl_fc_status.config(text="● Connected", foreground="green")
            self.btn_conn_fc.config(state=tk.DISABLED)
            for b in (self.btn_disc_fc, self.btn_arm_fc,
                      self.btn_disarm_fc, self.btn_manual_pulse):
                b.config(state=tk.NORMAL)
            self._log_serial(f"FaultyCat connected on {self.fc_port.get()}")
        except Exception as e:
            messagebox.showerror("FaultyCat Connection Error", str(e))

    def disconnect_faultycat(self):
        if self.faultycat:
            try: self.faultycat.close()
            except: pass
            self.faultycat = None
        self.lbl_fc_status.config(text="● Not Connected", foreground="gray")
        self.btn_conn_fc.config(state=tk.NORMAL)
        for b in (self.btn_disc_fc, self.btn_arm_fc,
                  self.btn_disarm_fc, self.btn_manual_pulse):
            b.config(state=tk.DISABLED)

    def arm_faultycat(self):
        if self.faultycat:
            self._log_serial(f"FC arm → {self.faultycat.arm()}")

    def disarm_faultycat(self):
        if self.faultycat:
            self._log_serial(f"FC disarm → {self.faultycat.disarm()}")

    def manual_pulse(self):
        if self.faultycat:
            self._log_serial(f"FC manual pulse → {self.faultycat.pulse()}")

    # ══════════════════════════════════════════════════════════════════════════
    # Movement
    # ══════════════════════════════════════════════════════════════════════════

    def _jog(self, x=None, y=None):
        if not self.plotter:
            self._set_status("Plotter not connected"); return
        try:
            self.plotter.move(x=x, y=y, feed=self.feed_rate.get())
        except Exception as e:
            self._log_serial(f"Jog error: {e}")

    def _set_home(self):
        if not self.plotter: return
        self.plotter.set_home()
        self._log_serial("Home set at current XY position")

    def _set_spindle(self, speed):
        if not self.plotter: return
        try:
            self.plotter.set_spindle(float(speed))
            self._log_serial(f"Spindle → {speed}")
        except Exception as e:
            self._log_serial(f"Spindle error: {e}")

    # ══════════════════════════════════════════════════════════════════════════
    # Chip corners
    # ══════════════════════════════════════════════════════════════════════════

    def set_corner_bl(self):
        if not self.plotter:
            messagebox.showwarning("No Plotter", "Connect the plotter first."); return
        self.corner_bl = self.plotter.get_position().copy()
        self.lbl_bl.config(
            text=f"BL: X={self.corner_bl['x']:.3f}  Y={self.corner_bl['y']:.3f}",
            foreground=GREEN)
        self._log_serial(f"Corner BL: {self.corner_bl}")
        self._on_corners_changed()

    def set_corner_tr(self):
        if not self.plotter:
            messagebox.showwarning("No Plotter", "Connect the plotter first."); return
        self.corner_tr = self.plotter.get_position().copy()
        self.lbl_tr.config(
            text=f"TR: X={self.corner_tr['x']:.3f}  Y={self.corner_tr['y']:.3f}",
            foreground=GREEN)
        self._log_serial(f"Corner TR: {self.corner_tr}")
        self._on_corners_changed()

    def go_bl(self):
        if not self.plotter or not self.corner_bl: return
        cur = self.plotter.get_position()
        self.plotter.move(x=self.corner_bl["x"]-cur["x"],
                           y=self.corner_bl["y"]-cur["y"], feed=self.feed_rate.get())

    def go_tr(self):
        if not self.plotter or not self.corner_tr: return
        cur = self.plotter.get_position()
        self.plotter.move(x=self.corner_tr["x"]-cur["x"],
                           y=self.corner_tr["y"]-cur["y"], feed=self.feed_rate.get())

    def _on_corners_changed(self):
        if self.corner_bl and self.corner_tr:
            dx = abs(self.corner_tr["x"] - self.corner_bl["x"])
            dy = abs(self.corner_tr["y"] - self.corner_bl["y"])
            self.lbl_area.config(text=f"Area: {dx:.2f} × {dy:.2f} mm", foreground="black")
        self._update_estimates()
        self._draw_path_preview()

    # ══════════════════════════════════════════════════════════════════════════
    # Estimates
    # ══════════════════════════════════════════════════════════════════════════

    def _get_params(self):
        try:
            return dict(
                step_x       = float(self.step_x.get()),
                step_y       = float(self.step_y.get()),
                z_start      = float(self.z_start.get()),
                z_max        = float(self.z_max.get()),
                z_step       = float(self.z_step.get()),
                feed         = int(self.feed_rate.get()),
                ppl          = int(self.pulses_per_loc.get()),
                pulse_delay  = float(self.pulse_delay.get()),
                settle_delay = float(self.settle_delay.get()),
            )
        except (ValueError, tk.TclError):
            return None

    def _update_estimates(self, *_):
        if not self.corner_bl or not self.corner_tr:
            self.lbl_summary.config(text="Set both chip corners to see estimate.")
            self.lbl_z_layers.config(text="Z layers: --")
            return
        p = self._get_params()
        if p is None:
            self.lbl_summary.config(text="⚠ Invalid parameter value")
            return

        x_min = min(self.corner_bl["x"], self.corner_tr["x"])
        x_max = max(self.corner_bl["x"], self.corner_tr["x"])
        y_min = min(self.corner_bl["y"], self.corner_tr["y"])
        y_max = max(self.corner_bl["y"], self.corner_tr["y"])

        pts      = generate_snake_path(x_min, x_max, y_min, y_max, p["step_x"], p["step_y"])
        z_levels = build_z_levels(p["z_start"], p["z_max"], p["z_step"])
        total_pts = len(pts) * len(z_levels)
        total_pulses = total_pts * p["ppl"]
        est = estimate_scan_time(pts, z_levels, p["feed"],
                                  p["ppl"], p["pulse_delay"], p["settle_delay"])

        zlbl = f"Z layers: {len(z_levels)}"
        if len(z_levels) > 1:
            zlbl += f"  ({z_levels[0]} → {z_levels[-1]}, step {p['z_step']})"
        else:
            zlbl += f"  (only {z_levels[0]})"
        self.lbl_z_layers.config(text=zlbl, foreground="black")

        self.lbl_summary.config(text=(
            f"XY points / layer   : {len(pts)}\n"
            f"Z layers            : {len(z_levels)}\n"
            f"Total scan points   : {total_pts}\n"
            f"Total pulses        : {total_pulses}\n"
            f"Predicted scan time : {format_duration(est)}"
        ))

    # ══════════════════════════════════════════════════════════════════════════
    # Path preview
    # ══════════════════════════════════════════════════════════════════════════

    def _draw_path_preview(self, highlight_index=None):
        self.ax.clear()
        self._style_ax(self.ax, "Snake Scan Path  (first Z layer shown)")

        if self.corner_bl and self.corner_tr:
            x_min = min(self.corner_bl["x"], self.corner_tr["x"])
            x_max = max(self.corner_bl["x"], self.corner_tr["x"])
            y_min = min(self.corner_bl["y"], self.corner_tr["y"])
            y_max = max(self.corner_bl["y"], self.corner_tr["y"])

            p = self._get_params()
            sx = p["step_x"] if p else 0.5
            sy = p["step_y"] if p else 0.5
            pts = generate_snake_path(x_min, x_max, y_min, y_max, sx, sy)

            if pts:
                xs, ys = zip(*pts)
                self.ax.plot(xs, ys, color="#445566", linewidth=0.6, zorder=1)
                self.ax.scatter(xs, ys, s=10, color=CYAN, zorder=2, alpha=0.6)

                if self.scan_data:
                    gx = [d["x"] for d in self.scan_data]
                    gy = [d["y"] for d in self.scan_data]
                    gc = [d["glitch"] / (d["pulses"] or 1) for d in self.scan_data]
                    sc = self.ax.scatter(gx, gy, c=gc, cmap="RdYlGn",
                                         s=20, vmin=0, vmax=1, zorder=3)
                    try: self.fig.colorbar(sc, ax=self.ax, label="Glitch rate")
                    except: pass

                if highlight_index is not None and 0 <= highlight_index < len(pts):
                    hx, hy = pts[highlight_index]
                    self.ax.scatter([hx], [hy], s=100, color="white", marker="*", zorder=5)

                rx = [x_min, x_max, x_max, x_min, x_min]
                ry = [y_min, y_min, y_max, y_max, y_min]
                self.ax.plot(rx, ry, color=YELLOW, linewidth=1.5, linestyle="--", zorder=4)
                self.ax.text(x_min, y_min, " BL", color=GREEN, fontsize=8, va="top")
                self.ax.text(x_max, y_max, "TR ", color=GREEN, fontsize=8, ha="right")

        self.fig.tight_layout()
        self.canvas.draw_idle()

    # ══════════════════════════════════════════════════════════════════════════
    # Scan
    # ══════════════════════════════════════════════════════════════════════════

    def start_scan(self):
        if not self.plotter:
            messagebox.showerror("Error", "Plotter not connected."); return
        if not self.corner_bl or not self.corner_tr:
            messagebox.showerror("Error", "Set both chip corners first."); return
        p = self._get_params()
        if p is None:
            messagebox.showerror("Error", "Invalid scan parameter — check all fields are numeric."); return
        if self.scanning: return
        self.scanning = True
        self.scan_start_time = time.time()
        self.btn_start_scan.config(state=tk.DISABLED)
        self.btn_stop_scan.config(state=tk.NORMAL)
        self.scan_thread = threading.Thread(target=self._scan_worker, args=(p,), daemon=True)
        self.scan_thread.start()

    def stop_scan(self):
        self.scanning = False
        self._log_scan("⚠ Stop requested…")
        if self.faultycat:
            try: self.faultycat.disarm()
            except: pass

    def reset_data(self):
        if self.scanning:
            messagebox.showwarning("Scan Running", "Stop the scan before resetting."); return
        self.scan_data.clear()
        self.lbl_stats.config(text="No scan data yet.")
        self.progress_var.set(0)
        self.lbl_progress.config(text="Idle")
        self.lbl_eta.config(text="")
        self._draw_path_preview()
        self._log_scan("Data reset.")

    def _scan_worker(self, p):
        try:
            x_min = min(self.corner_bl["x"], self.corner_tr["x"])
            x_max = max(self.corner_bl["x"], self.corner_tr["x"])
            y_min = min(self.corner_bl["y"], self.corner_tr["y"])
            y_max = max(self.corner_bl["y"], self.corner_tr["y"])

            pts      = generate_snake_path(x_min, x_max, y_min, y_max, p["step_x"], p["step_y"])
            z_levels = build_z_levels(p["z_start"], p["z_max"], p["z_step"])
            total_pts = len(pts) * len(z_levels)

            if total_pts == 0:
                self._log_scan("No scan points — check step sizes and corners."); return

            est = estimate_scan_time(pts, z_levels, p["feed"],
                                      p["ppl"], p["pulse_delay"], p["settle_delay"])
            self._log_scan(
                f"Scan start: {len(pts)} XY pts × {len(z_levels)} Z layers = {total_pts} pts  "
                f"({p['ppl']} pulses each)  |  predicted: {format_duration(est)}")

            if self.faultycat:
                r = self.faultycat.arm()
                self._log_scan(f"FC arm → {r}")

            done = 0
            scan_t0 = time.time()

            for z_val in z_levels:
                if not self.scanning: break
                self._safe_call(lambda zv=z_val: self.plotter.set_spindle(zv))
                self._log_scan(f"── Z layer: spindle={z_val} ({z_levels.index(z_val)+1}/{len(z_levels)}) ──")

                for xy_idx, (tx, ty) in enumerate(pts):
                    if not self.scanning: break

                    cur = self.plotter.get_position()
                    try:
                        self.plotter.move(x=tx - cur["x"], y=ty - cur["y"], feed=p["feed"])
                    except Exception as e:
                        self._log_scan(f"Move error @ ({tx},{ty}): {e}"); break

                    time.sleep(p["settle_delay"])

                    glitch = crash = nothing = 0
                    for _ in range(p["ppl"]):
                        if not self.scanning: break
                        resp = ""
                        if self.faultycat:
                            try: resp = self.faultycat.pulse()
                            except Exception as e: resp = f"ERR:{e}"
                        rl = resp.lower()
                        if any(k in rl for k in ("glitch", "success", "fault")):
                            glitch += 1
                        elif any(k in rl for k in ("crash", "reset", "error")):
                            crash += 1
                        else:
                            nothing += 1
                        if p["pulse_delay"] > 0:
                            time.sleep(p["pulse_delay"])

                    self.scan_data.append({
                        "x": tx, "y": ty, "z": z_val,
                        "pulses": p["ppl"],
                        "glitch": glitch, "crash": crash, "nothing": nothing,
                    })

                    done += 1
                    elapsed = time.time() - scan_t0
                    eta = (elapsed / done * (total_pts - done)) if done else 0
                    pct = done / total_pts * 100
                    self.root.after(0, self._update_progress,
                                    done, total_pts, tx, ty, z_val,
                                    glitch, crash, pct, eta, xy_idx)

            if self.faultycat:
                try: self._log_scan(f"FC disarm → {self.faultycat.disarm()}")
                except: pass

            self._safe_call(lambda: self.plotter.set_spindle(0))
            elapsed_total = time.time() - scan_t0
            self._log_scan(
                ("✅ Scan complete." if self.scanning else "⚠ Scan stopped early.") +
                f"  Actual time: {format_duration(elapsed_total)}")

        except Exception as e:
            self._log_scan(f"❌ Scan error: {e}")
        finally:
            self.scanning = False
            self.root.after(0, lambda: self.btn_start_scan.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.btn_stop_scan.config(state=tk.DISABLED))
            self.root.after(0, lambda: self.lbl_eta.config(text=""))
            self.root.after(0, self._draw_path_preview)

    def _safe_call(self, fn):
        try: fn()
        except Exception as e: self._log_scan(f"Error: {e}")

    def _update_progress(self, done, total, x, y, z, glitch, crash, pct, eta, xy_idx):
        self.progress_var.set(pct)
        self.lbl_progress.config(
            text=f"Point {done}/{total}  |  X={x:.3f}  Y={y:.3f}  Z={z:.0f}  |  G:{glitch} C:{crash}")
        self.lbl_eta.config(text=f"ETA: {format_duration(eta)}  |  {pct:.1f}% complete")
        self._update_stats()
        self._draw_path_preview(highlight_index=xy_idx)

    def _update_stats(self):
        if not self.scan_data: return
        pts     = len(self.scan_data)
        pulses  = sum(d["pulses"] for d in self.scan_data)
        glitches= sum(d["glitch"] for d in self.scan_data)
        crashes = sum(d["crash"]  for d in self.scan_data)
        gr = glitches / pulses * 100 if pulses else 0
        cr = crashes  / pulses * 100 if pulses else 0
        self.lbl_stats.config(text=(
            f"Points: {pts}   Pulses: {pulses}\n"
            f"Glitches: {glitches} ({gr:.1f}%)   Crashes: {crashes} ({cr:.1f}%)"
        ))

    # ══════════════════════════════════════════════════════════════════════════
    # Heatmap
    # ══════════════════════════════════════════════════════════════════════════

    def show_heatmap(self):
        if not self.scan_data:
            messagebox.showinfo("No Data", "Run a scan first."); return

        z_set = sorted(set(d["z"] for d in self.scan_data))
        win = tk.Toplevel(self.root)
        win.title("EMFI Scan Heatmaps")
        win.geometry("1000x720")
        nb = ttk.Notebook(win)
        nb.pack(fill=tk.BOTH, expand=True)

        for z_val in z_set:
            layer = [d for d in self.scan_data if d["z"] == z_val]
            xs = sorted(set(d["x"] for d in layer))
            ys = sorted(set(d["y"] for d in layer))
            if not xs or not ys: continue

            g_grid = np.zeros((len(ys), len(xs)))
            c_grid = np.zeros((len(ys), len(xs)))
            xi_map = {v: i for i, v in enumerate(xs)}
            yi_map = {v: i for i, v in enumerate(ys)}
            for d in layer:
                t = d["pulses"] or 1
                g_grid[yi_map[d["y"]], xi_map[d["x"]]] = d["glitch"] / t * 100
                c_grid[yi_map[d["y"]], xi_map[d["x"]]] = d["crash"]  / t * 100

            ext = [min(xs), max(xs), min(ys), max(ys)]
            tab = ttk.Frame(nb)
            nb.add(tab, text=f"Z={z_val:.0f}")

            fig = Figure(figsize=(9, 6), facecolor=BG_DARK)
            ax1 = fig.add_subplot(121, facecolor=BG_MID)
            im1 = ax1.imshow(g_grid, cmap="RdYlGn", vmin=0, vmax=100,
                              aspect="auto", origin="lower", extent=ext)
            ax1.set_title(f"Glitch Rate (%)  Z={z_val:.0f}", color=FG)
            ax1.set_xlabel("X (mm)", color=FG); ax1.set_ylabel("Y (mm)", color=FG)
            ax1.tick_params(colors=FG); fig.colorbar(im1, ax=ax1)

            ax2 = fig.add_subplot(122, facecolor=BG_MID)
            im2 = ax2.imshow(c_grid, cmap="RdYlGn_r", vmin=0, vmax=100,
                              aspect="auto", origin="lower", extent=ext)
            ax2.set_title(f"Crash Rate (%)  Z={z_val:.0f}", color=FG)
            ax2.set_xlabel("X (mm)", color=FG)
            ax2.tick_params(colors=FG); fig.colorbar(im2, ax=ax2)
            fig.tight_layout()

            c = FigureCanvasTkAgg(fig, tab)
            c.get_tk_widget().pack(fill=tk.BOTH, expand=True)
            c.draw()

        best = max(self.scan_data, key=lambda d: d["glitch"] / (d["pulses"] or 1))
        br   = best["glitch"] / (best["pulses"] or 1) * 100
        ttk.Label(win,
                  text=f"Best location — X={best['x']:.3f}  Y={best['y']:.3f}  "
                       f"Z={best['z']:.0f}  Glitch rate={br:.1f}%",
                  foreground=GREEN, font=("Courier", 10, "bold")).pack(pady=6)

    # ══════════════════════════════════════════════════════════════════════════
    # Refresh + logging
    # ══════════════════════════════════════════════════════════════════════════

    def _refresh_position(self):
        if self.plotter:
            try:
                pos = self.plotter.get_position()
                self.lbl_pos.config(
                    text=f"X: {pos['x']:.3f}   Y: {pos['y']:.3f}   Z(spindle): {pos['z']:.0f}")
            except: pass
        self.root.after(500, self._refresh_position)

    def _log_serial(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.serial_log.config(state=tk.NORMAL)
        self.serial_log.insert(tk.END, f"[{ts}] {msg}\n")
        self.serial_log.see(tk.END)
        self.serial_log.config(state=tk.DISABLED)

    def _log_scan(self, msg):
        ts = time.strftime("%H:%M:%S")
        self.scan_log.config(state=tk.NORMAL)
        self.scan_log.insert(tk.END, f"[{ts}] {msg}\n")
        self.scan_log.see(tk.END)
        self.scan_log.config(state=tk.DISABLED)

    def _set_status(self, msg):
        self.status_bar.config(text=msg)

    # ══════════════════════════════════════════════════════════════════════════
    # State persistence
    # ══════════════════════════════════════════════════════════════════════════

    def _save_state(self):
        with open(STATE_FILE, "w") as f:
            json.dump({
                "geometry":       self.root.geometry(),
                "plotter_port":   self.plotter_port.get(),
                "plotter_baud":   self.plotter_baud.get(),
                "fc_port":        self.fc_port.get(),
                "fc_baud":        self.fc_baud.get(),
                "step_x":         self.step_x.get(),
                "step_y":         self.step_y.get(),
                "z_start":        self.z_start.get(),
                "z_max":          self.z_max.get(),
                "z_step":         self.z_step.get(),
                "feed_rate":      self.feed_rate.get(),
                "pulses_per_loc": self.pulses_per_loc.get(),
                "pulse_delay":    self.pulse_delay.get(),
                "settle_delay":   self.settle_delay.get(),
                "move_step":      self.move_step.get(),
                "z_manual":       self.z_manual.get(),
                "corner_bl":      self.corner_bl,
                "corner_tr":      self.corner_tr,
            }, f)

    def _load_state(self):
        if not os.path.exists(STATE_FILE): return
        try:
            with open(STATE_FILE) as f: s = json.load(f)
            if "geometry" in s: self.root.geometry(s["geometry"])
            self.plotter_port.set(s.get("plotter_port",  "/dev/ttyUSB0"))
            self.plotter_baud.set(s.get("plotter_baud",  115200))
            self.fc_port.set(s.get("fc_port",            "/dev/ttyUSB1"))
            self.fc_baud.set(s.get("fc_baud",            115200))
            self.step_x.set(s.get("step_x",              0.5))
            self.step_y.set(s.get("step_y",              0.5))
            self.z_start.set(s.get("z_start",            10.0))
            self.z_max.set(s.get("z_max",                40.0))
            self.z_step.set(s.get("z_step",              10.0))
            self.feed_rate.set(s.get("feed_rate",        1000))
            self.pulses_per_loc.set(s.get("pulses_per_loc", 5))
            self.pulse_delay.set(s.get("pulse_delay",    0.05))
            self.settle_delay.set(s.get("settle_delay",  0.10))
            self.move_step.set(s.get("move_step",        0.5))
            self.z_manual.set(s.get("z_manual",         20.0))
            if s.get("corner_bl"):
                self.corner_bl = s["corner_bl"]
                self.lbl_bl.config(
                    text=f"BL: X={self.corner_bl['x']:.3f}  Y={self.corner_bl['y']:.3f}",
                    foreground=GREEN)
            if s.get("corner_tr"):
                self.corner_tr = s["corner_tr"]
                self.lbl_tr.config(
                    text=f"TR: X={self.corner_tr['x']:.3f}  Y={self.corner_tr['y']:.3f}",
                    foreground=GREEN)
            self._on_corners_changed()
        except Exception as e:
            print(f"State load error: {e}")

    def on_close(self):
        if self.scanning:
            if not messagebox.askyesno("Scan Running", "Scan is active. Stop and exit?"):
                return
            self.stop_scan(); time.sleep(0.4)
        try: self._save_state()
        except: pass
        if self.plotter:
            try: self.plotter.close()
            except: pass
        if self.faultycat:
            try: self.faultycat.disarm(); self.faultycat.close()
            except: pass
        self.root.destroy()


# ──────────────────────────────────────────────────────────────────────────────

def main():
    root = tk.Tk()
    try: ttk.Style().theme_use("clam")
    except: pass
    EMFIPlotterGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
