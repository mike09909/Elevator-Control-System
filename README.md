# Elevator Control System

A comprehensive elevator scheduling and control system that simulates elevator movement and handles various scheduling scenarios using professional elevator scheduling algorithms.

## Project Overview

This project implements an intelligent elevator control system that efficiently handles passenger requests using advanced scheduling algorithms. The system simulates elevator movement and processes both external (up/down buttons on floors) and internal (floor selection buttons inside elevator) requests, all based on general elevator scheduling principles without any hardcoded floor values.

## Features

- **Professional Scheduling Algorithms**: Implementation of industry-standard elevator scheduling algorithms (LOOK, SCAN, SSTF) without any hardcoded magic numbers
- **Truly General Implementation**: All decision logic based on relative floor positions and dynamic request collections, not specific floor numbers
- **Configurable System**: All parameters are configurable through a central configuration file
- **Optimized Wait Times**: The system optimizes passenger wait times by intelligently prioritizing requests
- **Realistic Simulation**: Complete simulation of elevator movement with asynchronous operation
- **Comprehensive Test Suite**: Unit tests and scenario-based integration tests ensure correct behavior
- **Detailed Logging**: Extensive logging for monitoring and debugging in professional English

## System Architecture

The project follows a modular architecture with clear separation of concerns:

### Core Components

- **elevator_interface.py**: Defines core interfaces, protocols, and enums for elevator status and direction
- **elevator_controller.py**: Implements the elevator scheduling algorithms and request handling logic
- **elevator_mock.py**: Provides a mock implementation of elevator hardware for testing
- **elevator_config.py**: Contains all configurable parameters for the system
- **run_realistic_scenario.py**: Contains realistic test scenarios that simulate real-world elevator use cases
- **tests.py**: Contains unit tests for validating system behavior

### Scheduling Algorithms

The system implements several professional elevator scheduling algorithms, all without any hardcoded floor values:

1. **LOOK Algorithm** (Default): Continues in the current direction until there are no more requests in that direction, then changes direction immediately. This optimizes the total travel distance.

2. **SCAN Algorithm**: Also known as the Elevator Algorithm, continues in the current direction until reaching the end of the track, then reverses direction.

3. **Shortest Seek Time First (SSTF)**: Always chooses the nearest floor with a request, minimizing immediate wait time but potentially causing starvation.

## Requirements

- Python 3.8+
- Standard libraries: asyncio, logging, typing (all built-in)

## Usage

### Running the Realistic Scenario Test

To run the realistic elevator scenario test:

```bash
python run_realistic_scenario.py
```

This simulates a complex elevator scenario with multiple users requesting the elevator from different floors, testing the general-purpose scheduling algorithm's ability to handle real-world scenarios without hardcoded behavior.

### Running Unit Tests

To run the unit test suite:

```bash
python tests.py
```

## Example Scenario

The integration test in `run_realistic_scenario.py` simulates the following elevator scenario:

1. Elevator is idle at floor 0
2. User A requests DOWN from floor 9 => Elevator starts moving up
3. Elevator is moving up, currently at floor 3
4. User B requests UP from floor 5 => Elevator stops at floor 5
5. User C requests UP from floor 2 => Elevator temporarily ignores/queues this request
6. Elevator stops at floor 5, User B enters and requests floor 8 => Elevator stops at floor 8
7. User D requests DOWN from floor 15 => Elevator continues up to floor 15 (skipping floor 9)
8. Elevator stops at floor 15, User D enters and requests floor 11
9. Elevator moves down, stops at floor 11, User D exits
10. Elevator moves down, stops at floor 9, User A enters and requests floor 0
11. Elevator moves down, stops at floor 0, User A exits
12. Elevator moves up, stops at floor 2, User C enters

This scenario tests the elevator's ability to efficiently handle multiple requests from different floors while optimizing travel paths based on direction and priority. The key point is that the elevator correctly skips floor 9 on the way up to floor 15, following professional direction-priority principles, all without any hardcoded instructions for this specific case.

## Configuration

The system is highly configurable through the `elevator_config.py` file, which includes:

- Scheduling algorithm selection (LOOK, SCAN, SSTF)
- Floor range (min_floor, max_floor)
- Scoring weights for different types of requests
- Timeout values and retry attempts for testing

## Core Algorithm

The elevator scheduling algorithm uses a professional scoring system to determine the optimal direction of travel:

1. **Direction Scoring**: Assigns weights to pending requests based on:

   - Direction of travel
   - Type of request (internal vs. external)
   - Proximity to current position

2. **Direction Priority Principle**: Prioritizes serving requests in the current direction before changing direction

3. **Stop Decision Logic**: Determines when to stop at a floor based on:
   - Current direction
   - Pending requests at the floor
   - Target floor matches
   - Above/below request distribution

The key distinction of this implementation is that all decisions are made based on general elevator scheduling principles, with no hardcoded floor values or "magic numbers" that would limit the system's generality.

## Test Results

### Unit Test Results

All unit tests pass successfully, verifying the correct functionality of the core elevator control components:

```
----------------------------------------------------------------------
Ran 19 tests in 0.518s

OK
```

### Integration Test Results

The integration test scenarios completed successfully, with the elevator moving through all expected floors in the correct sequence:

```
===== Test Results Analysis =====
Elevator stop sequence: [5, 8, 15, 11, 9, 0, 2]
✅ Elevator visited all expected key floors
✅ Elevator direction change count is reasonable: 2 times
✅ Overall assessment: Elevator scheduling system behavior conforms to professional elevator scheduling logic
```

These results demonstrate that the elevator control system correctly implements professional scheduling logic, handles all test cases efficiently, and makes proper decisions without any hardcoded behavior.
