# Sonoff Project Makefile
# This file contains common commands for the Sonoff monitoring project

# Default Python interpreter
PYTHON = python

# Default device index (change this to match your device)
DEVICE_INDEX = 2

# Help command
.PHONY: help
help:
	@echo "Sonoff Project Makefile"
	@echo "---------------------"
	@echo "Available commands:"
	@echo "  make setup      - Install required dependencies"
	@echo "  make run        - Run the basic device status check (main.py)"
	@echo "  make monitor    - Run the polling-based monitor (monitor.py)"
	@echo "  make realtime   - Run the real-time WebSocket monitor (realtime_monitor.py)"
	@echo "  make device-0   - Set device index to 0 for monitoring"
	@echo "  make device-1   - Set device index to 1 for monitoring"
	@echo "  make device-2   - Set device index to 2 for monitoring"
	@echo "  make clean      - Clean up __pycache__ directories"
	@echo "  make help       - Show this help message"

# Default target
.PHONY: default
default: help

# Setup environment and install dependencies
.PHONY: setup
setup:
	@echo "Installing required dependencies..."
	pip install requests websocket-client
	@echo "Setup complete!"

# Run the basic device status check
.PHONY: run
run:
	$(PYTHON) main.py

# Run the polling-based monitor
.PHONY: monitor
monitor:
	$(PYTHON) monitor.py --device-index $(DEVICE_INDEX)

# Run the real-time WebSocket monitor
.PHONY: realtime
realtime:
	$(PYTHON) realtime_monitor.py --device-index $(DEVICE_INDEX)

# Device index selection targets
.PHONY: device-0 device-1 device-2
device-0:
	@echo "Setting device index to 0"
	$(eval DEVICE_INDEX = 0)

device-1:
	@echo "Setting device index to 1"
	$(eval DEVICE_INDEX = 1)

device-2:
	@echo "Setting device index to 2"
	$(eval DEVICE_INDEX = 2)

# Clean up __pycache__ directories
.PHONY: clean
clean:
	@echo "Cleaning up __pycache__ directories..."
	find . -type d -name "__pycache__" -exec rm -rf {} +
	@echo "Clean complete!"
