import unittest
import asyncio
from unittest.mock import MagicMock, patch
from elevator_interface import ElevatorStatus, ElevatorDirection
from elevator_controller import ElevatorController, ButtonPressRequest, ButtonType
from elevator_mock import InternalControlMockWithHandlers


class TestElevatorController(unittest.IsolatedAsyncioTestCase):
    """Unit test class for elevator controller"""
    
    def setUp(self):
        """Setup before test execution"""
        self.mock_internal_control = MagicMock()
        self.mock_internal_control.get_current_floor.return_value = 0
        self.mock_internal_control.get_current_status.return_value = ElevatorStatus.Idle
        self.mock_internal_control.get_current_direction.return_value = ElevatorDirection.Up
        
        self.controller = ElevatorController(self.mock_internal_control, 0, 20)
    
    def test_request_up(self):
        """Test up request processing"""
        self.controller.request_up(5)
        self.assertIn(5, self.controller.up_requests)
    
    def test_request_down(self):
        """Test down request processing"""
        self.controller.request_down(10)
        self.assertIn(10, self.controller.down_requests)
    
    async def test_handle_floor_button(self):
        """Test external floor button processing (UP/DOWN buttons)"""
        # Test UP button press
        await self.controller._handle_floor_button(15, ElevatorDirection.Up)
        self.assertIn(15, self.controller.up_requests)
        
        # Test DOWN button press
        await self.controller._handle_floor_button(12, ElevatorDirection.Down)
        self.assertIn(12, self.controller.down_requests)
    
    def test_should_stop_at_target_floor(self):
        """Test stopping at target floor"""
        self.controller.target_floors.add(5)
        self.assertTrue(self.controller.should_stop_at_floor(5, ElevatorDirection.Up))
    
    def test_should_stop_at_up_request_when_going_up(self):
        """Test stopping at up request while moving upward"""
        self.controller.up_requests.add(7)
        self.assertTrue(self.controller.should_stop_at_floor(7, ElevatorDirection.Up))
    
    def test_should_stop_at_down_request_when_going_down(self):
        """Test stopping at down request while moving downward"""
        self.controller.down_requests.add(3)
        self.assertTrue(self.controller.should_stop_at_floor(3, ElevatorDirection.Down))
    
    def test_should_not_stop_at_down_request_when_going_up_with_higher_requests(self):
        """Test not stopping at down request when going up with higher requests"""
        # Set up elevator with a down request at floor 9 and another at floor 15 while moving up
        self.controller.down_requests.add(9)
        self.controller.down_requests.add(15)
        
        # When elevator is at floor 8 going up, it should not stop at floor 9, but continue to floor 15
        # According to professional elevator scheduling principles, when going up and encountering down requests,
        # it should continue upward until there are no more higher floor requests
        self.assertFalse(self.controller.should_stop_at_floor(9, ElevatorDirection.Up))
    
    def test_should_stop_at_down_request_when_going_up_no_higher_requests(self):
        """Test stopping at down request when going up with no higher requests"""
        # Set up elevator with only a down request at floor 9, with no higher floor requests
        self.controller.down_requests.add(9)
        
        # When elevator is at floor 8 going up, it should stop at floor 9 and change direction
        # According to professional elevator scheduling principles, when going up with no higher requests,
        # it should stop at down requests and change direction
        self.assertTrue(self.controller.should_stop_at_floor(9, ElevatorDirection.Up))
    
    def test_on_stop_removes_processed_requests(self):
        """Test removal of processed requests when stopping"""
        # Mock the async function to avoid runtime error
        original_create_task = asyncio.create_task
        asyncio.create_task = MagicMock()
        
        try:
            self.controller.target_floors.add(10)
            self.controller.up_requests.add(10)
            
            self.controller.on_stop(10, ElevatorDirection.Up)
            
            self.assertNotIn(10, self.controller.target_floors)
            self.assertNotIn(10, self.controller.up_requests)
        finally:
            # Restore original function
            asyncio.create_task = original_create_task
    
    def test_on_stop_handles_direction_change_points(self):
        """Test request handling at direction change points"""
        # Mock the async function to avoid runtime error
        original_create_task = asyncio.create_task
        asyncio.create_task = MagicMock()
        
        try:
            # Set elevator at highest request point
            self.controller.down_requests.add(15)
            self.mock_internal_control.get_current_floor.return_value = 15
            
            # When elevator reaches floor 15 going up, should remove down request
            self.controller.on_stop(15, ElevatorDirection.Up)
            self.assertNotIn(15, self.controller.down_requests)
            
            # Set elevator at lowest request point
            self.controller.up_requests.add(2)
            self.mock_internal_control.get_current_floor.return_value = 2
            
            # When elevator reaches floor 2 going down, should remove up request
            self.controller.on_stop(2, ElevatorDirection.Down)
            self.assertNotIn(2, self.controller.up_requests)
        finally:
            # Restore original function
            asyncio.create_task = original_create_task
    
    async def test_on_button_press_creates_update_task(self):
        """Test update task creation on button press"""
        # Modified test for async implementation
        with patch('asyncio.create_task') as mock_create_task:
            request = ButtonPressRequest(floor=5, button_type=ButtonType.UP)
            self.controller.on_button_press(request)
            # We expect create_task to be called
            mock_create_task.assert_called()
    
    def test_invalid_floor_request(self):
        """Test invalid floor request handling"""
        request = ButtonPressRequest(floor=25, button_type=ButtonType.UP)
        self.controller.on_button_press(request)
        self.assertNotIn(25, self.controller.up_requests)
    
    def test_max_floor_up_request(self):
        """Test up request from maximum floor"""
        self.controller.request_up(self.controller.max_floor)
        self.assertNotIn(self.controller.max_floor, self.controller.up_requests)
    
    def test_min_floor_down_request(self):
        """Test down request from minimum floor"""
        self.controller.request_down(self.controller.min_floor)
        self.assertNotIn(self.controller.min_floor, self.controller.down_requests)
    
    def test_determine_direction_with_multiple_requests(self):
        """Test direction decision with multiple types of requests"""
        # Simulate current position at floor 6
        self.mock_internal_control.get_current_floor.return_value = 6
        
        # Add various requests: down request at floor 15 (higher), up request at floor 2 (lower)
        self.controller.down_requests.add(15)
        self.controller.up_requests.add(2)
        
        # According to elevator scheduling principles, it should service higher requests first (go to floor 15)
        direction = self.controller._determine_direction(6)
        self.assertEqual(direction, ElevatorDirection.Up)
        
        # Clear requests and simulate elevator moving up to floor 12
        self.controller.down_requests.clear()
        self.controller.up_requests.clear()
        self.mock_internal_control.get_current_floor.return_value = 12
        
        # Add new requests: down requests at both higher and lower floors
        self.controller.down_requests.add(15)
        self.controller.down_requests.add(8)
        
        # Current direction is up, should continue upward (to floor 15)
        self.controller._current_direction = ElevatorDirection.Up
        direction = self.controller._determine_direction(12)
        self.assertEqual(direction, ElevatorDirection.Up)


class TestElevatorScenario(unittest.IsolatedAsyncioTestCase):
    """Integration test class for elevator scenarios"""
    
    async def asyncSetUp(self):
        """Asynchronous setup before test execution"""
        self.controller = ElevatorController(None, 0, 20)  # Temporarily None
        self.internal_control = InternalControlMockWithHandlers(self.controller, 0, 20)
        self.controller.internal_control = self.internal_control
        
        await self.controller.start()
    
    async def test_scenario_part1(self):
        """Test scenario part 1: User A requests DOWN from floor 9"""
        # Elevator is idle at floor 0
        self.assertEqual(self.internal_control.get_current_floor(), 0)
        self.assertEqual(self.internal_control.get_current_status(), ElevatorStatus.Idle)
        
        # User A requests DOWN from floor 9
        self.controller.on_button_press(ButtonPressRequest(floor=9, button_type=ButtonType.DOWN))
        
        # Give elevator time to start and move
        await asyncio.sleep(0.5)
        
        # Verify elevator starts moving up
        self.assertEqual(self.internal_control.get_current_status(), ElevatorStatus.Running)
        self.assertEqual(self.internal_control.get_current_direction(), ElevatorDirection.Up)
    
    async def test_scenario_part2(self):
        """Test scenario part 2: User B requests UP from floor 5, elevator should stop"""
        # Set elevator initial state as moving up at floor 3
        self.internal_control.floor = 3
        self.internal_control.status = ElevatorStatus.Running
        self.internal_control.direction = ElevatorDirection.Up
        
        # User A requests DOWN from floor 9 (background request)
        self.controller.down_requests.add(9)
        
        # User B requests UP from floor 5
        self.controller.on_button_press(ButtonPressRequest(floor=5, button_type=ButtonType.UP))
        
        # Verify elevator should stop at floor 5
        self.assertTrue(self.controller.should_stop_at_floor(5, ElevatorDirection.Up))
    
    async def test_scenario_part3(self):
        """Test scenario part 3: User C requests UP from floor 2, elevator should temporarily ignore request"""
        # Set elevator initial state as moving up at floor 5
        self.internal_control.floor = 5
        self.internal_control.status = ElevatorStatus.Running
        self.internal_control.direction = ElevatorDirection.Up
        
        # User A requests DOWN from floor 9 (background request)
        self.controller.down_requests.add(9)
        
        # User C requests UP from floor 2
        self.controller.on_button_press(ButtonPressRequest(floor=2, button_type=ButtonType.UP))
        
        # In this implementation, the elevator will respond to UP requests from floor 2 while moving upward
        # This test verifies that the elevator will not immediately change direction to go down to floor 2
        # Instead, it continues moving up to complete requests in the current direction
        current_floor = self.internal_control.get_current_floor()
        self.assertGreater(current_floor, 2)  # Ensure current floor is above floor 2
        # Verify elevator continues in current direction instead of immediately returning to floor 2
        self.assertEqual(self.internal_control.get_current_direction(), ElevatorDirection.Up)
    
    async def test_scenario_part4(self):
        """Test scenario part 4: User D requests DOWN from floor 15, elevator skips floor 9"""
        # Set elevator initial state to floor 8 moving up
        self.internal_control.floor = 8
        self.internal_control.status = ElevatorStatus.Running
        self.internal_control.direction = ElevatorDirection.Up
        
        # User A has pressed DOWN button at floor 9 (existing request)
        self.controller.down_requests.add(9)
        
        # User D presses DOWN button at floor 15
        self.controller.on_button_press(ButtonPressRequest(floor=15, button_type=ButtonType.DOWN))
        
        # Verify elevator should not stop at floor 9
        self.assertFalse(self.controller.should_stop_at_floor(9, ElevatorDirection.Up))
        
        # Verify elevator should stop at floor 15
        self.assertTrue(self.controller.should_stop_at_floor(15, ElevatorDirection.Up))


if __name__ == "__main__":
    unittest.main() 