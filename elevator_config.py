"""
Elevator System Configuration File

This file contains all configuration parameters for the elevator system,
using configurable settings instead of hardcoded constants
"""
from enum import Enum
from typing import Dict, Any


class SchedulingStrategy(Enum):
    """Elevator scheduling strategy enumeration"""
    SCAN = 'scan'       # Scan algorithm (direction priority, returns from endpoint)
    LOOK = 'look'       # Look algorithm (direction priority, changes direction when no more requests)
    SSTF = 'sstf'       # Shortest Seek Time First algorithm


# Default elevator floor configuration
DEFAULT_MIN_FLOOR = 0
DEFAULT_MAX_FLOOR = 20

# Elevator scheduling weight configuration
REQUEST_WEIGHT = 2      # Basic request weight
TARGET_WEIGHT = 5       # Target floor weight (internal buttons) - increased priority

# Scheduling algorithm safety parameters
MIN_DISTANCE_FACTOR = 1  # Minimum distance factor to avoid division by zero 
FLOOR_PROXIMITY_THRESHOLD = 1  # Threshold for determining proximity to min/max floors

# Runtime configuration
ELEVATOR_IDLE_CHECK_INTERVAL = 1.0  # Elevator idle state check interval (seconds)
ELEVATOR_MOVEMENT_CHECK_INTERVAL = 0.5  # Elevator movement state check interval (seconds)

# Door operation timing
DOOR_OPERATION_TIME = 1.5  # Time for doors to open/close and passengers to enter/exit (seconds)

# Test timing configuration
DEFAULT_WAIT_TIME = 3.0
SHORT_WAIT_TIME = 0.5
LONG_WAIT_TIME = 5.0
SCENARIO_WAIT_TIME = 1.0

# Test retry configuration
MAX_RETRY_ATTEMPTS = 3

# Complete default configuration
DEFAULT_CONFIG = {
    "elevator": {
        "min_floor": DEFAULT_MIN_FLOOR,
        "max_floor": DEFAULT_MAX_FLOOR
    },
    "scheduling": {
        "strategy": SchedulingStrategy.LOOK.value,  # Default using LOOK algorithm
        "weights": {
            "request": REQUEST_WEIGHT,
            "target": TARGET_WEIGHT
        },
        "safety": {
            "min_distance_factor": MIN_DISTANCE_FACTOR,
            "floor_proximity_threshold": FLOOR_PROXIMITY_THRESHOLD
        }
    },
    "timing": {
        "door_operation": DOOR_OPERATION_TIME
    },
    "intervals": {
        "idle_check": ELEVATOR_IDLE_CHECK_INTERVAL,
        "movement_check": ELEVATOR_MOVEMENT_CHECK_INTERVAL
    },
    "timeouts": {
        "default_wait": DEFAULT_WAIT_TIME,
        "short_wait": SHORT_WAIT_TIME,
        "long_wait": LONG_WAIT_TIME,
        "scenario_wait": SCENARIO_WAIT_TIME
    },
    "retries": {
        "max_attempts": MAX_RETRY_ATTEMPTS
    }
}


def get_config() -> Dict[str, Any]:
    """
    Get elevator system configuration
    
    Returns:
        Dictionary containing complete configuration information
    """
    return DEFAULT_CONFIG.copy() 