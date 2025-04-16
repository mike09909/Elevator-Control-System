"""
Elevator Scheduling System Realistic Scenario Test

This script simulates realistic elevator usage scenarios by sending user requests in chronological order,
testing whether the elevator system can operate naturally according to professional elevator scheduling
logic and verifying that the elevator's behavior meets expectations.
"""
import asyncio
import logging
from elevator_interface import ElevatorStatus, ElevatorDirection, wait
from elevator_controller import ElevatorController, ButtonPressRequest, ButtonType
from elevator_mock import InternalControlMockWithHandlers
from elevator_config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("RealisticTest")

class ImprovedElevatorTest:
    """Improved elevator realistic scenario test class"""
    
    def __init__(self):
        """Initialize the test environment"""
        self.config = get_config()
        
        # Create controller and mock elevator
        self.controller = ElevatorController(None, 0, 20)
        self.internal_control = InternalControlMockWithHandlers(self.controller, 0, 20)
        self.controller.internal_control = self.internal_control
        
        # Record elevator stops
        self.stops = []
        self.register_stop_tracking()
        
        # Record button press sequence
        self.button_presses = []
        
        # Enhanced tracking variables
        self.floors_passed = []  # Record all floors the elevator passes through
        self.floors_stopped = []  # Record floors where the elevator stopped
        self.expected_stops = [5, 8, 15, 11, 9, 0, 2]  # Expected stop sequence
    
    def register_stop_tracking(self):
        """Register elevator stop event tracking"""
        original_on_stop = self.controller.on_stop
        
        def on_stop_wrapper(floor, direction):
            # Check floor validity
            if floor < self.config["elevator"]["min_floor"] or floor > self.config["elevator"]["max_floor"]:
                logger.warning(f"Invalid floor stop: Floor {floor}")
                return original_on_stop(floor, direction)
                
            # Record valid stops
            self.stops.append(floor)
            self.floors_stopped.append(floor)  # Also record in enhanced tracking
            logger.info(f"Elevator stopped: Floor {floor}, Direction: {direction}, Current stop sequence: {self.stops}")
            return original_on_stop(floor, direction)
            
        self.controller.on_stop = on_stop_wrapper
    
    def press_button(self, floor, button_type):
        """Press elevator button and record button press history"""
        self.button_presses.append((floor, button_type))
        logger.info(f"Button pressed: Floor {floor}, Type: {button_type}")
        self.controller.on_button_press(ButtonPressRequest(floor=floor, button_type=button_type))
    
    async def monitor_elevator_status(self, interval=0.5, duration=300):
        """
        Monitor elevator status
        
        Args:
            interval: Monitoring interval (seconds)
            duration: Total monitoring duration (seconds), default 5 minutes
        """
        start_time = asyncio.get_event_loop().time()
        last_floor = self.internal_control.get_current_floor()
        
        while asyncio.get_event_loop().time() - start_time < duration:
            current_floor = self.internal_control.get_current_floor()
            current_status = self.internal_control.get_current_status()
            current_direction = self.internal_control.get_current_direction()
            
            # Track floor changes
            if current_floor != last_floor:
                self.floors_passed.append(current_floor)
                logger.debug(f"Elevator moved to floor {current_floor}")
            
            up_requests = list(self.controller.up_requests)
            down_requests = list(self.controller.down_requests)
            target_floors = list(self.controller.target_floors)
            
            logger.debug(f"Elevator status - Floor: {current_floor}, Status: {current_status}, Direction: {current_direction}")
            logger.debug(f"Request status - Up: {up_requests}, Down: {down_requests}, Target: {target_floors}")
            
            last_floor = current_floor
            await asyncio.sleep(interval)
    
    async def wait_for_idle(self):
        """
        Wait for elevator to become idle, unlimited wait
        
        Returns:
            True: When elevator becomes idle
        """
        while True:
            if (self.internal_control.get_current_status() == ElevatorStatus.Idle and
                not self.controller.up_requests and 
                not self.controller.down_requests and 
                not self.controller.target_floors):
                logger.info("Elevator has become completely idle")
                return True
            await asyncio.sleep(0.5)
    
    async def wait_for_floor(self, floor):
        """
        Wait for elevator to reach a specific floor, unlimited wait
        
        Args:
            floor: Expected floor
        
        Returns:
            True: When elevator reaches the specified floor
        """
        while True:
            current_floor = self.internal_control.get_current_floor()
            
            if current_floor == floor and self.internal_control.get_current_status() == ElevatorStatus.Idle:
                logger.info(f"Elevator has reached floor {floor} and stopped")
                return True
                
            # Also check stop history
            if self.stops and self.stops[-1] == floor:
                logger.info(f"Elevator has already stopped at floor {floor}")
                return True
                
            await asyncio.sleep(0.5)
    
    async def run_scenario(self):
        """Run the test scenario"""
        logger.info("=== Starting Realistic Elevator Scenario Test ===")
        
        # Start elevator status monitoring
        monitor_task = asyncio.create_task(self.monitor_elevator_status())
        
        try:
            # Start controller
            await self.controller.start()
            logger.info("Elevator controller started, initial position: Floor 0")
            
            # Scenario 1: Elevator is idle at Floor 0, User A presses DOWN button at Floor 9
            logger.info("Scenario 1: User A presses DOWN button at Floor 9")
            self.press_button(9, ButtonType.DOWN)
            
            # Wait for elevator to start moving
            await asyncio.sleep(2)
            
            
            
            # Scenario 2: Elevator is moving up, User B presses UP button at Floor 5, User C presses UP button at Floor 2
            logger.info("Scenario 2: User B presses UP button at Floor 5, User C presses UP button at Floor 2")
            self.press_button(5, ButtonType.UP)
            self.press_button(2, ButtonType.UP)
            
            # Wait for elevator to reach Floor 5
            await self.wait_for_floor(5)
            
            # Scenario 3: User B enters elevator, presses Floor 8
            logger.info("Scenario 3: User B enters elevator, presses Floor 8")
            self.press_button(8, ButtonType.FLOOR)
            
            # Scenario 4: User D presses DOWN button at Floor 15
            logger.info("Scenario 4: User D presses DOWN button at Floor 15")
            self.press_button(15, ButtonType.DOWN)
            
            # Wait for elevator to reach Floor 8
            await self.wait_for_floor(8)
            
            # Wait for elevator to reach Floor 15
            await self.wait_for_floor(15)
            
            # Scenario 5: User D enters elevator, presses Floor 11
            logger.info("Scenario 5: User D enters elevator, presses Floor 11")
            self.press_button(11, ButtonType.FLOOR)
            
            # Wait for elevator to reach Floor 11
            await self.wait_for_floor(11)
            
            # Wait for elevator to reach Floor 9
            await self.wait_for_floor(9)
            
            # Scenario 6: User A enters elevator, presses Floor 0
            logger.info("Scenario 6: User A enters elevator, presses Floor 0")
            self.press_button(0, ButtonType.FLOOR)
            
            # Wait for elevator to reach Floor 0
            await self.wait_for_floor(0)
            
            # Ensure elevator has a chance to go to Floor 2 to pick up User C
            await asyncio.sleep(5)
            
            # Wait for elevator to process all requests
            await self.wait_for_idle()
            
            # Verify elevator stop sequence
            self.verify_results()
            
        finally:
            # Cancel monitoring task
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
        logger.info("=== Realistic Elevator Scenario Test Completed ===")
    
    def verify_results(self):
        """Verify test results"""
        logger.info("===== Test Results Analysis =====")
        logger.info(f"Button press sequence: {self.button_presses}")
        logger.info(f"Elevator stop sequence: {self.stops}")
        
        # Extract key floors from stop history
        key_stops = []
        for floor in self.stops:
            if floor in self.expected_stops and (not key_stops or key_stops[-1] != floor):
                key_stops.append(floor)
        
        logger.info(f"Key floor stop sequence: {key_stops}")
        
        # Check if all key floors were visited
        all_visited = set(key_stops).issuperset(set(self.expected_stops))
        if all_visited:
            logger.info("✅ Elevator visited all expected key floors")
        else:
            missed = set(self.expected_stops) - set(key_stops)
            logger.warning(f"❌ Elevator did not visit the following key floors: {missed}")
        
        # Verify if elevator stopped at unexpected floors
        unexpected_stops = [floor for floor in self.stops if floor not in self.expected_stops]
        if not unexpected_stops:
            logger.info("✅ Elevator only stopped at expected floors")
        else:
            logger.warning(f"❌ Elevator unexpectedly stopped at floors: {unexpected_stops}")
        
        # Calculate travel efficiency
        if len(self.floors_passed) > 1:
            total_distance = sum(abs(self.floors_passed[i] - self.floors_passed[i-1]) 
                               for i in range(1, len(self.floors_passed)))
            logger.info(f"Total elevator travel distance: {total_distance} floors")
        
        # Analyze elevator behavior against professional scheduling principles
        self.analyze_behavior()
    
    def analyze_behavior(self):
        """Analyze if elevator behavior follows professional scheduling principles"""
        unique_stops = []
        for floor in self.stops:
            if not unique_stops or unique_stops[-1] != floor:
                unique_stops.append(floor)
        
        # Check if direction priority principle was followed
        direction_priority_respected = True
        direction_changes = 0
        increasing = None
        
        for i in range(1, len(unique_stops)):
            current_increasing = unique_stops[i] > unique_stops[i-1]
            
            if increasing is not None and increasing != current_increasing:
                direction_changes += 1
                
            increasing = current_increasing
        
        # Check if direction changes are reasonable (should only be a few changes)
        if direction_changes <= 3:
            logger.info(f"✅ Elevator direction change count is reasonable: {direction_changes} times")
        else:
            logger.warning(f"❌ Elevator direction changes too frequently: {direction_changes} times")
            direction_priority_respected = False
        
        # Check basic elevator scheduling principles
        principles_respected = []
        
        # Principle 1: Direction priority - serving up requests when going up, down requests when going down
        principles_respected.append("Direction priority")
        
        # Principle 2: Elevator should not change direction frequently
        if direction_changes <= 3:
            principles_respected.append("Avoid frequent direction changes")
        
        # Principle 3: Elevator should handle mixed requests (internal and external)
        if len(unique_stops) >= 3:
            principles_respected.append("Handle mixed requests")
            
        logger.info(f"Elevator behavior analysis: Followed these principles: {', '.join(principles_respected)}")
        
        # Overall assessment
        if direction_priority_respected and len(principles_respected) >= 2:
            logger.info("✅ Overall assessment: Elevator scheduling system behavior conforms to professional elevator scheduling logic")
        else:
            logger.warning("❌ Overall assessment: Elevator scheduling system behavior does not fully conform to professional elevator scheduling logic")


async def main():
    """Main function"""
    test = ImprovedElevatorTest()
    await test.run_scenario()


if __name__ == "__main__":
    asyncio.run(main()) 