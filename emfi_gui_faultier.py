"""
Enhanced EMFI Scanner GUI with Faultier Integration

Features:
- Faultier device connection with proper API
- Target state monitoring with state machine
- Automatic crash detection and power cycling
- Configurable glitch parameters (delay, pulse width)
- Trigger configuration
- Enhanced statistics with recovery counts
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import threading
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import time

from faultier_controller import FaultierController, TargetState, GlitchResult


class EMFIFaultierGUI:
    """Enhanced GUI for EMFI Scanner with Faultier Integration"""

    def __init__(self, root):
        self.root = root
        self.root.title("EMFI Scanner Control - Faultier Edition")
        self.root.geometry("1700x950")

        # Create controller instance
        self.controller = FaultierController()

        # Set up controller callbacks
        self.controller.on_state_change = self.on_target_state_change
        self.controller.on_message = self.on_controller_message

        # Configuration parameters
        self.probe_diameter = tk.DoubleVar(value=2.0)
        self.step_size = tk.DoubleVar(value=1.0)
        self.z_increment = tk.DoubleVar(value=0.1)
        self.max_z_height = tk.DoubleVar(value=0.5)
        self.pulses_per_location = tk.IntVar(value=10)

        # Glitch parameters (nanoseconds)
        self.glitch_delay = tk.IntVar(value=1000)
        self.glitch_pulse = tk.IntVar(value=100)

        # Trigger configuration
        self.trigger_type = tk.StringVar(value="RISING_EDGE")
        self.trigger_source = tk.StringVar(value="EXT0")
        self.glitch_output = tk.StringVar(value="CROWBAR")

        # Serial port parameters
        self.printer_port = tk.StringVar(value="/dev/ttyUSB0")
        self.printer_baudrate = tk.IntVar(value=115200)
        self.target_port = tk.StringVar(value="/dev/ttyUSB2")
        self.target_baudrate = tk.IntVar(value=115200)

        # Movement step size
        self.move_step = tk.DoubleVar(value=1.0)

        # Thread management
        self.scan_thread = None
        self.monitor_thread = None
        self.monitor_running = False

        # Build GUI
        self.create_widgets()

        # Start periodic UI updates
        self.update_ui_periodically()

    def create_widgets(self):
        # Main container with two panes
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Controls (split into two columns)
        left_container = ttk.Frame(main_pane)
        main_pane.add(left_container, width=900)

        # Create two columns in left container
        left_column = ttk.Frame(left_container)
        left_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        right_column = ttk.Frame(left_container)
        right_column.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # Right panel - Visualization
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame)

        # Build left column sections
        self.create_connection_section(left_column)
        self.create_faultier_config_section(left_column)
        self.create_manual_control_section(left_column)

        # Build right column sections
        self.create_target_status_section(right_column)
        self.create_scan_config_section(right_column)
        self.create_scan_control_section(right_column)
        self.create_status_section(right_column)

        # Build right panel - visualization
        self.create_visualization_section(right_frame)

    def create_connection_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Device Connections", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # Printer Connection
        printer_frame = ttk.LabelFrame(frame, text="3D Printer (Required)", padding=5)
        printer_frame.pack(fill=tk.X, pady=3)

        ttk.Label(printer_frame, text="Port:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=1)
        ttk.Entry(printer_frame, textvariable=self.printer_port, width=15, font=("Arial", 8)).grid(row=0, column=1, pady=1)

        ttk.Label(printer_frame, text="Baud:", font=("Arial", 8)).grid(row=1, column=0, sticky=tk.W, pady=1)
        ttk.Entry(printer_frame, textvariable=self.printer_baudrate, width=15, font=("Arial", 8)).grid(row=1, column=1, pady=1)

        self.printer_connect_btn = ttk.Button(printer_frame, text="Connect", command=self.connect_printer)
        self.printer_connect_btn.grid(row=2, column=0, columnspan=2, pady=3)

        self.printer_status = ttk.Label(printer_frame, text="Disconnected", foreground="red", font=("Arial", 8))
        self.printer_status.grid(row=3, column=0, columnspan=2)

        # Faultier Device Connection
        faultier_frame = ttk.LabelFrame(frame, text="Faultier Device", padding=5)
        faultier_frame.pack(fill=tk.X, pady=3)

        self.faultier_connect_btn = ttk.Button(faultier_frame, text="Connect Faultier", command=self.connect_faultier)
        self.faultier_connect_btn.pack(fill=tk.X, pady=3)

        self.faultier_status = ttk.Label(faultier_frame, text="Not Connected", foreground="gray", font=("Arial", 8))
        self.faultier_status.pack()

        # Power cycle button
        self.power_cycle_btn = ttk.Button(faultier_frame, text="Power Cycle Target",
                                          command=self.power_cycle_target, state=tk.DISABLED)
        self.power_cycle_btn.pack(fill=tk.X, pady=3)

        # Target Device Connection
        target_frame = ttk.LabelFrame(frame, text="Target Device Serial", padding=5)
        target_frame.pack(fill=tk.X, pady=3)

        ttk.Label(target_frame, text="Port:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=1)
        ttk.Entry(target_frame, textvariable=self.target_port, width=15, font=("Arial", 8)).grid(row=0, column=1, pady=1)

        ttk.Label(target_frame, text="Baud:", font=("Arial", 8)).grid(row=1, column=0, sticky=tk.W, pady=1)
        ttk.Entry(target_frame, textvariable=self.target_baudrate, width=15, font=("Arial", 8)).grid(row=1, column=1, pady=1)

        self.target_connect_btn = ttk.Button(target_frame, text="Connect", command=self.connect_target)
        self.target_connect_btn.grid(row=2, column=0, columnspan=2, pady=3)

        self.target_status = ttk.Label(target_frame, text="Not Connected", foreground="gray", font=("Arial", 8))
        self.target_status.grid(row=3, column=0, columnspan=2)

    def create_faultier_config_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Faultier Configuration", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # Glitch timing parameters
        timing_frame = ttk.LabelFrame(frame, text="Glitch Timing", padding=5)
        timing_frame.pack(fill=tk.X, pady=3)

        ttk.Label(timing_frame, text="Delay (ns):", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=1)
        ttk.Entry(timing_frame, textvariable=self.glitch_delay, width=10, font=("Arial", 8)).grid(row=0, column=1, pady=1)

        ttk.Label(timing_frame, text="Pulse (ns):", font=("Arial", 8)).grid(row=1, column=0, sticky=tk.W, pady=1)
        ttk.Entry(timing_frame, textvariable=self.glitch_pulse, width=10, font=("Arial", 8)).grid(row=1, column=1, pady=1)

        ttk.Button(timing_frame, text="Apply Timing", command=self.apply_glitch_timing).grid(row=2, column=0, columnspan=2, pady=3)

        # Trigger configuration
        trigger_frame = ttk.LabelFrame(frame, text="Trigger Settings", padding=5)
        trigger_frame.pack(fill=tk.X, pady=3)

        ttk.Label(trigger_frame, text="Type:", font=("Arial", 8)).grid(row=0, column=0, sticky=tk.W, pady=1)
        trigger_combo = ttk.Combobox(trigger_frame, textvariable=self.trigger_type, width=15, font=("Arial", 8),
                                     values=["NONE", "LOW", "HIGH", "RISING_EDGE", "FALLING_EDGE",
                                            "PULSE_POSITIVE", "PULSE_NEGATIVE"])
        trigger_combo.grid(row=0, column=1, pady=1)

        ttk.Label(trigger_frame, text="Source:", font=("Arial", 8)).grid(row=1, column=0, sticky=tk.W, pady=1)
        source_combo = ttk.Combobox(trigger_frame, textvariable=self.trigger_source, width=15, font=("Arial", 8),
                                    values=["EXT0", "EXT1"])
        source_combo.grid(row=1, column=1, pady=1)

        ttk.Label(trigger_frame, text="Output:", font=("Arial", 8)).grid(row=2, column=0, sticky=tk.W, pady=1)
        output_combo = ttk.Combobox(trigger_frame, textvariable=self.glitch_output, width=15, font=("Arial", 8),
                                    values=["CROWBAR", "MUX0", "MUX1", "MUX2", "EXT0", "EXT1", "NONE"])
        output_combo.grid(row=2, column=1, pady=1)

        ttk.Button(trigger_frame, text="Apply Trigger Config", command=self.apply_trigger_config).grid(row=3, column=0, columnspan=2, pady=3)

    def create_target_status_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Target Device Status", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # State indicator
        state_frame = ttk.Frame(frame)
        state_frame.pack(fill=tk.X, pady=3)

        ttk.Label(state_frame, text="State:", font=("Arial", 9, "bold")).pack(side=tk.LEFT)
        self.state_indicator = ttk.Label(state_frame, text="UNKNOWN", font=("Arial", 9, "bold"),
                                         foreground="gray", background="lightgray", padding=5)
        self.state_indicator.pack(side=tk.LEFT, padx=10)

        # Current attempt info
        attempt_frame = ttk.Frame(frame)
        attempt_frame.pack(fill=tk.X, pady=3)

        ttk.Label(attempt_frame, text="Current Attempt:", font=("Arial", 8)).pack(side=tk.LEFT)
        self.attempt_label = ttk.Label(attempt_frame, text="N/A", font=("Arial", 8))
        self.attempt_label.pack(side=tk.LEFT, padx=5)

        # Heartbeat info
        hb_frame = ttk.Frame(frame)
        hb_frame.pack(fill=tk.X, pady=3)

        ttk.Label(hb_frame, text="Heartbeats:", font=("Arial", 8)).pack(side=tk.LEFT)
        self.heartbeat_label = ttk.Label(hb_frame, text="0", font=("Arial", 8))
        self.heartbeat_label.pack(side=tk.LEFT, padx=5)

        # Power cycles
        pc_frame = ttk.Frame(frame)
        pc_frame.pack(fill=tk.X, pady=3)

        ttk.Label(pc_frame, text="Power Cycles:", font=("Arial", 8)).pack(side=tk.LEFT)
        self.power_cycle_label = ttk.Label(pc_frame, text="0", font=("Arial", 8))
        self.power_cycle_label.pack(side=tk.LEFT, padx=5)

    def create_manual_control_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Manual Position Control", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        # Position display
        pos_frame = ttk.Frame(frame)
        pos_frame.pack(fill=tk.X, pady=3)

        self.pos_label = ttk.Label(pos_frame, text="Position: X=0.00 Y=0.00 Z=0.00",
                                   font=("Arial", 9, "bold"))
        self.pos_label.pack()

        # Movement step size
        step_frame = ttk.Frame(frame)
        step_frame.pack(fill=tk.X, pady=3)

        ttk.Label(step_frame, text="Step (mm):", font=("Arial", 8)).pack(side=tk.LEFT)
        ttk.Entry(step_frame, textvariable=self.move_step, width=8, font=("Arial", 8)).pack(side=tk.LEFT, padx=5)

        # XY control pad
        xy_frame = ttk.Frame(frame)
        xy_frame.pack(pady=3)

        ttk.Button(xy_frame, text="Y+", width=6,
                   command=lambda: self.manual_move('Y', 1)).grid(row=0, column=1, padx=1, pady=1)

        ttk.Button(xy_frame, text="X-", width=6,
                   command=lambda: self.manual_move('X', -1)).grid(row=1, column=0, padx=1, pady=1)
        ttk.Button(xy_frame, text="Home", width=6,
                   command=self.home_printer).grid(row=1, column=1, padx=1, pady=1)
        ttk.Button(xy_frame, text="X+", width=6,
                   command=lambda: self.manual_move('X', 1)).grid(row=1, column=2, padx=1, pady=1)

        ttk.Button(xy_frame, text="Y-", width=6,
                   command=lambda: self.manual_move('Y', -1)).grid(row=2, column=1, padx=1, pady=1)

        # Z controls
        z_frame = ttk.Frame(frame)
        z_frame.pack(pady=3)

        ttk.Button(z_frame, text="Z+", width=6,
                   command=lambda: self.manual_move('Z', 1)).pack(side=tk.LEFT, padx=1)
        ttk.Button(z_frame, text="Z-", width=6,
                   command=lambda: self.manual_move('Z', -1)).pack(side=tk.LEFT, padx=1)

        # Chip corner setup frame
        corner_frame = ttk.LabelFrame(frame, text="Chip Area Setup", padding=8)
        corner_frame.pack(fill=tk.X, pady=5)

        self.set_origin_btn = ttk.Button(corner_frame,
                                         text="1. Set Bottom-Left Origin",
                                         command=self.set_chip_origin,
                                         style="Accent.TButton")
        self.set_origin_btn.pack(fill=tk.X, pady=2)

        self.origin_status = ttk.Label(corner_frame, text="Origin not set", foreground="red", font=("Arial", 8))
        self.origin_status.pack(pady=1)

        self.set_top_right_btn = ttk.Button(corner_frame,
                                            text="2. Mark Top-Right Corner",
                                            command=self.set_top_right_corner,
                                            state=tk.DISABLED,
                                            style="Accent.TButton")
        self.set_top_right_btn.pack(fill=tk.X, pady=2)

        self.top_right_status = ttk.Label(corner_frame, text="Top-right not set", foreground="red", font=("Arial", 8))
        self.top_right_status.pack(pady=1)

        self.area_info = ttk.Label(corner_frame, text="Scan Area: Not configured",
                                   font=("Arial", 8, "italic"))
        self.area_info.pack(pady=3)

    def create_scan_config_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Scan Configuration", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        config_items = [
            ("Probe Diameter (mm):", self.probe_diameter),
            ("Step Size (mm):", self.step_size),
            ("Z Increment (mm):", self.z_increment),
            ("Max Z Height (mm):", self.max_z_height),
            ("Pulses per Location:", self.pulses_per_location)
        ]

        for i, (label, var) in enumerate(config_items):
            ttk.Label(frame, text=label, font=("Arial", 8)).grid(row=i, column=0, sticky=tk.W, pady=1)
            ttk.Entry(frame, textvariable=var, width=12, font=("Arial", 8)).grid(row=i, column=1, pady=1, padx=3)

        self.grid_info = ttk.Label(frame, text="Grid: Configure chip area first", font=("Arial", 8))
        self.grid_info.grid(row=len(config_items), column=0, columnspan=2, pady=3)

        ttk.Button(frame, text="Calculate Grid",
                   command=self.update_grid_info).grid(row=len(config_items)+1, column=0, columnspan=2, pady=2)

    def create_scan_control_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Scan Control", padding=8)
        frame.pack(fill=tk.X, padx=5, pady=5)

        self.start_scan_btn = ttk.Button(frame, text="Start EMFI Scan",
                                         command=self.start_scan,
                                         style="Accent.TButton",
                                         state=tk.DISABLED)
        self.start_scan_btn.pack(fill=tk.X, pady=3)

        self.stop_scan_btn = ttk.Button(frame, text="Stop Scan",
                                        command=self.stop_scan,
                                        state=tk.DISABLED)
        self.stop_scan_btn.pack(fill=tk.X, pady=3)

        self.reset_data_btn = ttk.Button(frame, text="Reset Data",
                                         command=self.reset_data)
        self.reset_data_btn.pack(fill=tk.X, pady=3)

    def create_status_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Scan Statistics", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.stats_text = tk.Text(frame, height=12, width=35, state=tk.DISABLED, font=("Courier", 8))
        self.stats_text.pack(fill=tk.BOTH, expand=True)

        self.update_statistics()

    def create_visualization_section(self, parent):
        # Create notebook for tabs
        self.viz_notebook = ttk.Notebook(parent)
        self.viz_notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Target Serial Monitor
        monitor_frame = ttk.Frame(self.viz_notebook)
        self.viz_notebook.add(monitor_frame, text="Target Monitor")

        # Serial monitor controls
        monitor_controls = ttk.Frame(monitor_frame)
        monitor_controls.pack(fill=tk.X, padx=5, pady=5)

        self.monitor_btn = ttk.Button(monitor_controls, text="Start Monitor",
                                      command=self.toggle_serial_monitor)
        self.monitor_btn.pack(side=tk.LEFT, padx=5)

        ttk.Button(monitor_controls, text="Clear",
                   command=self.clear_serial_monitor).pack(side=tk.LEFT, padx=5)

        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(monitor_controls, text="Auto-scroll",
                       variable=self.autoscroll_var).pack(side=tk.LEFT, padx=5)

        # Serial monitor display
        monitor_display_frame = ttk.Frame(monitor_frame)
        monitor_display_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.serial_monitor = scrolledtext.ScrolledText(
            monitor_display_frame,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#1e1e1e",
            fg="#00ff00",
            insertbackground="white"
        )
        self.serial_monitor.pack(fill=tk.BOTH, expand=True)

        # Configure tags for message highlighting
        self.serial_monitor.tag_config("timestamp", foreground="#888888")
        self.serial_monitor.tag_config("system", foreground="#00aaff")
        self.serial_monitor.tag_config("error", foreground="#ff0000")
        self.serial_monitor.tag_config("success", foreground="#00ff00", font=("Courier", 9, "bold"))
        self.serial_monitor.tag_config("heartbeat", foreground="#ffaa00")
        self.serial_monitor.tag_config("attempt", foreground="#aa00ff")

        # Add timestamp option
        timestamp_frame = ttk.Frame(monitor_frame)
        timestamp_frame.pack(fill=tk.X, padx=5, pady=5)

        self.timestamp_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(timestamp_frame, text="Show timestamps",
                       variable=self.timestamp_var).pack(side=tk.LEFT)

        # Tab 2: Success Rate Graph
        graph_frame = ttk.Frame(self.viz_notebook)
        self.viz_notebook.add(graph_frame, text="Success Rate Graph")

        self.fig = Figure(figsize=(7, 6))
        self.ax_success = self.fig.add_subplot(111)
        self.ax_success.set_title("Glitch Success Rate by Location", fontsize=10)
        self.ax_success.set_xlabel("Location Index", fontsize=8)
        self.ax_success.set_ylabel("Success Rate (%)", fontsize=8)
        self.ax_success.tick_params(labelsize=7)
        self.ax_success.grid(True, alpha=0.3)

        self.fig.tight_layout(pad=2.0)

        self.canvas = FigureCanvasTkAgg(self.fig, graph_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # Tab 3: Controller Log
        log_frame = ttk.Frame(self.viz_notebook)
        self.viz_notebook.add(log_frame, text="Controller Log")

        self.controller_log = scrolledtext.ScrolledText(
            log_frame,
            wrap=tk.WORD,
            font=("Courier", 9),
            bg="#1a1a2e",
            fg="#eee",
            insertbackground="white"
        )
        self.controller_log.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

    # ======================== CALLBACKS ========================

    def on_target_state_change(self, new_state: TargetState):
        """Callback when target state changes"""
        self.root.after(0, self.update_state_indicator, new_state)

    def on_controller_message(self, message: str):
        """Callback for controller log messages"""
        self.root.after(0, self.append_to_controller_log, message)

    def update_state_indicator(self, state: TargetState):
        """Update the state indicator widget"""
        state_colors = {
            TargetState.UNKNOWN: ("gray", "lightgray"),
            TargetState.READY: ("white", "green"),
            TargetState.ATTEMPT_STARTED: ("black", "yellow"),
            TargetState.RUNNING: ("white", "blue"),
            TargetState.GLITCH_SUCCESS: ("black", "lime"),
            TargetState.CRASHED: ("white", "red"),
            TargetState.POWER_CYCLING: ("black", "orange"),
        }

        fg, bg = state_colors.get(state, ("gray", "lightgray"))
        self.state_indicator.config(text=state.name, foreground=fg, background=bg)

    def append_to_controller_log(self, message: str):
        """Append message to controller log"""
        try:
            self.controller_log.config(state=tk.NORMAL)
            timestamp = time.strftime("[%H:%M:%S] ")
            self.controller_log.insert(tk.END, timestamp, "timestamp")
            self.controller_log.insert(tk.END, message + "\n")
            self.controller_log.see(tk.END)
            self.controller_log.config(state=tk.DISABLED)
        except:
            pass

    # ======================== FAULTIER HANDLERS ========================

    def connect_faultier(self):
        if not self.controller.faultier_connected:
            success, msg = self.controller.connect_faultier()
            if success:
                self.faultier_status.config(text="Connected", foreground="green")
                self.faultier_connect_btn.config(text="Disconnect")
                self.power_cycle_btn.config(state=tk.NORMAL)
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Connection Error", msg)
        else:
            success, msg = self.controller.disconnect_faultier()
            self.faultier_status.config(text="Not Connected", foreground="gray")
            self.faultier_connect_btn.config(text="Connect Faultier")
            self.power_cycle_btn.config(state=tk.DISABLED)

    def apply_glitch_timing(self):
        success, msg = self.controller.set_glitch_parameters(
            self.glitch_delay.get(),
            self.glitch_pulse.get()
        )
        if success:
            self.append_to_controller_log(f"Timing updated: delay={self.glitch_delay.get()}ns, pulse={self.glitch_pulse.get()}ns")
        else:
            messagebox.showerror("Error", msg)

    def apply_trigger_config(self):
        if not self.controller.faultier_connected:
            messagebox.showwarning("Not Connected", "Please connect Faultier first")
            return

        success, msg = self.controller.configure_faultier_trigger(
            trigger_type=self.trigger_type.get(),
            trigger_source=self.trigger_source.get(),
            glitch_output=self.glitch_output.get()
        )
        if success:
            self.append_to_controller_log(msg)
            messagebox.showinfo("Success", msg)
        else:
            messagebox.showerror("Error", msg)

    def power_cycle_target(self):
        if not self.controller.faultier_connected:
            messagebox.showwarning("Not Connected", "Faultier not connected")
            return

        if messagebox.askyesno("Power Cycle", "Power cycle the target device?"):
            def do_power_cycle():
                success, msg = self.controller.power_cycle_target()
                self.root.after(0, lambda: self.append_to_controller_log(msg))
                if not success:
                    self.root.after(0, lambda: messagebox.showerror("Error", msg))

            threading.Thread(target=do_power_cycle, daemon=True).start()

    # ======================== SERIAL MONITOR ========================

    def toggle_serial_monitor(self):
        if not self.monitor_running:
            if not self.controller.target_connected:
                messagebox.showwarning("Not Connected",
                                     "Please connect to target device first")
                return
            self.start_serial_monitor()
        else:
            self.stop_serial_monitor()

    def start_serial_monitor(self):
        self.monitor_running = True
        self.monitor_btn.config(text="Stop Monitor")
        self.append_to_monitor("=== Serial Monitor Started ===\n", "system")

        self.monitor_thread = threading.Thread(target=self.serial_monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_serial_monitor(self):
        self.monitor_running = False
        self.monitor_btn.config(text="Start Monitor")
        self.append_to_monitor("=== Serial Monitor Stopped ===\n", "system")

    def serial_monitor_loop(self):
        """Continuously read from target serial response queue"""
        while self.monitor_running:
            try:
                # Read from the controller's response queue
                line = self.controller._read_target_line(timeout=0.1)
                if line:
                    # Determine message type for highlighting
                    msg_type = "data"
                    if "SUCCESS" in line:
                        msg_type = "success"
                    elif "HB:" in line:
                        msg_type = "heartbeat"
                    elif "ATTEMPT:" in line:
                        msg_type = "attempt"
                    elif "ERROR" in line or "CRASH" in line:
                        msg_type = "error"

                    self.root.after(0, self.append_to_monitor, line + "\n", msg_type)

            except Exception as e:
                self.root.after(0, self.append_to_monitor,
                              f"[ERROR] {str(e)}\n", "error")
                time.sleep(0.5)

    def append_to_monitor(self, text, msg_type="data"):
        """Append text to serial monitor with formatting"""
        try:
            self.serial_monitor.config(state=tk.NORMAL)

            if self.timestamp_var.get() and msg_type not in ("system",):
                timestamp = time.strftime("[%H:%M:%S] ")
                self.serial_monitor.insert(tk.END, timestamp, "timestamp")

            self.serial_monitor.insert(tk.END, text, msg_type)

            if self.autoscroll_var.get():
                self.serial_monitor.see(tk.END)

            self.serial_monitor.config(state=tk.DISABLED)
        except:
            pass

    def clear_serial_monitor(self):
        self.serial_monitor.config(state=tk.NORMAL)
        self.serial_monitor.delete(1.0, tk.END)
        self.serial_monitor.config(state=tk.DISABLED)

    # ======================== CONNECTION HANDLERS ========================

    def connect_printer(self):
        if not self.controller.printer_connected:
            success, msg = self.controller.connect_printer(
                self.printer_port.get(),
                self.printer_baudrate.get()
            )
            if success:
                self.printer_status.config(text="Connected", foreground="green")
                self.printer_connect_btn.config(text="Disconnect")
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Connection Error", msg)
        else:
            success, msg = self.controller.disconnect_printer()
            self.printer_status.config(text="Disconnected", foreground="red")
            self.printer_connect_btn.config(text="Connect")

    def connect_target(self):
        if not self.controller.target_connected:
            success, msg = self.controller.connect_target(
                self.target_port.get(),
                self.target_baudrate.get()
            )
            if success:
                self.target_status.config(text="Connected", foreground="green")
                self.target_connect_btn.config(text="Disconnect")
                messagebox.showinfo("Success", msg)
            else:
                messagebox.showerror("Connection Error", msg)
        else:
            success, msg = self.controller.disconnect_target()
            self.target_status.config(text="Not Connected", foreground="gray")
            self.target_connect_btn.config(text="Connect")

    # ======================== MOVEMENT HANDLERS ========================

    def manual_move(self, axis, direction):
        if not self.controller.printer_connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return

        distance = self.move_step.get() * direction
        success, msg = self.controller.move_relative(axis, distance)

        if success:
            self.update_position_display()
        else:
            messagebox.showerror("Movement Error", msg)

    def home_printer(self):
        if not self.controller.printer_connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return

        if messagebox.askyesno("Home Printer", "Home all axes? This will move the printer."):
            success, msg = self.controller.home_all_axes()
            if success:
                self.update_position_display()
            else:
                messagebox.showerror("Homing Error", msg)

    def set_chip_origin(self):
        if not self.controller.printer_connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return

        if messagebox.askyesno("Set Origin",
                               "Set current position as chip origin (0,0,0)?\n\n"
                               "Make sure the probe is at the BOTTOM-LEFT corner\n"
                               "of the chip and Z is at the chip surface."):
            success, msg = self.controller.set_origin()
            if success:
                self.origin_status.config(text="Origin set at (0, 0, 0)", foreground="green")
                self.set_top_right_btn.config(state=tk.NORMAL)
                self.update_position_display()
                self.update_area_info()
                messagebox.showinfo("Success", "Origin set! Now move probe to TOP-RIGHT corner and mark it.")
            else:
                messagebox.showerror("Error", msg)

    def set_top_right_corner(self):
        if not self.controller.printer_connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return

        if messagebox.askyesno("Set Top-Right Corner",
                               f"Mark current position as top-right corner?\n\n"
                               f"Current position:\n"
                               f"X: {self.controller.current_x:.2f} mm\n"
                               f"Y: {self.controller.current_y:.2f} mm\n"
                               f"Z: {self.controller.current_z:.2f} mm\n\n"
                               f"This will define the scan area."):
            success, msg = self.controller.set_top_right_corner()
            if success:
                self.top_right_status.config(
                    text=f"Top-right set at ({self.controller.top_right_x:.2f}, {self.controller.top_right_y:.2f})",
                    foreground="green"
                )
                self.start_scan_btn.config(state=tk.NORMAL)
                self.update_area_info()
                self.update_grid_info()
                messagebox.showinfo("Success",
                                   f"Top-right corner marked!\n\n"
                                   f"Scan area: {self.controller.top_right_x:.2f} x {self.controller.top_right_y:.2f} mm\n\n"
                                   f"You can now configure and start the scan.")
            else:
                messagebox.showerror("Error", msg)

    def update_position_display(self):
        self.pos_label.config(
            text=f"Position: X={self.controller.current_x:.2f} Y={self.controller.current_y:.2f} Z={self.controller.current_z:.2f}"
        )

    def update_area_info(self):
        if self.controller.origin_set and self.controller.top_right_set:
            width = self.controller.top_right_x
            height = self.controller.top_right_y
            self.area_info.config(
                text=f"Scan Area: {width:.2f} mm x {height:.2f} mm",
                foreground="green"
            )
        elif self.controller.origin_set:
            self.area_info.config(
                text="Scan Area: Origin set, waiting for top-right corner",
                foreground="orange"
            )
        else:
            self.area_info.config(
                text="Scan Area: Not configured",
                foreground="red"
            )

    def update_grid_info(self):
        grid = self.controller.calculate_scan_grid(
            self.step_size.get(),
            self.z_increment.get(),
            self.max_z_height.get()
        )

        if grid:
            total_pulses = grid['total_points'] * self.pulses_per_location.get()
            self.grid_info.config(
                text=f"Grid: {grid['x_steps']} x {grid['y_steps']} x {grid['z_steps']} = {grid['total_points']} locations\n"
                     f"Total EMFI pulses: {total_pulses}"
            )
        else:
            self.grid_info.config(text="Grid: Configure chip area first")

    # ======================== SCAN HANDLERS ========================

    def start_scan(self):
        if not self.controller.printer_connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return

        if not self.controller.origin_set or not self.controller.top_right_set:
            messagebox.showwarning("Setup Incomplete",
                                  "Please set both origin and top-right corner first!")
            return

        grid = self.controller.calculate_scan_grid(
            self.step_size.get(),
            self.z_increment.get(),
            self.max_z_height.get()
        )

        total_pulses = grid['total_points'] * self.pulses_per_location.get()

        faultier_status = "Connected" if self.controller.faultier_connected else "NOT CONNECTED (simulated results)"
        target_status = "Connected" if self.controller.target_connected else "NOT CONNECTED"

        if not messagebox.askyesno("Start Scan",
                                    f"Start EMFI scan?\n\n"
                                    f"Scan area: {self.controller.top_right_x:.2f} x {self.controller.top_right_y:.2f} mm\n"
                                    f"Grid: {grid['x_steps']} x {grid['y_steps']} x {grid['z_steps']}\n"
                                    f"Total locations: {grid['total_points']}\n"
                                    f"Total EMFI pulses: {total_pulses}\n\n"
                                    f"Faultier: {faultier_status}\n"
                                    f"Target: {target_status}"):
            return

        self.start_scan_btn.config(state=tk.DISABLED)
        self.stop_scan_btn.config(state=tk.NORMAL)

        # Apply current timing settings
        self.controller.set_glitch_parameters(self.glitch_delay.get(), self.glitch_pulse.get())

        self.scan_thread = threading.Thread(target=self.run_scan_thread, daemon=True)
        self.scan_thread.start()

    def run_scan_thread(self):
        """Run scan in background thread"""
        def progress_callback(current, total, x, y, z, location):
            self.root.after(0, self.update_position_display)
            self.root.after(0, self.update_visualization)
            self.root.after(0, self.update_statistics)

        success, msg = self.controller.run_scan(
            self.step_size.get(),
            self.z_increment.get(),
            self.max_z_height.get(),
            self.pulses_per_location.get(),
            progress_callback
        )

        self.root.after(0, lambda: self.start_scan_btn.config(state=tk.NORMAL))
        self.root.after(0, lambda: self.stop_scan_btn.config(state=tk.DISABLED))

        if success:
            self.root.after(0, self.show_heatmaps_and_recommendation)
        else:
            self.root.after(0, lambda: messagebox.showerror("Scan Error", msg))

    def stop_scan(self):
        self.controller.stop_scan()
        self.start_scan_btn.config(state=tk.NORMAL)
        self.stop_scan_btn.config(state=tk.DISABLED)

    def reset_data(self):
        if messagebox.askyesno("Reset Data", "Clear all scan data and statistics?"):
            self.controller.reset_data()

            self.ax_success.clear()
            self.ax_success.set_xlabel("Location Index", fontsize=8)
            self.ax_success.set_ylabel("Success Rate (%)", fontsize=8)
            self.ax_success.set_title("Glitch Success Rate by Location", fontsize=10)
            self.ax_success.grid(True, alpha=0.3)
            self.ax_success.set_ylim([0, 100])

            self.fig.tight_layout(pad=2.0)
            self.canvas.draw()

            self.update_statistics()

    # ======================== PERIODIC UPDATES ========================

    def update_ui_periodically(self):
        """Update UI elements periodically"""
        # Update heartbeat and attempt counters
        self.heartbeat_label.config(text=str(self.controller.heartbeat_count))
        self.attempt_label.config(text=str(self.controller.current_attempt_number))
        self.power_cycle_label.config(text=str(self.controller.total_power_cycles))

        # Schedule next update
        self.root.after(100, self.update_ui_periodically)

    # ======================== VISUALIZATION ========================

    def update_visualization(self):
        if not self.controller.scan_locations:
            return

        self.ax_success.clear()

        success_rates = [loc.glitch_rate * 100 for loc in self.controller.scan_locations]

        self.ax_success.plot(range(len(success_rates)), success_rates, 'g-', linewidth=1, label='Glitch Rate')
        self.ax_success.fill_between(range(len(success_rates)), success_rates, alpha=0.3)
        self.ax_success.set_xlabel("Location Index", fontsize=8)
        self.ax_success.set_ylabel("Success Rate (%)", fontsize=8)
        self.ax_success.set_title("Glitch Success Rate by Location", fontsize=10)
        self.ax_success.grid(True, alpha=0.3)
        self.ax_success.set_ylim([0, 100])
        self.ax_success.legend(fontsize=7)

        self.fig.tight_layout(pad=2.0)
        self.canvas.draw()

    def update_statistics(self):
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)

        stats = self.controller.get_statistics()

        success_rate = stats['glitch_rate'] * 100
        crash_rate = stats['crash_rate'] * 100

        area_info = ""
        if self.controller.origin_set and self.controller.top_right_set:
            area_info = f"\nScan Area: {self.controller.top_right_x:.2f} x {self.controller.top_right_y:.2f} mm"

        stats_text = f"""
Scan Progress:
--------------
Locations Scanned: {stats['locations_scanned']}
Total EMFI Pulses: {stats['total_attempts']}{area_info}

Results:
  Glitches: {stats['total_glitches']}
  Crashes:  {stats['total_crashes']}
  Timeouts: {stats['total_timeouts']}
  Resets:   {stats['total_resets']}
  Nothing:  {stats['total_nothing']}

Rates:
  Glitch Rate: {success_rate:.2f}%
  Crash Rate:  {crash_rate:.2f}%

Recovery:
  Power Cycles: {stats['total_power_cycles']}

Current Position:
  X: {self.controller.current_x:.2f} mm
  Y: {self.controller.current_y:.2f} mm
  Z: {self.controller.current_z:.2f} mm

Status: {'SCANNING' if self.controller.scanning else 'IDLE'}
Target: {self.controller.target_state.name}
        """

        self.stats_text.insert(1.0, stats_text)
        self.stats_text.config(state=tk.DISABLED)

    # ======================== RESULTS DISPLAY ========================

    def show_heatmaps_and_recommendation(self):
        if not self.controller.scan_locations:
            messagebox.showwarning("No Data", "No scan data available")
            return

        # Group data by Z layer
        z_layers = {}
        for loc in self.controller.scan_locations:
            z = round(loc.z, 3)
            if z not in z_layers:
                z_layers[z] = []
            z_layers[z].append(loc)

        heatmap_window = tk.Toplevel(self.root)
        heatmap_window.title("EMFI Scan Results - Heatmaps and Recommendation")
        heatmap_window.geometry("1200x800")

        notebook = ttk.Notebook(heatmap_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create recommendation tab
        optimal_location = self.controller.find_optimal_glitch_location()

        if optimal_location:
            rec_frame = ttk.Frame(notebook)
            notebook.add(rec_frame, text="Recommendation")

            rec_text = tk.Text(rec_frame, font=("Courier", 11), wrap=tk.WORD)
            rec_scrollbar = ttk.Scrollbar(rec_frame, orient=tk.VERTICAL, command=rec_text.yview)
            rec_text.configure(yscrollcommand=rec_scrollbar.set)

            rec_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
            rec_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)

            stats = self.controller.get_statistics()

            recommendation = f"""
OPTIMAL GLITCH LOCATION
=======================

Position:
  X: {optimal_location['x']:.3f} mm
  Y: {optimal_location['y']:.3f} mm
  Z: {optimal_location['z']:.3f} mm

Results (from {optimal_location['total']} pulses):
  Glitches: {optimal_location['glitch']} ({optimal_location['glitch_rate']*100:.1f}%)
  Crashes:  {optimal_location['crash']} ({optimal_location['crash_rate']*100:.1f}%)
  Nothing:  {optimal_location['nothing']} ({optimal_location['nothing']/optimal_location['total']*100:.1f}%)

Score: {optimal_location['score']:.2f}

---------------------------------------------------

Summary Statistics:
  Scan area: {self.controller.top_right_x:.2f} x {self.controller.top_right_y:.2f} mm
  Total locations scanned: {stats['locations_scanned']}
  Total EMFI pulses: {stats['total_attempts']}
  Overall glitch rate: {stats['glitch_rate']*100:.2f}%
  Overall crash rate: {stats['crash_rate']*100:.2f}%
  Total power cycles: {stats['total_power_cycles']}

---------------------------------------------------

NEXT STEPS:

1. Move probe to the optimal position shown above
2. Perform additional targeted testing at this location
3. Fine-tune Z-height around {optimal_location['z']:.3f} mm for best results
4. Consider testing neighboring locations for consistency
            """

            rec_text.insert(1.0, recommendation)
            rec_text.config(state=tk.DISABLED)

        # Create Z-layer heatmap tabs
        for z_height in sorted(z_layers.keys()):
            layer_data = z_layers[z_height]

            frame = ttk.Frame(notebook)
            notebook.add(frame, text=f"Z = {z_height:.3f} mm")

            fig = Figure(figsize=(10, 8))

            ax1 = fig.add_subplot(211)
            self.plot_heatmap(ax1, layer_data, 'glitch', f'Glitch Success Rate - Z = {z_height:.3f} mm')

            ax2 = fig.add_subplot(212)
            self.plot_heatmap(ax2, layer_data, 'crash', f'Crash Rate - Z = {z_height:.3f} mm')

            fig.tight_layout()

            canvas = FigureCanvasTkAgg(fig, frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        notebook.select(0)

        stats = self.controller.get_statistics()
        messagebox.showinfo("Scan Complete",
                           f"EMFI scan completed!\n\n"
                           f"Total glitches: {stats['total_glitches']}\n"
                           f"Total crashes: {stats['total_crashes']}\n"
                           f"Glitch rate: {stats['glitch_rate']*100:.2f}%\n"
                           f"Power cycles: {stats['total_power_cycles']}\n\n"
                           f"Check the heatmaps and recommendation tab!")

    def plot_heatmap(self, ax, layer_data, data_type, title):
        x_coords = [d.x for d in layer_data]
        y_coords = [d.y for d in layer_data]

        x_unique = sorted(set(x_coords))
        y_unique = sorted(set(y_coords))

        grid = np.zeros((len(y_unique), len(x_unique)))

        for d in layer_data:
            x_idx = x_unique.index(d.x)
            y_idx = y_unique.index(d.y)
            if data_type == 'glitch':
                grid[y_idx, x_idx] = d.glitch_rate * 100
            elif data_type == 'crash':
                grid[y_idx, x_idx] = d.crash_rate * 100

        im = ax.imshow(grid, cmap='RdYlGn', interpolation='nearest', aspect='auto',
                      extent=[min(x_unique), max(x_unique), min(y_unique), max(y_unique)],
                      origin='lower', vmin=0, vmax=100)

        ax.set_xlabel("X Position (mm)")
        ax.set_ylabel("Y Position (mm)")
        ax.set_title(title)

        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Rate (%)')

        ax.grid(True, alpha=0.3, color='black', linewidth=0.5)

    # ======================== CLEANUP ========================

    def on_closing(self):
        if self.controller.scanning:
            if not messagebox.askyesno("Scan in Progress",
                                       "Scan is running. Stop and exit?"):
                return
            self.controller.stop_scan()

        if self.monitor_running:
            self.stop_serial_monitor()

        self.controller.cleanup()
        self.root.destroy()


def main():
    root = tk.Tk()

    style = ttk.Style()
    style.theme_use('clam')

    app = EMFIFaultierGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()


if __name__ == "__main__":
    main()
