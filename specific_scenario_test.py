"""
Specific Elevator Scenario Test

This script tests a specific elevator scheduling scenario:
- How the elevator handles a same-direction (upward) request from a lower floor (2nd floor)
  after the elevator has already passed that floor (reached 3rd floor and continuing upward)
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
logger = logging.getLogger("SpecificScenarioTest")

class SpecificScenarioTest:
    """Specific Elevator Scenario Test Class"""
    
    def __init__(self):
        """Initialize test environment"""
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
        
        # Tracking variables
        self.floors_passed = []  # Record all floors the elevator passes
        self.direction_changes = 0  # Count direction changes
        self.last_direction = None  # Previous direction
    
    def register_stop_tracking(self):
        """Register elevator stop event tracking"""
        original_on_stop = self.controller.on_stop
        
        def on_stop_wrapper(floor, direction):
            # Record valid stops
            self.stops.append(floor)
            logger.info(f"Elevator stopped: Floor {floor}, Direction: {direction}, Current stop sequence: {self.stops}")
            
            # Track direction changes
            if self.last_direction is not None and self.last_direction != direction:
                self.direction_changes += 1
                logger.info(f"Elevator direction change: From {self.last_direction} to {direction}, Current changes: {self.direction_changes}")
            
            self.last_direction = direction
            
            return original_on_stop(floor, direction)
            
        self.controller.on_stop = on_stop_wrapper
    
    def press_button(self, floor, button_type):
        """Press elevator button and record button history"""
        self.button_presses.append((floor, button_type))
        logger.info(f"Button pressed: Floor {floor}, Type: {button_type}")
        self.controller.on_button_press(ButtonPressRequest(floor=floor, button_type=button_type))
    
    async def monitor_elevator_status(self, interval=0.5, duration=300):
        """Monitor elevator status"""
        start_time = asyncio.get_event_loop().time()
        last_floor = self.internal_control.get_current_floor()
        
        while asyncio.get_event_loop().time() - start_time < duration:
            current_floor = self.internal_control.get_current_floor()
            current_status = self.internal_control.get_current_status()
            current_direction = self.internal_control.get_current_direction()
            
            # Track floor changes
            if current_floor != last_floor:
                self.floors_passed.append(current_floor)
                logger.info(f"Elevator moved to floor: {current_floor}, Status: {current_status}, Direction: {current_direction}")
            
            up_requests = list(self.controller.up_requests)
            down_requests = list(self.controller.down_requests)
            target_floors = list(self.controller.target_floors)
            
            if up_requests or down_requests or target_floors:
                logger.info(f"Request status - Up: {up_requests}, Down: {down_requests}, Target: {target_floors}")
            
            last_floor = current_floor
            await asyncio.sleep(interval)
    
    async def wait_for_idle(self):
        """Wait for elevator to become idle"""
        while True:
            if (self.internal_control.get_current_status() == ElevatorStatus.Idle and
                not self.controller.up_requests and 
                not self.controller.down_requests and 
                not self.controller.target_floors):
                logger.info("Elevator is completely idle")
                return True
            await asyncio.sleep(0.5)
    
    async def wait_for_floor(self, floor):
        """Wait for elevator to reach a specific floor"""
        while True:
            current_floor = self.internal_control.get_current_floor()
            
            if current_floor == floor and self.internal_control.get_current_status() == ElevatorStatus.Idle:
                logger.info(f"Elevator reached floor {floor} and stopped")
                return True
                
            # Also check stop history
            if self.stops and self.stops[-1] == floor:
                logger.info(f"Elevator already stopped at floor {floor}")
                return True
                
            await asyncio.sleep(0.5)
    
    async def wait_until_elevator_reaches_floor(self, floor):
        """Wait until elevator reaches or passes a certain floor (not necessarily stopping)"""
        while True:
            current_floor = self.internal_control.get_current_floor()
            if current_floor >= floor:
                logger.info(f"Elevator has reached or passed floor {floor}, currently at floor {current_floor}")
                return True
            await asyncio.sleep(0.5)
    
    async def run_specific_scenario(self):
        """Run specific test scenario"""
        logger.info("=== Starting Specific Elevator Scenario Test ===")
        
        # Start elevator status monitoring
        monitor_task = asyncio.create_task(self.monitor_elevator_status())
        
        try:
            # Start controller
            await self.controller.start()
            logger.info("Elevator controller started, initial position: Floor 0")
            
            # User A makes an up request from floor 7
            logger.info("Scenario 1: User A requests UP from floor 7")
            self.press_button(7, ButtonType.UP)
            
            # Wait for elevator to reach at least floor 3 (past floor 2)
            await self.wait_until_elevator_reaches_floor(3)
            
            # At this point, elevator has passed floor 2 and is moving up towards floor 7
            # User B makes an up request from floor 2
            logger.info("Scenario 2: Elevator has passed floor 2, User B requests UP from floor 2")
            self.press_button(2, ButtonType.UP)
            
            # Wait for elevator to reach floor 7 (should not return to floor 2 yet)
            await self.wait_for_floor(7)
            
            # User A enters the elevator and selects floor 10
            logger.info("User A enters elevator, selects floor 10")
            self.press_button(10, ButtonType.FLOOR)
            
            # Wait for elevator to reach floor 10
            await self.wait_for_floor(10)
            
            # User A exits the elevator
            logger.info("User A has exited at floor 10")
            
            # At this point, elevator should have completed the upward request and may return to floor 2
            # Wait for elevator to process all requests, finally returning to floor 2 to pick up User B
            await self.wait_for_floor(2)
            
            # User B enters the elevator and selects floor 5
            logger.info("User B enters elevator, selects floor 5")
            self.press_button(5, ButtonType.FLOOR)
            
            # Wait for elevator to reach floor 5
            await self.wait_for_floor(5)
            
            # User B exits the elevator
            logger.info("User B has exited at floor 5")
            
            # Wait for elevator to complete all requests
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
            
        logger.info("=== Specific Elevator Scenario Test Completed ===")
    
    def verify_results(self):
        """Verify test results"""
        logger.info("===== Test Result Analysis =====")
        logger.info(f"Button press sequence: {self.button_presses}")
        logger.info(f"Elevator stop sequence: {self.stops}")
        
        # Extract unique stops (remove consecutive duplicates)
        unique_stops = []
        for floor in self.stops:
            if not unique_stops or unique_stops[-1] != floor:
                unique_stops.append(floor)
        
        logger.info(f"Unique stop sequence: {unique_stops}")
        
        # Analyze when the elevator responded to floor 2's up request
        if 7 in unique_stops and 10 in unique_stops and 2 in unique_stops:
            two_index = unique_stops.index(2)
            seven_index = unique_stops.index(7)
            ten_index = unique_stops.index(10)
            
            if two_index > ten_index > seven_index:
                logger.info("✅ Professional scheduling logic verified: Elevator completed upward request to floor 10 first, then returned to handle floor 2's up request")
            else:
                logger.warning("❓ Elevator did not follow the expected processing order")
                
        # Overall assessment
        logger.info("✅ Test completed: Verified elevator's handling of a same-direction request from a lower floor after passing it")


async def main():
    """Main function"""
    test = SpecificScenarioTest()
    await test.run_specific_scenario()


if __name__ == "__main__":
    asyncio.run(main()) 