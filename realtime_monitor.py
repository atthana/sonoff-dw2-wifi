import sonoff
import config
import time
import json
import argparse
import threading
import random
from datetime import datetime
from websocket import WebSocketApp, enableTrace
import ssl
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

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
        self.reconnect_count = 0
        self.max_reconnect_delay = 60  # Maximum reconnect delay in seconds
        self.ping_interval = 25  # Send ping every 25 seconds to keep connection alive
        self.last_ping_time = 0
        self.last_successful_connection = 0
        self.connection_stable = False
        self.fallback_to_polling = False
        
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
            # Reset reconnect count on successful message
            self.reconnect_count = 0
            self.connection_stable = True
            self.last_successful_connection = time.time()
            
            data = json.loads(message)
            
            # Handle pong response
            if 'action' in data and data['action'] == 'pong':
                logging.debug("Received pong from server")
                return
                
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
            logging.error(f"Error processing message: {e}")
    
    def on_error(self, ws, error):
        """Handle websocket errors"""
        logging.error(f"WebSocket error: {error}")
    
    def on_close(self, ws, close_status_code, close_msg):
        """Handle websocket connection close"""
        print('---------- on_close ----------')
        print("WebSocket connection closed")
        
        if not self.running:
            return
            
        # Calculate exponential backoff with jitter for reconnection
        # คำนวณเวลารอก่อนเชื่อมต่อใหม่แบบ exponential backoff
        # แทนที่จะรอ 5 วินาทีทุกครั้ง ตอนนี้เราใช้ระบบ exponential backoff ซึ่งจะรอนานขึ้นเรื่อยๆ หากมีการเชื่อมต่อล้มเหลวหลายครั้ง เพื่อไม่ให้เกิดการโหลดเซิร์ฟเวอร์มากเกินไป
        self.reconnect_count += 1
        base_delay = min(2 ** self.reconnect_count, self.max_reconnect_delay)
        jitter = random.uniform(0, 0.5 * base_delay)
        delay = base_delay + jitter
        delay = min(delay, self.max_reconnect_delay)  # Cap at max_reconnect_delay
        
        # If we've had too many reconnection attempts, fall back to polling
        # หากมีการเชื่อมต่อล้มเหลวมากกว่า 10 ครั้ง ให้เปลี่ยนไปใช้ polling แทน
        if self.reconnect_count > 10:
            if not self.fallback_to_polling:
                print("Too many reconnection attempts. Falling back to polling.")
                self.fallback_to_polling = True
        
        print(f"Attempting to reconnect in {delay:.1f} seconds... (Attempt {self.reconnect_count})")
        time.sleep(delay)
        self.start_websocket()
    
    def on_open(self, ws):
        """Handle websocket connection open"""
        print("WebSocket connection established")
        self.last_successful_connection = time.time()
        self.connection_stable = True
        
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
        
        # Start ping thread to keep connection alive
        ping_thread = threading.Thread(target=self.ping_websocket)
        ping_thread.daemon = True
        ping_thread.start()
    
    def ping_websocket(self):
        """Send periodic pings to keep the WebSocket connection alive"""
        while self.running and self.ws:
            if time.time() - self.last_ping_time > self.ping_interval:
                try:
                    if self.ws and self.ws.sock and self.ws.sock.connected:
                        # Send ping message
                        # ส่ง ping ทุกๆ 25 วินาที เพื่อรักษาการเชื่อมต่อให้คงอยู่
                        ping_payload = {
                            'action': 'ping',
                            'apikey': self.sonoff.get_user_apikey(),
                            'sequence': str(int(time.time() * 1000))
                        }
                        self.ws.send(json.dumps(ping_payload))
                        self.last_ping_time = time.time()
                        logging.debug("Ping sent to server")
                except Exception as e:
                    logging.error(f"Error sending ping: {e}")
            time.sleep(1)
    
    def start_websocket(self):
        """Start the websocket connection"""
        if not self.sonoff._wshost:
            print("Error: WebSocket host not available")
            return False
    
        # I have to use api of sonoff to get the websocket host, cannot create new websocket host because of the security policy of sonoff 
        ws_url = f"wss://{self.sonoff._wshost}:8080/api/ws"
        print(f"Connecting to WebSocket: {ws_url}")
        
        # Disable SSL certificate verification for local testing
        sslopt = {"cert_reqs": ssl.CERT_NONE, "check_hostname": False}
        
        # Enable trace for debugging if needed
        # enableTrace(True)
        self.ws = WebSocketApp(
            ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close
        )
        
        # Start WebSocket connection in a separate thread
        wst = threading.Thread(target=self.ws.run_forever, kwargs={
            "sslopt": sslopt,
            "ping_interval": 30,  # Send WebSocket ping frame every 30 seconds
            "ping_timeout": 10    # Wait 10 seconds for pong response
        })
        wst.daemon = True
        wst.start()
        self.last_ping_time = time.time()
        return True
    
    def poll_status(self):
        """Periodically poll device status as a backup to websocket"""
        polling_interval = 30  # Default polling interval (30 seconds)
        
        while self.running:
            try:
                # Adjust polling interval based on connection stability
                # ปรับความถี่ในการ polling ตามสถานะการเชื่อมต่อ
                if self.fallback_to_polling:
                    # If we're in fallback mode, poll more frequently
                    # ถ้าอยู่ในโหมด fallback ให้ polling ถี่ขึ้น
                    polling_interval = 5
                elif not self.connection_stable or (time.time() - self.last_successful_connection) > 60:
                    # If connection is unstable or no messages for 60 seconds, poll more frequently
                    # ถ้าการเชื่อมต่อไม่เสถียร ให้ polling ถี่ขึ้น
                    polling_interval = 10
                else:
                    # Normal backup polling interval
                    # ความถี่ปกติสำหรับการ polling แบบสำรอง
                    polling_interval = 30
                
                # Force update to get the latest device status
                devices = self.sonoff.get_devices(force_update=True)
                if devices and len(devices) > self.device_index:
                    current_device = devices[self.device_index]
                    current_state = current_device['params']['switch']
                    
                    # If the state has changed and wasn't caught by websocket
                    if current_state != self.last_state:
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        detection_method = "polling" if self.fallback_to_polling else "backup polling"
                        print(f"[{timestamp}] {self.name}: Switch is {current_state.upper()} (detected by {detection_method})")
                        self.last_state = current_state
                        
                    # If we're in fallback mode, always show the current status
                    elif self.fallback_to_polling and random.random() < 0.2:  # Show status occasionally (20% chance)
                        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        print(f"[{timestamp}] {self.name}: Switch is {current_state.upper()} (polling mode)")
                        
            except Exception as e:
                logging.error(f"Error polling status: {e}")
            
            # Wait before checking again
            time.sleep(polling_interval)
    
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
            self.fallback_to_polling = True
        
        # Start polling as a backup
        polling_thread = threading.Thread(target=self.poll_status)
        polling_thread.daemon = True
        polling_thread.start()
        
        # Start connection health checker
        health_thread = threading.Thread(target=self.check_connection_health)
        health_thread.daemon = True
        health_thread.start()
        
        try:
            # Keep the main thread alive
            while self.running:
                time.sleep(1)
        except KeyboardInterrupt:
            self.running = False
            if self.ws:
                self.ws.close()
            print("\nMonitoring stopped.")
            
    def check_connection_health(self):
        """Monitor the health of the WebSocket connection"""
        """ตรวจสอบสุขภาพของการเชื่อมต่อ WebSocket"""
        while self.running:
            # If no successful connection for 2 minutes, reset connection
            # หากไม่มีการเชื่อมต่อที่สำเร็จเป็นเวลา 2 นาที ให้รีเซ็ตการเชื่อมต่อ
            if time.time() - self.last_successful_connection > 120 and not self.fallback_to_polling:
                logging.warning("No successful WebSocket communication for 2 minutes, resetting connection")
                try:
                    if self.ws:
                        self.ws.close()
                except:
                    pass
                
                # Reset reconnect count occasionally to allow fresh attempts
                if self.reconnect_count > 20:
                    self.reconnect_count = 5
            
            time.sleep(30)

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
