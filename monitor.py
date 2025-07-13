import sonoff
import config
import time
import argparse
from datetime import datetime

def monitor_device(device_index=2, check_interval=5):
    """
    Monitor a specific device's switch status and report changes in real-time.
    
    Args:
        device_index: Index of the device in the devices list (default: 2)
        check_interval: Time between status checks in seconds (default: 5)
    """
    print('Initializing Sonoff connection...')
    s = sonoff.Sonoff(config.username, config.password, config.api_region)
    
    # Get initial device information
    devices = s.get_devices()
    if not devices or len(devices) <= device_index:
        print(f"Error: Device at index {device_index} not found.")
        return
    
    device_id = devices[device_index]['deviceid']
    name = devices[device_index]['name']
    
    print(f"Monitoring device: {name} (ID: {device_id})")
    print("Press Ctrl+C to stop monitoring.")
    print("-" * 50)
    
    # Store the previous state to detect changes
    previous_state = None
    
    try:
        while True:
            # Force update to get the latest device status
            devices = s.get_devices(force_update=True)
            if not devices or len(devices) <= device_index:
                print(f"Error: Device at index {device_index} not found.")
                time.sleep(check_interval)
                continue
                
            current_device = devices[device_index]
            current_state = current_device['params']['switch']
            
            # If this is the first check or the state has changed
            if previous_state is None or previous_state != current_state:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                print(f"[{timestamp}] {name}: Switch is {current_state.upper()}")
                previous_state = current_state
            
            # Wait before checking again
            time.sleep(check_interval)
            
    except KeyboardInterrupt:
        print("\nMonitoring stopped.")

if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description='Monitor Sonoff device switch status')
    parser.add_argument('--device-index', type=int, default=2,
                        help='Index of the device in the devices list (default: 2)')
    parser.add_argument('--check-interval', type=int, default=5,
                        help='Time between status checks in seconds (default: 5)')
    args = parser.parse_args()
    
    # Start monitoring with the specified parameters
    monitor_device(device_index=args.device_index, check_interval=args.check_interval)
