import sonoff
import config
import time
import json
import argparse
import threading
from datetime import datetime
from websocket import WebSocketApp
import ssl

class SonoffMonitor:
    def __init__(self, username, password, api_region, device_index=2):
        self.username = username
        self.password = password
        self.api_region = api_region
        self.device_index = device_index
        self.sonoff = None
        self.device = None
        self.device_id = None
        self.name = None
        self.ws = None
        self.running = False
        self.last_state = None
        
    def initialize(self):
        """Initialize the Sonoff connection and get device information"""
        print('Initializing Sonoff connection...')
        self.sonoff = sonoff.Sonoff(self.username, self.password, self.api_region)
        
        # Get initial device information
        devices = self.sonoff.get_devices()
        if not devices or len(devices) <= self.device_index:
            print(f"Error: Device at index {self.device_index} not found.")
            return False
        
        self.device = devices[self.device_index]
        self.device_id = self.device['deviceid']
        self.name = self.device['name']
        self.last_state = self.device['params']['switch']
        
        print(f"Monitoring device: {self.name} (ID: {self.device_id})")
        print(f"Initial state: {self.last_state.upper()}")
        return True
    
    def on_message(self, ws, message):
        """Handle incoming websocket messages"""
        try:
            data = json.loads(message)
            
            # Check if this is a device update message
            if 'action' in data and data['action'] == 'update':
                if 'deviceid' in data and data['deviceid'] == self.device_id:
                    if 'params' in data and 'switch' in data['params']:
                        new_state = data['params']['switch']
                        if new_state != self.last_state:
                            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            print(f"[{timestamp}] {self.name}: Switch changed from {self.last_state.upper()} to {new_state.upper()}")
                            self.last_state = new_state
        except Exception as e:
            print(f"Error processing message: {e}")
    
    def on_error(self, ws, error):
        """Handle websocket errors"""
        print(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle websocket connection close"""
        print("WebSocket connection closed")
        if self.running:
            print("Attempting to reconnect in 5 seconds...")
            time.sleep(5)
            self.start_websocket()
    
    def on_open(self, ws):
        """Handle websocket connection open"""
        print("WebSocket connection established")
        
        # Send authentication message
        payload = {
            'action': 'userOnline',
            'at': self.sonoff.get_bearer_token(),
            'apikey': self.sonoff.get_user_apikey(),
            'userAgent': 'app',
            'appid': self.sonoff.appid,
            'nonce': str(int(time.time() / 100)),
            'ts': int(time.time()),
            'version': 8,
            'sequence': str(int(time.time() * 1000))
        }
        ws.send(json.dumps(payload))
    
    def start_websocket(self):
        """Start the websocket connection"""
        if not self.sonoff._wshost:
            print("Error: WebSocket host not available")
            return False
        
        ws_url = f"wss://{self.sonoff._wshost}:8080/api/ws"
        print(f"Connecting to WebSocket: {ws_url}")
        
        # Disable SSL certificate verification for local testing
        sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
        
        self.ws = WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Start WebSocket connection in a separate thread
        wst = threading.Thread(target=self.ws.run_forever, kwargs={"sslopt": sslopt})
        wst.daemon = True
        wst.start()
        return True
    
    def poll_status(self):
        """Periodically poll device status as a backup to websocket"""
        while self.running:
            try:
                # Force update to get the latest device status
                devices = self.sonoff.get_devices(force_update=True)
                if devices and len(devices) > self.device_index:
                    current_device = devices[self.device_index]
                    current_state = current_device['params']['switch']
                    
                    # If the state has changed and wasn't caught by websocket
                    if current_state != self.last_state:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        print(f"[{timestamp}] {self.name}: Switch is {current_state.upper()} (detected by polling)")
                        self.last_state = current_state
            except Exception as e:
                print(f"Error polling status: {e}")
            
            # Wait before checking again (longer interval since this is a backup)
            time.sleep(30)
    
    def start_monitoring(self):
        """Start monitoring the device"""
        if not self.initialize():
            return
        
        self.running = True
        print("Starting real-time monitoring...")
        print("Press Ctrl+C to stop monitoring.")
        print("-" * 50)
        
        # Start websocket connection
        if not self.start_websocket():
            print("Failed to start WebSocket connection. Falling back to polling only.")
        
        # Start polling as a backup
        polling_thread = threading.Thread(target=self.poll_status)
        polling_thread.daemon = True
        polling_thread.start()
        
        try:
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            if self.ws:
                self.ws.close()
            print("\nMonitoring stopped.")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Real-time monitor for Sonoff device switch status')
    parser.add_argument('--device-index', type=int, default=2,
                        help='Index of the device in the devices list (default: 2)')
    args = parser.parse_args()
    
    # Start monitoring with the specified parameters
    monitor = SonoffMonitor(
        username=config.username,
        password=config.password,
        api_region=config.api_region,
        device_index=args.device_index
    )
    monitor.start_monitoring()
