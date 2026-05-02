"""
Smart Home Security System - Serial Bridge

This script bridges communication between the Arduino UNO
(connected via USB Serial) and the Flask web server.

Architecture:
    Arduino UNO --USB Serial--> serial_bridge.py --HTTP--> Flask Server
    ESP32-S Camera --WiFi/HTTP--> Flask Server
    Web Browser --HTTP--> Flask Server

The bridge:
1. Reads sensor data from Arduino serial and POSTs to Flask
2. Polls Flask for hardware commands and sends them to Arduino
3. Forwards keypad codes from Arduino to Flask

Usage:
    python serial_bridge.py [--port COM3] [--baud 9600] [--server http://localhost:5000]

Requirements:
    pip install pyserial requests
"""

import serial
import serial.tools.list_ports
import requests
import json
import threading
import time
import argparse
import sys

# ==================== CONFIGURATION ====================
DEFAULT_BAUD = 9600
DEFAULT_SERVER = "http://localhost:5000"
POLL_INTERVAL = 3  # seconds between command polls


class SerialBridge:
    """Bridges Arduino UNO serial communication with Flask server."""

    def __init__(self, port, baud, server_url):
        self.server_url = server_url.rstrip('/')
        self.running = False
        self.serial_conn = None

        # Connect to Arduino
        try:
            self.serial_conn = serial.Serial(port, baud, timeout=1)
            print(f"Connected to Arduino on {port} at {baud} baud")
            time.sleep(2)  # Wait for Arduino reset
        except serial.SerialException as e:
            print(f"ERROR: Could not open serial port {port}")
            print(f"  {e}")
            print("\nAvailable ports:")
            for p in serial.tools.list_ports.comports():
                print(f"  {p.device} - {p.description}")
            sys.exit(1)

    def start(self):
        """Start the bridge with reader and poller threads."""
        self.running = True

        # Start serial reader thread
        reader = threading.Thread(target=self._serial_reader, daemon=True)
        reader.start()

        # Start command poller thread
        poller = threading.Thread(target=self._command_poller, daemon=True)
        poller.start()

        print(f"Bridge active: Arduino <--> {self.server_url}")
        print("Press Ctrl+C to stop\n")

        try:
            while self.running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            print("\nShutting down bridge...")
            self.running = False

    def stop(self):
        """Stop the bridge."""
        self.running = False
        if self.serial_conn and self.serial_conn.is_open:
            self.serial_conn.close()
            print("Serial connection closed")

    # ==================== SERIAL READER ====================
    def _serial_reader(self):
        """Read lines from Arduino and process them."""
        buffer = ""

        while self.running:
            try:
                if self.serial_conn and self.serial_conn.is_open:
                    data = self.serial_conn.read(1024).decode('utf-8', errors='replace')
                    if data:
                        buffer += data
                        # Process complete lines
                        while '\n' in buffer:
                            line, buffer = buffer.split('\n', 1)
                            line = line.strip()
                            if line:
                                self._process_arduino_line(line)
            except serial.SerialException as e:
                print(f"Serial error: {e}")
                time.sleep(1)
            except Exception as e:
                print(f"Reader error: {e}")
                time.sleep(0.5)

    def _process_arduino_line(self, line):
        """Process a single line from Arduino."""
        # Skip debug lines (start with #)
        if line.startswith('#'):
            print(f"[Arduino] {line[1:].strip()}")
            return

        # Sensor data: SENSORS:{json}
        if line.startswith('SENSORS:'):
            json_str = line[8:]  # Remove "SENSORS:" prefix
            self._send_sensor_data(json_str)
            return

        # Keypad code: KEYPAD:1234
        if line.startswith('KEYPAD:'):
            code = line[7:]  # Remove "KEYPAD:" prefix
            self._send_keypad_code(code)
            return

        # Unknown format - just print it
        print(f"[Arduino] {line}")

    # ==================== SEND TO FLASK SERVER ====================
    def _send_sensor_data(self, json_str):
        """Forward sensor data to Flask server."""
        try:
            data = json.loads(json_str)
            url = f"{self.server_url}/api/sensors/update"
            resp = requests.post(url, json=data, timeout=5)
            if resp.status_code == 200:
                print(f"[Sensor] Sent: flame={data.get('flame')}, "
                      f"smoke={data.get('smoke')}, laser={data.get('laser')}")
            else:
                print(f"[Sensor] Server error: {resp.status_code}")
        except json.JSONDecodeError as e:
            print(f"[Sensor] JSON parse error: {e}")
        except requests.RequestException as e:
            print(f"[Sensor] Request failed: {e}")

    def _send_keypad_code(self, code):
        """Forward keypad code to Flask server and notify Arduino of result."""
        try:
            url = f"{self.server_url}/api/keypad"
            resp = requests.post(url, json={"code": code}, timeout=5)
            if resp.status_code == 200:
                result = resp.json()
                status = result.get('status', '')
                if status == 'unlocked':
                    self._send_to_arduino("CMD:KEYPAD_OK:1")
                    print(f"[Keypad] Code accepted - door unlocked")
                else:
                    self._send_to_arduino("CMD:KEYPAD_FAIL:0")
                    print(f"[Keypad] Code rejected")
            else:
                print(f"[Keypad] Server error: {resp.status_code}")
        except requests.RequestException as e:
            print(f"[Keypad] Request failed: {e}")

    # ==================== COMMAND POLLER ====================
    def _command_poller(self):
        """Poll Flask server for hardware commands and send to Arduino."""
        while self.running:
            try:
                url = f"{self.server_url}/api/sensors/latest"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    self._process_server_commands(data)
            except requests.RequestException:
                pass  # Silently retry

            time.sleep(POLL_INTERVAL)

    def _process_server_commands(self, data):
        """Parse server sensor state and send commands to Arduino."""
        commands = []

        # Door command
        door = data.get('door', False)
        commands.append(f"CMD:DOOR:{1 if door else 0}")

        # Buzzer command
        buzzer = data.get('buzzer', False)
        commands.append(f"CMD:BUZZER:{1 if buzzer else 0}")

        # LED command
        led = data.get('led', False)
        commands.append(f"CMD:LED:{1 if led else 0}")

        # Servo angle
        servo_angle = data.get('servo_angle', 0)
        commands.append(f"CMD:SERVO:{servo_angle}")

        # Send all commands to Arduino
        for cmd in commands:
            self._send_to_arduino(cmd)

    # ==================== SEND TO ARDUINO ====================
    def _send_to_arduino(self, message):
        """Send a command string to Arduino via serial."""
        try:
            if self.serial_conn and self.serial_conn.is_open:
                self.serial_conn.write(f"{message}\n".encode('utf-8'))
        except serial.SerialException as e:
            print(f"[Serial write error] {e}")


# ==================== AUTO-DETECT PORT ====================
def find_arduino_port():
    """Try to auto-detect the Arduino UNO serial port."""
    ports = serial.tools.list_ports.comports()
    for p in ports:
        desc = p.description.lower()
        # Common Arduino UNO identifiers
        if any(x in desc for x in ['arduino', 'uno', 'ch340', 'cp210', 'ft232']):
            print(f"Auto-detected Arduino on {p.device} ({p.description})")
            return p.device
    # Fallback: return first available port
    if ports:
        print(f"Using first available port: {ports[0].device} ({ports[0].description})")
        return ports[0].device
    return None


# ==================== MAIN ====================
def main():
    parser = argparse.ArgumentParser(description='Smart Home Serial Bridge')
    parser.add_argument('--port', '-p', help='Arduino serial port (e.g., COM3 or /dev/ttyUSB0)')
    parser.add_argument('--baud', '-b', type=int, default=DEFAULT_BAUD,
                        help=f'Baud rate (default: {DEFAULT_BAUD})')
    parser.add_argument('--server', '-s', default=DEFAULT_SERVER,
                        help=f'Flask server URL (default: {DEFAULT_SERVER})')
    args = parser.parse_args()

    # Find port
    port = args.port
    if not port:
        port = find_arduino_port()
        if not port:
            print("ERROR: No serial port specified and no Arduino auto-detected!")
            print("Usage: python serial_bridge.py --port COM3")
            print("\nAvailable ports:")
            for p in serial.tools.list_ports.comports():
                print(f"  {p.device} - {p.description}")
            sys.exit(1)

    # Start bridge
    bridge = SerialBridge(port, args.baud, args.server)
    try:
        bridge.start()
    finally:
        bridge.stop()


if __name__ == '__main__':
    main()
