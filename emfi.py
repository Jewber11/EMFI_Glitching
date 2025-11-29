import serial
import time
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure
import tkinter as tk
from tkinter import ttk, messagebox
import threading

class EMFIScannerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("EMFI Scanner Control - Ender 3 S1 Pro")
        self.root.geometry("3000x2500")
        
        # Configuration parameters
        self.chip_width = tk.DoubleVar(value=10.0)
        self.chip_length = tk.DoubleVar(value=10.0)
        self.probe_diameter = tk.DoubleVar(value=2.0)
        self.step_size = tk.DoubleVar(value=1.0)
        self.z_increment = tk.DoubleVar(value=0.1)
        self.max_z_height = tk.DoubleVar(value=0.5)
        self.pulses_per_location = tk.IntVar(value=10)  # Number of EMFI pulses per location
        
        # Serial connection parameters
        self.port = tk.StringVar(value="/dev/ttyUSB0")
        self.baudrate = tk.IntVar(value=115200)
        self.ser = None
        self.connected = False
        
        # Current position tracking
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_z = 0.0
        
        # Scanning state
        self.scanning = False
        self.scan_thread = None
        self.total_glitches = 0
        self.total_crashes = 0  # Track crashes separately
        self.total_attempts = 0
        self.glitch_data = []  # List of (x, y, z, glitch_count, crash_count, total_pulses)
        
        # Movement step size for manual control
        self.move_step = tk.DoubleVar(value=1.0)
        
        # Build GUI
        self.create_widgets()
        
    def create_widgets(self):
        # Main container with two panes
        main_pane = tk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Left panel - Controls
        left_frame = ttk.Frame(main_pane)
        main_pane.add(left_frame, width=500)
        
        # Right panel - Visualization
        right_frame = ttk.Frame(main_pane)
        main_pane.add(right_frame)
        
        # Build left panel sections
        self.create_connection_section(left_frame)
        self.create_manual_control_section(left_frame)
        self.create_scan_config_section(left_frame)
        self.create_scan_control_section(left_frame)
        self.create_status_section(left_frame)
        
        # Build right panel - visualization
        self.create_visualization_section(right_frame)
        
    def create_connection_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Printer Connection", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        ttk.Label(frame, text="Port:").grid(row=0, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.port, width=20).grid(row=0, column=1, pady=2)
        
        ttk.Label(frame, text="Baudrate:").grid(row=1, column=0, sticky=tk.W, pady=2)
        ttk.Entry(frame, textvariable=self.baudrate, width=20).grid(row=1, column=1, pady=2)
        
        self.connect_btn = ttk.Button(frame, text="Connect", command=self.connect_printer)
        self.connect_btn.grid(row=2, column=0, columnspan=2, pady=5)
        
        self.connection_status = ttk.Label(frame, text="Disconnected", foreground="red")
        self.connection_status.grid(row=3, column=0, columnspan=2)
        
    def create_manual_control_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Manual Position Control", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        # Position display
        pos_frame = ttk.Frame(frame)
        pos_frame.pack(fill=tk.X, pady=5)
        
        self.pos_label = ttk.Label(pos_frame, text="Position: X=0.00 Y=0.00 Z=0.00", 
                                    font=("Arial", 10, "bold"))
        self.pos_label.pack()
        
        # Movement step size
        step_frame = ttk.Frame(frame)
        step_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(step_frame, text="Move Step (mm):").pack(side=tk.LEFT)
        ttk.Entry(step_frame, textvariable=self.move_step, width=10).pack(side=tk.LEFT, padx=5)
        
        # XY control pad
        xy_frame = ttk.Frame(frame)
        xy_frame.pack(pady=5)
        
        # Y+ button
        ttk.Button(xy_frame, text="Y+", width=8, 
                   command=lambda: self.manual_move('Y', 1)).grid(row=0, column=1, padx=2, pady=2)
        
        # X-, Home, X+ buttons
        ttk.Button(xy_frame, text="X-", width=8, 
                   command=lambda: self.manual_move('X', -1)).grid(row=1, column=0, padx=2, pady=2)
        ttk.Button(xy_frame, text="Home All", width=8, 
                   command=self.home_printer).grid(row=1, column=1, padx=2, pady=2)
        ttk.Button(xy_frame, text="X+", width=8, 
                   command=lambda: self.manual_move('X', 1)).grid(row=1, column=2, padx=2, pady=2)
        
        # Y- button
        ttk.Button(xy_frame, text="Y-", width=8, 
                   command=lambda: self.manual_move('Y', -1)).grid(row=2, column=1, padx=2, pady=2)
        
        # Z controls
        z_frame = ttk.Frame(frame)
        z_frame.pack(pady=5)
        
        ttk.Button(z_frame, text="Z+", width=8, 
                   command=lambda: self.manual_move('Z', 1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(z_frame, text="Z-", width=8, 
                   command=lambda: self.manual_move('Z', -1)).pack(side=tk.LEFT, padx=2)
        
        # Set origin button
        set_origin_frame = ttk.Frame(frame)
        set_origin_frame.pack(pady=10)
        
        self.set_origin_btn = ttk.Button(set_origin_frame, 
                                         text="Set Current Position as Chip Origin (0,0,0)", 
                                         command=self.set_chip_origin,
                                         style="Accent.TButton")
        self.set_origin_btn.pack()
        
    def create_scan_config_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Scan Configuration", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        config_items = [
            ("Chip Width (mm):", self.chip_width),
            ("Chip Length (mm):", self.chip_length),
            ("Probe Diameter (mm):", self.probe_diameter),
            ("Step Size (mm):", self.step_size),
            ("Z Increment (mm):", self.z_increment),
            ("Max Z Height (mm):", self.max_z_height),
            ("Pulses per Location:", self.pulses_per_location)
        ]
        
        for i, (label, var) in enumerate(config_items):
            ttk.Label(frame, text=label).grid(row=i, column=0, sticky=tk.W, pady=2)
            ttk.Entry(frame, textvariable=var, width=15).grid(row=i, column=1, pady=2, padx=5)
        
        # Calculate grid size
        self.grid_info = ttk.Label(frame, text="Grid: 0 x 0 x 0 = 0 points")
        self.grid_info.grid(row=len(config_items), column=0, columnspan=2, pady=5)
        
        ttk.Button(frame, text="Calculate Grid", 
                   command=self.update_grid_info).grid(row=len(config_items)+1, column=0, columnspan=2)
        
    def create_scan_control_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Scan Control", padding=10)
        frame.pack(fill=tk.X, padx=5, pady=5)
        
        self.start_scan_btn = ttk.Button(frame, text="Start EMFI Scan", 
                                         command=self.start_scan, 
                                         style="Accent.TButton")
        self.start_scan_btn.pack(fill=tk.X, pady=5)
        
        self.stop_scan_btn = ttk.Button(frame, text="Stop Scan", 
                                        command=self.stop_scan, 
                                        state=tk.DISABLED)
        self.stop_scan_btn.pack(fill=tk.X, pady=5)
        
        self.reset_data_btn = ttk.Button(frame, text="Reset Data", 
                                         command=self.reset_data)
        self.reset_data_btn.pack(fill=tk.X, pady=5)
        
    def create_status_section(self, parent):
        frame = ttk.LabelFrame(parent, text="Scan Statistics", padding=10)
        frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        self.stats_text = tk.Text(frame, height=8, width=40, state=tk.DISABLED)
        self.stats_text.pack(fill=tk.BOTH, expand=True)
        
        self.update_statistics()
        
    def create_visualization_section(self, parent):
        # Create matplotlib figure with two subplots
        self.fig = Figure(figsize=(10, 8))
        
        # Top plot - 3D probe position visualization
        self.ax_3d = self.fig.add_subplot(211, projection='3d')
        self.ax_3d.set_title("3D Probe Position")
        self.ax_3d.set_xlabel("X Position (mm)")
        self.ax_3d.set_ylabel("Y Position (mm)")
        self.ax_3d.set_zlabel("Z Height (mm)")
        
        # Bottom plot - Success rate by location
        self.ax_success = self.fig.add_subplot(212)
        self.ax_success.set_title("Glitch Success Rate by Location")
        self.ax_success.set_xlabel("Location Index")
        self.ax_success.set_ylabel("Success Rate (%)")
        self.ax_success.grid(True, alpha=0.3)
        
        self.fig.tight_layout()
        
        # Embed in tkinter
        self.canvas = FigureCanvasTkAgg(self.fig, parent)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
    def connect_printer(self):
        try:
            if not self.connected:
                self.ser = serial.Serial(self.port.get(), self.baudrate.get(), timeout=5)
                time.sleep(2)
                self.connected = True
                self.connection_status.config(text="Connected", foreground="green")
                self.connect_btn.config(text="Disconnect")
                
                # Initialize printer
                self.initialize_printer()
                messagebox.showinfo("Success", "Connected to printer successfully!")
            else:
                self.ser.close()
                self.connected = False
                self.connection_status.config(text="Disconnected", foreground="red")
                self.connect_btn.config(text="Connect")
        except Exception as e:
            messagebox.showerror("Connection Error", f"Failed to connect:\n{str(e)}")
            
    def initialize_printer(self):
        """Initialize printer settings"""
        self.send_gcode("M84 X Y Z S12000")
        self.send_gcode("G21")  # Millimeters
        self.send_gcode("G90")  # Absolute positioning
        self.send_gcode("M999")  # Ignore errors
        
    def send_gcode(self, command):
        """Send G-code command to printer"""
        if not self.connected:
            return None
            
        try:
            self.ser.write(str.encode(command + "\r\n"))
            time.sleep(0.05)
            
            response = ""
            start_time = time.time()
            while time.time() - start_time < 0.5:
                if self.ser.in_waiting:
                    response += self.ser.read(self.ser.in_waiting).decode('utf-8', errors='ignore')
                    break
                time.sleep(0.01)
                
            return response
        except Exception as e:
            print(f"Error sending G-code: {e}")
            return None
            
    def manual_move(self, axis, direction):
        """Move printer manually"""
        if not self.connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return
            
        distance = self.move_step.get() * direction
        
        self.send_gcode("G91")  # Relative positioning
        self.send_gcode(f"G1 {axis}{distance} F3000")
        self.send_gcode("M400")  # Wait for completion
        self.send_gcode("G90")  # Absolute positioning
        
        # Update position tracking
        if axis == 'X':
            self.current_x += distance
        elif axis == 'Y':
            self.current_y += distance
        elif axis == 'Z':
            self.current_z += distance
            
        self.update_position_display()
        
    def home_printer(self):
        """Home all axes"""
        if not self.connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return
            
        if messagebox.askyesno("Home Printer", "Home all axes? This will move the printer."):
            self.send_gcode("G28")
            self.send_gcode("M400")
            self.current_x = 0
            self.current_y = 0
            self.current_z = 0
            self.update_position_display()
            self.send_gcode("M999")
            
    def set_chip_origin(self):
        """Set current position as chip origin (0,0,0)"""
        if not self.connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return
            
        if messagebox.askyesno("Set Origin", 
                               "Set current position as chip origin (0,0,0)?\n\n"
                               "Make sure the probe is at the BOTTOM-LEFT corner\n"
                               "of the chip and Z is at the chip surface."):
            self.send_gcode("G92 X0 Y0 Z0")
            self.current_x = 0
            self.current_y = 0
            self.current_z = 0
            self.update_position_display()
            messagebox.showinfo("Success", "Origin set at current position!")
            
    def update_position_display(self):
        """Update position label"""
        self.pos_label.config(
            text=f"Position: X={self.current_x:.2f} Y={self.current_y:.2f} Z={self.current_z:.2f}"
        )
        
    def update_grid_info(self):
        """Calculate and display grid dimensions"""
        x_steps = int(self.chip_width.get() / self.step_size.get()) + 1
        y_steps = int(self.chip_length.get() / self.step_size.get()) + 1
        z_steps = int(self.max_z_height.get() / self.z_increment.get()) + 1
        total_points = x_steps * y_steps * z_steps
        total_pulses = total_points * self.pulses_per_location.get()
        
        self.grid_info.config(
            text=f"Grid: {x_steps} x {y_steps} x {z_steps} = {total_points} locations\n"
                 f"Total EMFI pulses: {total_pulses}"
        )
        
    def trigger_emfi(self):
        """
        Trigger EMFI pulse - IMPLEMENT BASED ON YOUR HARDWARE
        Returns: 'glitch', 'crash', or 'nothing'
        """
        time.sleep(0.01)  # Small delay
        
        # TODO: Implement actual EMFI trigger and result detection
        # Example using GPIO:
        # GPIO.output(EMFI_PIN, GPIO.HIGH)
        # time.sleep(0.001)
        # GPIO.output(EMFI_PIN, GPIO.LOW)
        
        # TODO: Check target device response to determine result
        # - 'glitch': Successful glitch (altered behavior)
        # - 'crash': Device crashed/hung
        # - 'nothing': No effect
        
        # Placeholder: simulate glitch detection
        result_val = np.random.random()
        if result_val < 0.3:
            return 'glitch'
        elif result_val < 0.4:
            return 'crash'
        else:
            return 'nothing'
        
    def start_scan(self):
        """Start EMFI scanning process"""
        if not self.connected:
            messagebox.showwarning("Not Connected", "Please connect to printer first")
            return
            
        if self.scanning:
            return
            
        # Confirm start
        x_steps = int(self.chip_width.get() / self.step_size.get()) + 1
        y_steps = int(self.chip_length.get() / self.step_size.get()) + 1
        z_steps = int(self.max_z_height.get() / self.z_increment.get()) + 1
        total_points = x_steps * y_steps * z_steps
        total_pulses = total_points * self.pulses_per_location.get()
        
        if not messagebox.askyesno("Start Scan", 
                                    f"Start EMFI scan?\n\n"
                                    f"Grid: {x_steps} x {y_steps} x {z_steps}\n"
                                    f"Total locations: {total_points}\n"
                                    f"Total EMFI pulses: {total_pulses}\n\n"
                                    f"Make sure origin is set correctly!"):
            return
            
        self.scanning = True
        self.start_scan_btn.config(state=tk.DISABLED)
        self.stop_scan_btn.config(state=tk.NORMAL)
        
        # Start scan in separate thread
        self.scan_thread = threading.Thread(target=self.run_scan, daemon=True)
        self.scan_thread.start()
        
    def stop_scan(self):
        """Stop scanning process"""
        self.scanning = False
        self.start_scan_btn.config(state=tk.NORMAL)
        self.stop_scan_btn.config(state=tk.DISABLED)
        
        # Move to safe position
        self.send_gcode("G1 Z30 F1000")
        
    def run_scan(self):
        """Main scanning loop - runs in separate thread"""
        try:
            x_steps = int(self.chip_width.get() / self.step_size.get()) + 1
            y_steps = int(self.chip_length.get() / self.step_size.get()) + 1
            z_steps = int(self.max_z_height.get() / self.z_increment.get()) + 1
            
            for z_idx in range(z_steps):
                if not self.scanning:
                    break
                    
                z_pos = z_idx * self.z_increment.get()
                
                for y_idx in range(y_steps):
                    if not self.scanning:
                        break
                        
                    y_pos = y_idx * self.step_size.get()
                    
                    # Snake pattern
                    if y_idx % 2 == 0:
                        x_range = range(x_steps)
                    else:
                        x_range = range(x_steps - 1, -1, -1)
                    
                    for x_idx in x_range:
                        if not self.scanning:
                            break
                            
                        x_pos = x_idx * self.step_size.get()
                        
                        # Move to position
                        self.send_gcode(f"G1 X{x_pos:.3f} Y{y_pos:.3f} Z{z_pos:.3f} F3000")
                        self.send_gcode("M400")
                        
                        self.current_x = x_pos
                        self.current_y = y_pos
                        self.current_z = z_pos
                        self.root.after(0, self.update_position_display)
                        
                        # Perform multiple EMFI pulses at this location
                        glitch_count = 0
                        crash_count = 0
                        nothing_count = 0
                        
                        for pulse in range(self.pulses_per_location.get()):
                            if not self.scanning:
                                break
                                
                            result = self.trigger_emfi()
                            if result == 'glitch':
                                glitch_count += 1
                                self.total_glitches += 1
                            elif result == 'crash':
                                crash_count += 1
                                self.total_crashes += 1
                            else:
                                nothing_count += 1
                            self.total_attempts += 1
                        
                        # Record data
                        self.glitch_data.append({
                            'x': x_pos,
                            'y': y_pos,
                            'z': z_pos,
                            'glitch': glitch_count,
                            'crash': crash_count,
                            'nothing': nothing_count,
                            'total': self.pulses_per_location.get()
                        })
                        
                        # Update visualization and stats
                        self.root.after(0, self.update_visualization)
                        self.root.after(0, self.update_statistics)
                        
            # Scan complete
            self.send_gcode("G1 Z30 F1000")
            
            # Generate heatmaps and find optimal location
            self.root.after(0, self.show_heatmaps_and_recommendation)
            
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Scan Error", f"Error during scan:\n{str(e)}"))
        
        finally:
            self.scanning = False
            self.root.after(0, lambda: self.start_scan_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_scan_btn.config(state=tk.DISABLED))
            
    def update_visualization(self):
        """Update the 3D visualization and success rate plot"""
        if not self.glitch_data:
            return
            
        # Clear plots
        self.ax_3d.clear()
        self.ax_success.clear()
        
        # Extract data
        x_coords = [d['x'] for d in self.glitch_data]
        y_coords = [d['y'] for d in self.glitch_data]
        z_coords = [d['z'] for d in self.glitch_data]
        success_rates = [d['glitch'] / d['total'] * 100 for d in self.glitch_data]
        
        # Top plot - 3D probe position
        # Plot scan path
        self.ax_3d.plot(x_coords, y_coords, z_coords, 'b-', alpha=0.3, linewidth=0.5, label='Scan Path')
        
        # Plot all scan points
        self.ax_3d.scatter(x_coords, y_coords, z_coords, c='gray', s=10, alpha=0.5)
        
        # Highlight current position if scanning
        if self.scanning:
            self.ax_3d.scatter([self.current_x], [self.current_y], [self.current_z], 
                              c='blue', s=100, marker='*', label='Current Position')
        
        self.ax_3d.set_xlabel("X Position (mm)")
        self.ax_3d.set_ylabel("Y Position (mm)")
        self.ax_3d.set_zlabel("Z Height (mm)")
        self.ax_3d.set_title("3D Probe Position")
        self.ax_3d.legend()
        
        # Bottom plot - Success rate over scan progression
        self.ax_success.plot(range(len(success_rates)), success_rates, 'g-', linewidth=1, label='Glitch Rate')
        self.ax_success.fill_between(range(len(success_rates)), success_rates, alpha=0.3)
        self.ax_success.set_xlabel("Location Index")
        self.ax_success.set_ylabel("Success Rate (%)")
        self.ax_success.set_title("Glitch Success Rate by Location")
        self.ax_success.grid(True, alpha=0.3)
        self.ax_success.set_ylim([0, 100])
        self.ax_success.legend()
        
        self.fig.tight_layout()
        self.canvas.draw()
        
    def update_statistics(self):
        """Update statistics text display"""
        self.stats_text.config(state=tk.NORMAL)
        self.stats_text.delete(1.0, tk.END)
        
        success_rate = (self.total_glitches/self.total_attempts*100) if self.total_attempts > 0 else 0
        crash_rate = (self.total_crashes/self.total_attempts*100) if self.total_attempts > 0 else 0
        
        stats = f"""
Scan Progress:
--------------
Total Locations: {len(self.glitch_data)}
Total EMFI Pulses: {self.total_attempts}

Results:
Total Glitches: {self.total_glitches}
Total Crashes: {self.total_crashes}

Glitch Rate: {success_rate:.2f}%
Crash Rate: {crash_rate:.2f}%

Current Position:
X: {self.current_x:.2f} mm
Y: {self.current_y:.2f} mm
Z: {self.current_z:.2f} mm

Status: {'SCANNING' if self.scanning else 'IDLE'}
        """
        
        self.stats_text.insert(1.0, stats)
        self.stats_text.config(state=tk.DISABLED)
        
    def reset_data(self):
        """Reset all scan data"""
        if messagebox.askyesno("Reset Data", "Clear all scan data and statistics?"):
            self.total_glitches = 0
            self.total_crashes = 0
            self.total_attempts = 0
            self.glitch_data = []
            self.update_visualization()
            self.update_statistics()
            
    def show_heatmaps_and_recommendation(self):
        """Generate heatmaps per Z layer and show optimal location recommendation"""
        if not self.glitch_data:
            messagebox.showwarning("No Data", "No scan data available")
            return
            
        # Group data by Z layer
        z_layers = {}
        for data in self.glitch_data:
            z = round(data['z'], 3)
            if z not in z_layers:
                z_layers[z] = []
            z_layers[z].append(data)
        
        # Create new window for heatmaps
        heatmap_window = tk.Toplevel(self.root)
        heatmap_window.title("EMFI Scan Results - Heatmaps and Recommendation")
        heatmap_window.geometry("1200x800")
        
        # Create notebook for tabs
        notebook = ttk.Notebook(heatmap_window)
        notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Create a tab for each Z layer
        for z_height in sorted(z_layers.keys()):
            layer_data = z_layers[z_height]
            
            # Create frame for this layer
            frame = ttk.Frame(notebook)
            notebook.add(frame, text=f"Z = {z_height:.3f} mm")
            
            # Create figure with two subplots
            fig = Figure(figsize=(10, 8))
            
            # Glitch heatmap
            ax1 = fig.add_subplot(211)
            self.plot_heatmap(ax1, layer_data, 'glitch', f'Glitch Success Rate - Z = {z_height:.3f} mm')
            
            # Crash heatmap
            ax2 = fig.add_subplot(212)
            self.plot_heatmap(ax2, layer_data, 'crash', f'Crash Rate - Z = {z_height:.3f} mm')
            
            fig.tight_layout()
            
            # Embed in frame
            canvas = FigureCanvasTkAgg(fig, frame)
            canvas.draw()
            canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # Find and display optimal location
        optimal_location = self.find_optimal_glitch_location()
        
        if optimal_location:
            # Create recommendation tab
            rec_frame = ttk.Frame(notebook)
            notebook.add(rec_frame, text="★ Recommendation")
            
            rec_text = tk.Text(rec_frame, font=("Arial", 12), wrap=tk.WORD)
            rec_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            
            recommendation = f"""
╔═══════════════════════════════════════════════════════════════╗
║                  OPTIMAL GLITCH LOCATION                      ║
╚═══════════════════════════════════════════════════════════════╝

Position:
  X: {optimal_location['x']:.3f} mm
  Y: {optimal_location['y']:.3f} mm
  Z: {optimal_location['z']:.3f} mm

Results (from {optimal_location['total']} pulses):
  Glitches: {optimal_location['glitch']} ({optimal_location['glitch']/optimal_location['total']*100:.1f}%)
  Crashes:  {optimal_location['crash']} ({optimal_location['crash']/optimal_location['total']*100:.1f}%)
  Nothing:  {optimal_location['nothing']} ({optimal_location['nothing']/optimal_location['total']*100:.1f}%)

Score: {optimal_location['score']:.2f}

═══════════════════════════════════════════════════════════════

Summary Statistics:
  Total locations scanned: {len(self.glitch_data)}
  Total EMFI pulses: {self.total_attempts}
  Overall glitch rate: {self.total_glitches/self.total_attempts*100:.2f}%
  Overall crash rate: {self.total_crashes/self.total_attempts*100:.2f}%
            """
            
            rec_text.insert(1.0, recommendation)
            rec_text.config(state=tk.DISABLED)
        
        messagebox.showinfo("Scan Complete", 
                           f"EMFI scan completed!\n\n"
                           f"Total glitches: {self.total_glitches}\n"
                           f"Total crashes: {self.total_crashes}\n"
                           f"Glitch rate: {self.total_glitches/self.total_attempts*100:.2f}%\n\n"
                           f"Check the heatmaps and recommendation tab!")
    
    def plot_heatmap(self, ax, layer_data, data_type, title):
        """Plot a heatmap for a specific data type (glitch or crash)"""
        # Extract coordinates and values
        x_coords = [d['x'] for d in layer_data]
        y_coords = [d['y'] for d in layer_data]
        values = [d[data_type] / d['total'] * 100 for d in layer_data]
        
        # Create grid for heatmap
        x_unique = sorted(set(x_coords))
        y_unique = sorted(set(y_coords))
        
        grid = np.zeros((len(y_unique), len(x_unique)))
        
        for d in layer_data:
            x_idx = x_unique.index(d['x'])
            y_idx = y_unique.index(d['y'])
            grid[y_idx, x_idx] = d[data_type] / d['total'] * 100
        
        # Plot heatmap
        im = ax.imshow(grid, cmap='hot', interpolation='nearest', aspect='auto',
                      extent=[min(x_unique), max(x_unique), min(y_unique), max(y_unique)],
                      origin='lower', vmin=0, vmax=100)
        
        ax.set_xlabel("X Position (mm)")
        ax.set_ylabel("Y Position (mm)")
        ax.set_title(title)
        
        # Add colorbar
        cbar = plt.colorbar(im, ax=ax)
        cbar.set_label('Success Rate (%)')
        
        # Add grid lines
        ax.grid(True, alpha=0.3, color='white')
    
    def find_optimal_glitch_location(self):
        """
        Find the optimal glitch location based on:
        - High glitch success rate
        - Low crash rate (crashes are worse than nothing)
        - Consistency with neighboring locations
        """
        if not self.glitch_data:
            return None
        
        best_location = None
        best_score = -999999
        
        for i, data in enumerate(self.glitch_data):
            # Calculate base score
            glitch_rate = data['glitch'] / data['total']
            crash_rate = data['crash'] / data['total']
            
            # Scoring formula:
            # - Glitches are good (weight: +10)
            # - Crashes are bad but not as bad as nothing (weight: -3)
            # - Nothing means wasted pulses (weight: -1)
            score = (glitch_rate * 10.0 - 
                    crash_rate * 3.0 - 
                    (data['nothing'] / data['total']) * 1.0)
            
            # Bonus for high absolute glitch count
            if data['glitch'] >= 3:
                score += 2.0
            
            # Consider neighbors for consistency (if available)
            neighbor_glitch_rates = []
            for neighbor in self.glitch_data:
                if neighbor == data:
                    continue
                dist = np.sqrt((neighbor['x'] - data['x'])**2 + 
                             (neighbor['y'] - data['y'])**2 +
                             (neighbor['z'] - data['z'])**2)
                
                # Consider neighbors within 2mm
                if dist <= 2.0:
                    neighbor_glitch_rates.append(neighbor['glitch'] / neighbor['total'])
            
            # Bonus if neighbors also have good glitch rates (consistency)
            if neighbor_glitch_rates:
                avg_neighbor_rate = np.mean(neighbor_glitch_rates)
                if avg_neighbor_rate > 0.2:  # If neighbors have >20% glitch rate
                    score += avg_neighbor_rate * 2.0
            
            if score > best_score:
                best_score = score
                best_location = data.copy()
                best_location['score'] = score
        
        return best_location
            
    def on_closing(self):
        """Handle window closing"""
        if self.scanning:
            if not messagebox.askyesno("Scan in Progress", 
                                       "Scan is running. Stop and exit?"):
                return
            self.scanning = False
            
        if self.connected:
            try:
                self.send_gcode("M84")  # Disable motors
                self.ser.close()
            except:
                pass
                
        self.root.destroy()

def main():
    root = tk.Tk()
    
    # Configure style
    style = ttk.Style()
    style.theme_use('clam')
    
    app = EMFIScannerGUI(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()

if __name__ == "__main__":
    main()
