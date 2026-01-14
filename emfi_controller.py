import serial
import time
import numpy as np

class EMFIController:
    """Core controller for EMFI scanning operations"""
    
    def __init__(self):
        # Serial connections
        self.printer_ser = None
        self.printer_connected = False
        
        self.emfi_ser = None
        self.emfi_connected = False
        
        self.target_ser = None
        self.target_connected = False
        
        # Position tracking
        self.current_x = 0.0
        self.current_y = 0.0
        self.current_z = 0.0
        
        # Chip area definition
        self.origin_set = False
        self.top_right_x = None
        self.top_right_y = None
        self.top_right_set = False
        
        # Scan data
        self.total_glitches = 0
        self.total_crashes = 0
        self.total_attempts = 0
        self.glitch_data = []
        
        # Scanning state
        self.scanning = False
        
    # ======================== CONNECTION MANAGEMENT ========================
    
    def connect_printer(self, port, baudrate):
        """Connect to 3D printer"""
        try:
            self.printer_ser = serial.Serial(port, baudrate, timeout=5)
            time.sleep(2)
            self.printer_connected = True
            self.initialize_printer()
            return True, "Connected to printer successfully!"
        except Exception as e:
            return False, f"Failed to connect to printer:\n{str(e)}"
    
    def disconnect_printer(self):
        """Disconnect from 3D printer"""
        try:
            if self.printer_connected and self.printer_ser:
                self.send_gcode("M84")  # Disable motors
                self.printer_ser.close()
            self.printer_connected = False
            return True, "Printer disconnected"
        except Exception as e:
            return False, f"Error disconnecting printer:\n{str(e)}"
    
    def connect_emfi(self, port, baudrate):
        """Connect to EMFI device"""
        try:
            self.emfi_ser = serial.Serial(port, baudrate, timeout=2)
            time.sleep(0.5)
            self.emfi_connected = True
            return True, "Connected to EMFI device successfully!"
        except Exception as e:
            return False, f"Failed to connect to EMFI device:\n{str(e)}"
    
    def disconnect_emfi(self):
        """Disconnect from EMFI device"""
        try:
            if self.emfi_connected and self.emfi_ser:
                self.emfi_ser.close()
            self.emfi_connected = False
            return True, "EMFI device disconnected"
        except Exception as e:
            return False, f"Error disconnecting EMFI device:\n{str(e)}"
    
    def connect_target(self, port, baudrate):
        """Connect to target device"""
        try:
            self.target_ser = serial.Serial(port, baudrate, timeout=2)
            time.sleep(0.5)
            self.target_connected = True
            return True, "Connected to target device successfully!"
        except Exception as e:
            return False, f"Failed to connect to target device:\n{str(e)}"
    
    def disconnect_target(self):
        """Disconnect from target device"""
        try:
            if self.target_connected and self.target_ser:
                self.target_ser.close()
            self.target_connected = False
            return True, "Target device disconnected"
        except Exception as e:
            return False, f"Error disconnecting target device:\n{str(e)}"
    
    # ======================== COMMUNICATION ========================
    
    def initialize_printer(self):
        """Initialize printer settings"""
        self.send_gcode("M84 X Y Z S12000")
        self.send_gcode("G21")  # Millimeters
        self.send_gcode("G90")  # Absolute positioning
        self.send_gcode("M999")  # Ignore errors
    
    def send_gcode(self, command):
        """Send G-code command to printer"""
        if not self.printer_connected:
            return None
            
        try:
            self.printer_ser.write(str.encode(command + "\r\n"))
            time.sleep(0.05)
            
            response = ""
            start_time = time.time()
            while time.time() - start_time < 0.5:
                if self.printer_ser.in_waiting:
                    response += self.printer_ser.read(self.printer_ser.in_waiting).decode('utf-8', errors='ignore')
                    break
                time.sleep(0.01)
                
            return response
        except Exception as e:
            print(f"Error sending G-code: {e}")
            return None
    
    def send_emfi_command(self, command):
        """Send command to EMFI device"""
        if not self.emfi_connected:
            return None
        
        try:
            self.emfi_ser.write(str.encode(command + "\r\n"))
            time.sleep(0.01)
            
            response = ""
            start_time = time.time()
            while time.time() - start_time < 0.2:
                if self.emfi_ser.in_waiting:
                    response += self.emfi_ser.read(self.emfi_ser.in_waiting).decode('utf-8', errors='ignore')
                    break
                time.sleep(0.005)
                
            return response
        except Exception as e:
            print(f"Error sending EMFI command: {e}")
            return None
    
    def send_target_command(self, command):
        """Send command to target device"""
        if not self.target_connected:
            return None
        
        try:
            self.target_ser.write(str.encode(command + "\r\n"))
            time.sleep(0.01)
            
            response = ""
            start_time = time.time()
            while time.time() - start_time < 0.2:
                if self.target_ser.in_waiting:
                    response += self.target_ser.read(self.target_ser.in_waiting).decode('utf-8', errors='ignore')
                    break
                time.sleep(0.005)
                
            return response
        except Exception as e:
            print(f"Error sending target command: {e}")
            return None
    
    def read_target_response(self, timeout=0.5):
        """Read response from target device"""
        if not self.target_connected:
            return None
        
        try:
            response = ""
            start_time = time.time()
            while time.time() - start_time < timeout:
                if self.target_ser.in_waiting:
                    response += self.target_ser.read(self.target_ser.in_waiting).decode('utf-8', errors='ignore')
                time.sleep(0.01)
            return response if response else None
        except Exception as e:
            print(f"Error reading target response: {e}")
            return None
    
    # ======================== MOVEMENT CONTROL ========================
    
    def move_relative(self, axis, distance):
        """Move printer relatively on specified axis"""
        if not self.printer_connected:
            return False, "Printer not connected"
        
        try:
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
            
            return True, f"Moved {axis} by {distance}mm"
        except Exception as e:
            return False, f"Movement error: {str(e)}"
    
    def move_to_position(self, x, y, z):
        """Move to absolute position"""
        if not self.printer_connected:
            return False, "Printer not connected"
        
        try:
            self.send_gcode(f"G1 X{x:.3f} Y{y:.3f} Z{z:.3f} F3000")
            self.send_gcode("M400")
            
            self.current_x = x
            self.current_y = y
            self.current_z = z
            
            return True, f"Moved to position ({x}, {y}, {z})"
        except Exception as e:
            return False, f"Movement error: {str(e)}"
    
    def home_all_axes(self):
        """Home all axes"""
        if not self.printer_connected:
            return False, "Printer not connected"
        
        try:
            self.send_gcode("G28")
            self.send_gcode("M400")
            self.current_x = 0
            self.current_y = 0
            self.current_z = 0
            self.send_gcode("M999")
            return True, "Homing complete"
        except Exception as e:
            return False, f"Homing error: {str(e)}"
    
    def set_origin(self):
        """Set current position as origin (0,0,0)"""
        if not self.printer_connected:
            return False, "Printer not connected"
        
        try:
            self.send_gcode("G92 X0 Y0 Z0")
            self.current_x = 0
            self.current_y = 0
            self.current_z = 0
            self.origin_set = True
            return True, "Origin set at current position"
        except Exception as e:
            return False, f"Error setting origin: {str(e)}"
    
    def set_top_right_corner(self):
        """Mark current position as top-right corner"""
        if not self.printer_connected:
            return False, "Printer not connected"
        
        if not self.origin_set:
            return False, "Origin must be set first"
        
        if self.current_x <= 0 or self.current_y <= 0:
            return False, f"Invalid position: X={self.current_x:.2f}, Y={self.current_y:.2f}"
        
        self.top_right_x = self.current_x
        self.top_right_y = self.current_y
        self.top_right_set = True
        
        return True, f"Top-right corner set at ({self.top_right_x:.2f}, {self.top_right_y:.2f})"
    
    # ======================== EMFI OPERATIONS ========================
    
    def arm_faultycat(self):
        """Arm the FaultyCat device for EMFI"""
        if not self.emfi_connected:
            return False, "EMFI device not connected"
        
        try:
            # First disarm to ensure clean state
            self.send_emfi_command("d")
            time.sleep(0.1)
            
            # Arm the device
            self.send_emfi_command("a")
            time.sleep(0.1)
            
            return True, "FaultyCat armed successfully"
        except Exception as e:
            return False, f"Error arming FaultyCat: {str(e)}"
    
    def disarm_faultycat(self):
        """Disarm the FaultyCat device"""
        if not self.emfi_connected:
            return False, "EMFI device not connected"
        
        try:
            self.send_emfi_command("d")
            time.sleep(0.1)
            return True, "FaultyCat disarmed successfully"
        except Exception as e:
            return False, f"Error disarming FaultyCat: {str(e)}"
    
    def trigger_emfi(self):
        """
        Trigger EMFI pulse and detect result
        Returns: 'glitch', 'crash', or 'nothing'
        """
        # If FaultyCat EMFI device is connected, use it
        if self.emfi_connected:
            try:
                # Send pulse command to FaultyCat
                self.send_emfi_command("p")
                time.sleep(0.01)  # Small delay after pulse
            except Exception as e:
                print(f"Error triggering FaultyCat pulse: {e}")
                return 'nothing'
        else:
            # Simulate trigger with GPIO or other method
            # TODO: Implement GPIO trigger for non-FaultyCat devices
            time.sleep(0.01)
        
        # If target device is connected, check its response
        if self.target_connected:
            try:
                # TODO: Implement result detection based on target response
                # This depends on your specific target device
                
                # Example strategies:
                # 1. Send a test command and check for correct response
                # response = self.send_target_command("STATUS")
                # expected_response = "OK"
                
                # 2. Try to read some data and see if it's corrupted
                # data = self.read_target_response(timeout=0.2)
                
                # 3. Check if device is still responsive
                # if response is None or len(response) == 0:
                #     return 'crash'
                # elif response != expected_response:
                #     return 'glitch'
                # else:
                #     return 'nothing'
                
                # For now, read response and make basic determination
                response = self.read_target_response(timeout=0.1)
                
                if response is None or len(response) == 0:
                    # No response - device may have crashed
                    return 'crash'
                else:
                    # Got response - check if it seems normal
                    # This is a placeholder - customize based on your target
                    if "ERROR" in response.upper() or "FAULT" in response.upper():
                        return 'glitch'
                    else:
                        return 'nothing'
                        
            except Exception as e:
                print(f"Error reading target response: {e}")
                return 'crash'
        else:
            # Without target device, simulate result
            result_val = np.random.random()
            if result_val < 0.3:
                return 'glitch'
            elif result_val < 0.4:
                return 'crash'
            else:
                return 'nothing'
    
    # ======================== SCANNING ========================
    
    def calculate_scan_grid(self, step_size, z_increment, max_z_height):
        """Calculate scan grid dimensions"""
        if not self.top_right_set:
            return None
        
        x_steps = int(self.top_right_x / step_size) + 1
        y_steps = int(self.top_right_y / step_size) + 1
        z_steps = int(max_z_height / z_increment) + 1
        total_points = x_steps * y_steps * z_steps
        
        return {
            'x_steps': x_steps,
            'y_steps': y_steps,
            'z_steps': z_steps,
            'total_points': total_points
        }
    
    def run_scan(self, step_size, z_increment, max_z_height, pulses_per_location, progress_callback=None):
        """
        Run EMFI scan over the defined area
        progress_callback: function(current, total, x, y, z, data) called after each location
        """
        if not self.printer_connected:
            return False, "Printer not connected"
        
        if not self.origin_set or not self.top_right_set:
            return False, "Chip area not configured"
        
        grid = self.calculate_scan_grid(step_size, z_increment, max_z_height)
        if not grid:
            return False, "Failed to calculate grid"
        
        # Arm FaultyCat if connected
        if self.emfi_connected:
            success, msg = self.arm_faultycat()
            if not success:
                return False, f"Failed to arm FaultyCat: {msg}"
            print("FaultyCat armed and ready for EMFI")
        
        self.scanning = True
        x_steps = grid['x_steps']
        y_steps = grid['y_steps']
        z_steps = grid['z_steps']
        
        location_index = 0
        total_locations = grid['total_points']
        
        try:
            for z_idx in range(z_steps):
                if not self.scanning:
                    break
                
                z_pos = z_idx * z_increment
                
                for y_idx in range(y_steps):
                    if not self.scanning:
                        break
                    
                    y_pos = y_idx * step_size
                    
                    # Snake pattern for efficiency
                    if y_idx % 2 == 0:
                        x_range = range(x_steps)
                    else:
                        x_range = range(x_steps - 1, -1, -1)
                    
                    for x_idx in x_range:
                        if not self.scanning:
                            break
                        
                        x_pos = x_idx * step_size
                        
                        # Move to position
                        success, msg = self.move_to_position(x_pos, y_pos, z_pos)
                        if not success:
                            if self.emfi_connected:
                                self.disarm_faultycat()
                            return False, msg
                        
                        # Small delay to stabilize position
                        time.sleep(0.05)
                        
                        # Perform multiple EMFI pulses at this location
                        glitch_count = 0
                        crash_count = 0
                        nothing_count = 0
                        
                        for pulse in range(pulses_per_location):
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
                            
                            # Small delay between pulses at same location
                            time.sleep(0.02)
                        
                        # Record data
                        data_point = {
                            'x': x_pos,
                            'y': y_pos,
                            'z': z_pos,
                            'glitch': glitch_count,
                            'crash': crash_count,
                            'nothing': nothing_count,
                            'total': pulses_per_location
                        }
                        self.glitch_data.append(data_point)
                        
                        location_index += 1
                        
                        # Call progress callback
                        if progress_callback:
                            progress_callback(location_index, total_locations, x_pos, y_pos, z_pos, data_point)
            
            # Move to safe position
            self.send_gcode("G1 Z30 F1000")
            
            # Disarm FaultyCat if connected
            if self.emfi_connected:
                success, msg = self.disarm_faultycat()
                if success:
                    print("FaultyCat disarmed safely")
            
            return True, "Scan completed successfully"
            
        except Exception as e:
            # Make sure to disarm on error
            if self.emfi_connected:
                self.disarm_faultycat()
            return False, f"Scan error: {str(e)}"
        finally:
            self.scanning = False
    
    def stop_scan(self):
        """Stop the current scan"""
        self.scanning = False
        
        # Disarm FaultyCat if connected
        if self.emfi_connected:
            self.disarm_faultycat()
        
        # Move to safe position
        if self.printer_connected:
            self.send_gcode("G1 Z30 F1000")
    
    def reset_data(self):
        """Reset all scan data"""
        self.total_glitches = 0
        self.total_crashes = 0
        self.total_attempts = 0
        self.glitch_data = []
    
    # ======================== DATA ANALYSIS ========================
    
    def find_optimal_glitch_location(self):
        """
        Find the optimal glitch location based on scoring
        Returns: dict with location data and score, or None
        """
        if not self.glitch_data:
            return None
        
        best_location = None
        best_score = -999999
        
        for data in self.glitch_data:
            # Calculate base score
            glitch_rate = data['glitch'] / data['total']
            crash_rate = data['crash'] / data['total']
            
            # Scoring formula
            score = (glitch_rate * 10.0 - 
                    crash_rate * 3.0 - 
                    (data['nothing'] / data['total']) * 1.0)
            
            # Bonus for high absolute glitch count
            if data['glitch'] >= 3:
                score += 2.0
            
            # Consider neighbors for consistency
            neighbor_glitch_rates = []
            for neighbor in self.glitch_data:
                if neighbor == data:
                    continue
                dist = np.sqrt((neighbor['x'] - data['x'])**2 + 
                             (neighbor['y'] - data['y'])**2 +
                             (neighbor['z'] - data['z'])**2)
                
                if dist <= 2.0:
                    neighbor_glitch_rates.append(neighbor['glitch'] / neighbor['total'])
            
            if neighbor_glitch_rates:
                avg_neighbor_rate = np.mean(neighbor_glitch_rates)
                if avg_neighbor_rate > 0.2:
                    score += avg_neighbor_rate * 2.0
            
            if score > best_score:
                best_score = score
                best_location = data.copy()
                best_location['score'] = score
        
        return best_location
    
    def get_data_by_z_layer(self):
        """Group scan data by Z layer"""
        z_layers = {}
        for data in self.glitch_data:
            z = round(data['z'], 3)
            if z not in z_layers:
                z_layers[z] = []
            z_layers[z].append(data)
        return z_layers
    
    # ======================== CLEANUP ========================
    
    def cleanup(self):
        """Cleanup all connections"""
        self.disconnect_printer()
        self.disconnect_emfi()
        self.disconnect_target()
