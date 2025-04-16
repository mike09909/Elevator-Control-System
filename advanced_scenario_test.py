"""
Advanced Elevator Scenario Test

This script tests complex elevator scheduling scenarios:
1. Testing late requests from lower floors while elevator is already moving up
2. Testing complete up->down->up cycle with multiple direction changes
3. Testing that elevator completes the full journey to floor 0
"""
import asyncio
import logging
import signal
import sys
import time
from elevator_interface import ElevatorStatus, ElevatorDirection, wait
from elevator_controller import ElevatorController, ButtonPressRequest, ButtonType
from elevator_mock import InternalControlMockWithHandlers
from elevator_config import get_config

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ElevatorTest")

# Add signal handler to gracefully terminate
def signal_handler(sig, frame):
    logger.info("Test interrupted, shutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

class SimplifiedElevatorTest:
    """Simplified Elevator Test Class focusing on key scenarios"""
    
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
        self.direction_changes = 0  # Count direction changes
        self.last_direction = None  # Previous direction
        
        # Set a test timeout for safety
        self.test_timeout = 120  # seconds
    
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
                logger.info(f"⚠️ Elevator direction change: From {self.last_direction} to {direction}, Current changes: {self.direction_changes}")
            
            self.last_direction = direction
            
            return original_on_stop(floor, direction)
            
        self.controller.on_stop = on_stop_wrapper
    
    def press_button(self, floor, button_type):
        """Press elevator button and record button history"""
        self.button_presses.append((floor, button_type))
        logger.info(f"🔘 Button pressed: Floor {floor}, Type: {button_type}")
        self.controller.on_button_press(ButtonPressRequest(floor=floor, button_type=button_type))
    
    async def monitor_elevator_status(self, interval=0.3):
        """Monitor elevator status"""
        start_time = time.time()
        last_floor = self.internal_control.get_current_floor()
        
        while time.time() - start_time < self.test_timeout:
            current_floor = self.internal_control.get_current_floor()
            current_status = self.internal_control.get_current_status()
            current_direction = self.internal_control.get_current_direction()
            
            # Track floor changes
            if current_floor != last_floor:
                logger.info(f"Elevator moved to floor: {current_floor}, Status: {current_status}, Direction: {current_direction}")
            
            up_requests = list(self.controller.up_requests)
            down_requests = list(self.controller.down_requests)
            target_floors = list(self.controller.target_floors)
            
            if up_requests or down_requests or target_floors:
                logger.info(f"Request status - Up: {up_requests}, Down: {down_requests}, Target: {target_floors}")
            
            last_floor = current_floor
            await asyncio.sleep(interval)
        
        logger.warning("Test monitor timeout reached!")
    
    async def wait_for_idle(self, timeout=5):
        """Wait for elevator to become idle"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            if (self.internal_control.get_current_status() == ElevatorStatus.Idle and
                not self.controller.up_requests and 
                not self.controller.down_requests and 
                not self.controller.target_floors):
                logger.info("Elevator is completely idle")
                return True
            await asyncio.sleep(0.3)
        logger.warning("Timeout waiting for idle elevator")
        return False
    
    async def wait_for_floor(self, floor, timeout=30):
        """Wait for elevator to reach a specific floor and stop"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_floor = self.internal_control.get_current_floor()
            
            if current_floor == floor and self.internal_control.get_current_status() == ElevatorStatus.Idle:
                logger.info(f"✅ Elevator reached floor {floor} and stopped")
                await asyncio.sleep(0.5)  # Small delay to ensure we're stable
                return True
                
            # Also check stop history
            if self.stops and self.stops[-1] == floor:
                logger.info(f"✅ Elevator already stopped at floor {floor}")
                return True
                
            await asyncio.sleep(0.3)
            
        logger.warning(f"Timeout waiting for elevator to reach floor {floor}")
        return False
    
    async def wait_until_floor_passed(self, floor, direction=None, timeout=15):
        """Wait until elevator passes a specific floor going in a specific direction"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            current_floor = self.internal_control.get_current_floor()
            current_direction = self.internal_control.get_current_direction()
            
            if direction is None or current_direction == direction:
                if (direction == ElevatorDirection.Up and current_floor > floor) or \
                   (direction == ElevatorDirection.Down and current_floor < floor) or \
                   (direction is None and (current_floor > floor or current_floor < floor)):
                    logger.info(f"Elevator has passed floor {floor}, now at floor {current_floor}")
                    return True
            
            await asyncio.sleep(0.2)
            
        logger.warning(f"Timeout waiting for elevator to pass floor {floor}")
        return False
    
    async def run_test(self):
        """Run simplified test focusing on key scenarios"""
        logger.info("=== Starting Simplified Elevator Test ===")
        
        # Start elevator status monitoring
        monitor_task = asyncio.create_task(self.monitor_elevator_status())
        
        try:
            # Start controller
            await self.controller.start()
            logger.info("Elevator controller started, initial position: Floor 0")
            
            # Test 1: Simple up-down cycle with late request
            await self.test_late_request_scenario()
            
            # Verify results
            self.verify_results()
            
        except Exception as e:
            logger.error(f"Test failed with error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # Cancel monitoring task
            monitor_task.cancel()
            try:
                await monitor_task
            except asyncio.CancelledError:
                pass
            
            # Terminate the test
            logger.info("=== Elevator Test Completed ===")
    
    async def test_late_request_scenario(self):
        """Test scenario with late requests and full up-down-up cycle"""
        logger.info("=== Testing Late Request Scenario ===")
        
        # Phase 1: Initial state - Elevator at ground floor
        logger.info("Phase 1: Initial UP journey")
        
        # Event 1: User at floor 7 presses UP button
        logger.info("Event 1: User at floor 7 presses UP button")
        self.press_button(7, ButtonType.UP)
        
        # Wait for elevator to start moving up
        await asyncio.sleep(1)
        
        # Event 2: When elevator is passing floor 3, user at floor 2 presses UP button
        await self.wait_until_floor_passed(3, ElevatorDirection.Up)
        logger.info("Event 2: User at floor 2 presses UP button when elevator is already above")
        self.press_button(2, ButtonType.UP)
        
        # Wait for elevator to reach floor 7
        await self.wait_for_floor(7)
        
        # Event 3: User at floor 7 enters and presses button for floor 15
        logger.info("Event 3: User from floor 7 enters and presses button for floor 15")
        self.press_button(15, ButtonType.FLOOR)
        
        # Event 4: While elevator is moving up, user at floor 18 presses DOWN button
        await asyncio.sleep(2)  # Give elevator time to start moving
        logger.info("Event 4: User at floor 18 presses DOWN button")
        self.press_button(18, ButtonType.DOWN)
        
        # Wait for elevator to reach floor 15
        await self.wait_for_floor(15)
        
        # Event 5: User at floor 15 exits, another user enters and presses button for floor 20
        logger.info("Event 5: New user at floor 15 enters and presses button for floor 20")
        self.press_button(20, ButtonType.FLOOR)
        
        # Wait for elevator to reach floor 18 (for DOWN request)
        await self.wait_for_floor(18)
        
        # Event 6: User at floor 18 enters and presses button for floor 0 (ground floor)
        logger.info("Event 6: User from floor 18 enters and presses button for floor 0")
        self.press_button(0, ButtonType.FLOOR)
        
        # Wait for elevator to reach floor 20
        await self.wait_for_floor(20)
        
        # Phase 2: Elevator moving DOWN journey
        logger.info("Phase 2: DOWN journey")
        
        # Wait for elevator to reach floor 2 (delayed UP request)
        await self.wait_for_floor(2)
        
        # Event 7: User at floor 2 enters and presses button for floor 10
        logger.info("Event 7: User from floor 2 enters and presses button for floor 10")
        self.press_button(10, ButtonType.FLOOR)
        
        # Wait for elevator to reach floor 0
        await self.wait_for_floor(0)
        
        # Phase 3: Elevator should now go UP to floor 10
        logger.info("Phase 3: Final UP journey")
        
        # Wait for elevator to reach floor 10
        await self.wait_for_floor(10)
        
        # Ensure we're idle before concluding
        await self.wait_for_idle()
        logger.info("=== Late Request Scenario Completed ===")
    
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
        
        # Check for key floors
        expected_floors = [0, 7, 15, 18, 20, 2, 0, 10]
        missing_floors = [f for f in expected_floors if f not in unique_stops]
        
        if not missing_floors:
            logger.info(f"✅ Elevator stopped at all expected floors")
        else:
            logger.warning(f"❌ Elevator missed expected floors: {missing_floors}")
        
        # Check direction changes: should have at least 2 (UP->DOWN->UP)
        if self.direction_changes >= 2:
            logger.info(f"✅ Elevator changed direction {self.direction_changes} times as expected")
        else:
            logger.warning(f"❌ Elevator did not change direction enough times: {self.direction_changes}")
        
        # Check for the critical test cases
        test_results = []
        
        # Test 1: Did elevator handle the late UP request from floor 2?
        if 2 in unique_stops:
            test_results.append("✅ Elevator handled late UP request from floor 2")
        else:
            test_results.append("❌ Elevator failed to handle late UP request from floor 2")
            
        # Test 2: Did elevator reach floor 0 after picking up the DOWN request from floor 18?
        try:
            idx_18 = unique_stops.index(18)
            idx_0 = unique_stops.index(0)
            if idx_0 > idx_18:
                test_results.append("✅ Elevator properly serviced the 18->0 request")
            else:
                test_results.append("❌ Elevator failed to properly service the 18->0 request")
        except ValueError:
            test_results.append("❌ Couldn't verify 18->0 request due to missing floors")
            
        # Test 3: Did elevator complete the final UP journey to floor 10?
        try:
            idx_0 = unique_stops.index(0)
            idx_10 = unique_stops.index(10)
            if idx_10 > idx_0 and idx_10 == len(unique_stops) - 1:
                test_results.append("✅ Elevator completed final UP journey to floor 10")
            else:
                test_results.append("❌ Elevator failed to complete final UP journey to floor 10")
        except ValueError:
            test_results.append("❌ Couldn't verify final journey to floor 10 due to missing floors")
        
        for result in test_results:
            logger.info(result)
            
        # Overall assessment
        if all(result.startswith("✅") for result in test_results):
            logger.info("🎉 Overall assessment: Elevator passed all test cases!")
        else:
            logger.warning("⚠️ Overall assessment: Elevator failed some test cases")


async def main():
    """Main function"""
    # Set a global timeout for the entire script
    try:
        test = SimplifiedElevatorTest()
        await asyncio.wait_for(test.run_test(), timeout=120)
    except asyncio.TimeoutError:
        logger.error("Test timed out after 120 seconds!")
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    finally:
        logger.info("Test execution completed")
        # Force exit to ensure termination
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main()) 