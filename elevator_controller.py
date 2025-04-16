from enum import Enum
from typing import Set, Optional, Dict, List, Tuple, Callable, NoReturn, Any
import asyncio
import logging
from dataclasses import dataclass
from pydantic import BaseModel, validator

# Import existing base classes and interfaces
from elevator_interface import ElevatorStatus, ElevatorDirection, InternalControl

# Import configuration and constants
from elevator_config import SchedulingStrategy, get_config

# Get system configuration
CONFIG = get_config()

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("ElevatorSystem")

class ButtonType(Enum):
    """
    Enum for elevator button types.
    
    Attributes:
        FLOOR: Internal floor buttons inside the elevator
        UP: External up call buttons on each floor
        DOWN: External down call buttons on each floor
    """
    FLOOR = 'floor'  # Internal floor buttons
    UP = 'up'        # External up buttons
    DOWN = 'down'    # External down buttons


class ButtonPressRequest(BaseModel):
    """
    Model representing a button press request.
    
    Attributes:
        floor: The floor number where the button is pressed
        button_type: Type of button being pressed (default: FLOOR)
    """
    floor: int
    button_type: ButtonType = ButtonType.FLOOR
    
    @validator('floor')
    def validate_floor(cls, v: Any) -> int:
        """
        Validate that floor is an integer.
        
        Args:
            v: The floor value to validate
            
        Returns:
            The validated floor value
            
        Raises:
            ValueError: If floor is not an integer
        """
        if not isinstance(v, int):
            raise ValueError("Floor must be an integer")
        return v


@dataclass
class ElevatorRequest:
    """
    Data class representing an elevator request.
    
    Attributes:
        source_floor: The floor where the request originated
        target_floor: The destination floor (may be None for external requests initially)
        button_type: Type of button pressed
        direction: Direction of the request (derived from button type for UP/DOWN)
    """
    source_floor: int  # Source floor of the request
    target_floor: Optional[int] = None  # Target floor, may be None initially for external requests
    button_type: ButtonType = ButtonType.FLOOR  # Button type
    direction: Optional[ElevatorDirection] = None  # Request direction
    
    def __post_init__(self) -> None:
        """
        Post-initialization logic to set direction based on button type.
        """
        # Set direction based on button type for external buttons
        if self.button_type == ButtonType.UP:
            self.direction = ElevatorDirection.Up
        elif self.button_type == ButtonType.DOWN:
            self.direction = ElevatorDirection.Down


class ElevatorController:
    """
    Elevator controller class responsible for handling requests and scheduling.
    
    This class implements the elevator scheduling algorithm, processing button
    requests and determining elevator movement to efficiently serve passengers.
    """
    
    def __init__(self, internal_control: Optional[InternalControl] = None, 
                 min_floor: int = CONFIG["elevator"]["min_floor"], 
                 max_floor: int = CONFIG["elevator"]["max_floor"],
                 scheduling_strategy: str = SchedulingStrategy.LOOK.value) -> None:
        """
        Initialize the elevator controller.
        
        Args:
            internal_control: Reference to the elevator's internal control system
            min_floor: Minimum floor the elevator can reach
            max_floor: Maximum floor the elevator can reach
            scheduling_strategy: Strategy used for scheduling elevator movement
        """
        self.internal_control = internal_control
        self.min_floor = min_floor
        self.max_floor = max_floor
        
        # Get configuration
        self.CONFIG = get_config()
        
        # Initialize request sets
        self.up_requests: Set[int] = set()
        self.down_requests: Set[int] = set()
        self.target_floors: Set[int] = set()
        
        # Track elevator status
        self._is_running = False
        self._direction_conflict = False
        
        # Restore missing attributes
        self._current_direction = None
        self._last_target_floor = None
        self._subscribers = []
        
        # Set scheduling strategy
        self.scheduling_strategy = scheduling_strategy
        
        # Initialize logging
        details = f"min_floor={min_floor}, max_floor={max_floor}"
        logger.info(f"ElevatorController initialized with {details}")
        logger.info(f"Using scheduling strategy: {scheduling_strategy}")
    
    async def start(self) -> None:
        """
        Start the elevator controller and initialize elevator state.
        """
        logger.info("ElevatorController started")
        
        # Check for internal control
        if self.internal_control is None:
            logger.warning("No internal_control provided, elevator will not function properly")
            return
            
        # Initial state maintenance
        await self._update_direction()
    
    def on_button_press(self, request: ButtonPressRequest) -> None:
        """
        Handle button press events from any part of the elevator system.
        
        Args:
            request: The button press request containing floor and button type
        """
        logger.info(f"Button press event: floor={request.floor}, type={request.button_type}", 
                  extra={"floor": request.floor, "button_type": str(request.button_type)})
        
        # Validate floor is in range
        if not self._is_floor_in_range(request.floor):
            logger.warning(f"Invalid floor {request.floor} for button press")
            return
            
        # Process based on button type
        if request.button_type == ButtonType.UP:
            self.request_up(request.floor)
            # Schedule direction update if needed
            self._schedule_update_direction()
        elif request.button_type == ButtonType.DOWN:
            self.request_down(request.floor)
            # Schedule direction update if needed
            self._schedule_update_direction()
        elif request.button_type == ButtonType.FLOOR:
            # Handle internal floor button press
            self.target_floors.add(request.floor)
            logger.info(f"Added target floor: {request.floor}")
            # Schedule direction update if needed
            self._schedule_update_direction()
    
    async def _handle_floor_button(self, floor: int, direction: ElevatorDirection) -> None:
        """
        Handle a floor button press event.
        
        When a button is pressed on a floor panel, this method adds the floor
        to the appropriate request queue (up or down) and updates the elevator's
        direction if needed.
        
        Args:
            floor: The floor where the button was pressed
            direction: The requested direction (up or down)
        """
        # Ignore if floor is out of range
        if not self._is_floor_in_range(floor):
            logger.warning(f"Floor {floor} is out of range and will be ignored")
            return
        
        # Check if there's a direction conflict
        direction_conflict = False
        if direction == ElevatorDirection.Up:
            if floor in self.up_requests:
                logger.info(f"Up request for floor {floor} already registered")
                return
            logger.info(f"Up request registered for floor {floor}")
            self.up_requests.add(floor)
        else:  # Down direction
            if floor in self.down_requests:
                logger.info(f"Down request for floor {floor} already registered")
                return
            logger.info(f"Down request registered for floor {floor}")
            self.down_requests.add(floor)
        
        # Check for direction conflict with current movement
        current_floor = self.internal_control.get_current_floor()
        current_status = self.internal_control.get_current_status()
        
        # A direction conflict occurs when the elevator is moving in a different direction
        # than what would be needed to service this new request
        if current_status == ElevatorStatus.Running and self._current_direction is not None:
            # If moving up, but new request requires going down to reach it
            if self._current_direction == ElevatorDirection.Up and floor < current_floor:
                direction_conflict = True
                self._direction_conflict = True
                logger.info(f"Direction conflict detected: moving up but request from floor {floor} is below current floor {current_floor}")
            # If moving down, but new request requires going up to reach it
            elif self._current_direction == ElevatorDirection.Down and floor > current_floor:
                direction_conflict = True
                self._direction_conflict = True
                logger.info(f"Direction conflict detected: moving down but request from floor {floor} is above current floor {current_floor}")
        
        # If there's a direction conflict, we need to update the direction immediately
        if direction_conflict:
            # Immediately stop current elevator and update direction
            await self._stop_current_elevator()
            self._current_direction = direction
        else:
            # Start elevator if it's not running
            if current_status != ElevatorStatus.Running and not self._is_running:
                asyncio.create_task(self._update_direction())
        
        # Notify subscribers
        for subscriber in self._subscribers:
            subscriber.on_floor_button_pressed(floor, direction)
    
    def request_up(self, floor: int) -> None:
        """
        Process an up request from a specific floor.
        
        Args:
            floor: The floor from which the up request was made
        """
        # Check floor validity
        if not isinstance(floor, int) or not (self.min_floor <= floor <= self.max_floor):
            logger.warning(f"Invalid floor for up request: {floor}", 
                         extra={"floor": floor, "action": "request_up"})
            return
            
        # Cannot request up from the top floor
        if floor == self.max_floor:
            logger.warning(f"Cannot request up from top floor {floor}", 
                         extra={"floor": floor, "action": "request_up"})
            return
        
        self.up_requests.add(floor)
        logger.info(f"Added up request from floor: {floor}", 
                   extra={"floor": floor, "action": "request_up"})
    
    def request_down(self, floor: int) -> None:
        """
        Process a down request from a specific floor.
        
        Args:
            floor: The floor from which the down request was made
        """
        # Check floor validity
        if not isinstance(floor, int) or not (self.min_floor <= floor <= self.max_floor):
            logger.warning(f"Invalid floor for down request: {floor}", 
                         extra={"floor": floor, "action": "request_down"})
            return
            
        # Cannot request down from the bottom floor
        if floor == self.min_floor:
            logger.warning(f"Cannot request down from bottom floor {floor}", 
                         extra={"floor": floor, "action": "request_down"})
            return
        
        self.down_requests.add(floor)
        logger.info(f"Added down request from floor: {floor}", 
                   extra={"floor": floor, "action": "request_down"})
    
    def should_stop_at_floor(self, floor: int, direction: ElevatorDirection) -> bool:
        """
        Determine if the elevator should stop at a specific floor.
        
        Following professional elevator scheduling principles:
        1. Always stop for internal target floor requests
        2. Only stop for external requests when the elevator direction matches request direction
        3. Only change direction when there are no more requests in the current direction
        
        Args:
            floor: Floor to check
            direction: Current elevator direction
            
        Returns:
            True if the elevator should stop, False otherwise
        """
        # Check floor validity
        if not isinstance(floor, int) or not (self.min_floor <= floor <= self.max_floor):
            logger.warning(f"Invalid floor for should_stop_at_floor: {floor}")
            return False
            
        # Case 1: If it's an internal target floor, always stop
        if floor in self.target_floors:
            logger.info(f"Should stop at floor {floor} as it's a target floor", 
                       extra={"floor": floor, "direction": str(direction), "reason": "target_floor"})
            return True
        
        # Case 2: Only stop for external requests with matching direction
        # Elevator going up only stops for up requests
        if direction == ElevatorDirection.Up and floor in self.up_requests:
            logger.info(f"Should stop at floor {floor} for up request", 
                       extra={"floor": floor, "direction": str(direction), "reason": "up_request"})
            return True
        
        # Elevator going down only stops for down requests
        if direction == ElevatorDirection.Down and floor in self.down_requests:
            logger.info(f"Should stop at floor {floor} for down request", 
                       extra={"floor": floor, "direction": str(direction), "reason": "down_request"})
            return True
        
        # Case 3: Only stop to change direction when there are no more requests in the current direction
        # Key point: This ensures elevator won't stop for down requests when going up unless there are no higher requests

        # Checks for elevator going up:
        # 1. Floor has a down request
        # 2. No more up requests or target floors above
        # 3. No more down requests above (more important to service higher down requests like floor 15)
        if (direction == ElevatorDirection.Up and 
            floor in self.down_requests and
            not any(f > floor for f in self.target_floors) and 
            not any(f > floor for f in self.up_requests) and
            not any(f > floor for f in self.down_requests)):
            logger.info(f"Should stop at floor {floor} to change direction (up to down)", 
                       extra={"floor": floor, "direction": str(direction), "reason": "change_direction_up_to_down"})
            return True
        
        # Checks for elevator going down:
        # 1. Floor has an up request
        # 2. No more down requests or target floors below
        if (direction == ElevatorDirection.Down and 
            floor in self.up_requests and
            not any(f < floor for f in self.target_floors) and 
            not any(f < floor for f in self.down_requests)):
            logger.info(f"Should stop at floor {floor} to change direction (down to up)", 
                       extra={"floor": floor, "direction": str(direction), "reason": "change_direction_down_to_up"})
            return True
        
        # If none of the above conditions are met, don't stop
        return False
    
    def on_stop(self, floor: int, direction: ElevatorDirection) -> None:
        """
        Handle elevator stop events.
        
        This method is called when the elevator stops at a floor.
        It removes processed requests and schedules the next movement.
        
        Args:
            floor: Floor where the elevator stopped
            direction: Direction the elevator was moving
        """
        # Check floor validity
        if not isinstance(floor, int) or not (self.min_floor <= floor <= self.max_floor):
            logger.warning(f"Invalid floor for on_stop: {floor}")
            return
            
        logger.info(f"Elevator stopped at floor {floor}, direction {direction}", 
                   extra={"floor": floor, "direction": str(direction), "action": "stopped"})
        
        # Remove internal target floor requests
        if floor in self.target_floors:
            self.target_floors.remove(floor)
            logger.info(f"Removed target floor: {floor}", 
                        extra={"floor": floor, "action": "remove_target"})
        
        # Process external requests based on professional elevator scheduling logic
        
        # 1. Request processing based on direction matching
        # Up-moving elevator processes up requests
        if direction == ElevatorDirection.Up and floor in self.up_requests:
            self.up_requests.remove(floor)
            logger.info(f"Removed up request from floor: {floor}", 
                        extra={"floor": floor, "action": "remove_up_request"})
        
        # Down-moving elevator processes down requests
        if direction == ElevatorDirection.Down and floor in self.down_requests:
            self.down_requests.remove(floor)
            logger.info(f"Removed down request from floor: {floor}", 
                        extra={"floor": floor, "action": "remove_down_request"})
        
        # 2. Handle direction change points, but prioritize internal requests over direction changes
        # Check if there are internal requests which should be prioritized
        has_higher_target = any(f > floor for f in self.target_floors)
        has_lower_target = any(f < floor for f in self.target_floors)
        
        # Only consider direction change points when there are no internal requests in the current direction
        # Highest point direction change: Up → Down
        if direction == ElevatorDirection.Up and not has_higher_target:
            # Check if reached highest request point
            highest_up = max([self.min_floor] + [f for f in self.up_requests])
            highest_target = max([self.min_floor] + [f for f in self.target_floors]) if self.target_floors else self.min_floor
            
            # If current floor is already the highest request point, process down requests
            if floor >= highest_up and floor >= highest_target:
                if floor in self.down_requests:
                    self.down_requests.remove(floor)
                    logger.info(f"Removed down request at highest point: {floor}", 
                               extra={"floor": floor, "action": "remove_down_request"})
        
        # Lowest point direction change: Down → Up
        elif direction == ElevatorDirection.Down and not has_lower_target:
            # Check if reached lowest request point
            lowest_down = min([self.max_floor] + [f for f in self.down_requests])
            lowest_target = min([self.max_floor] + [f for f in self.target_floors]) if self.target_floors else self.max_floor
            
            # If current floor is already the lowest request point, process up requests
            if floor <= lowest_down and floor <= lowest_target:
                if floor in self.up_requests:
                    self.up_requests.remove(floor)
                    logger.info(f"Removed up request at lowest point: {floor}", 
                               extra={"floor": floor, "action": "remove_up_request"})
        
        # Update running state
        self._is_running = False
        
        # New addition: Add a short delay to simulate the time passengers spend boarding/exiting
        # This gives users time to press internal buttons before the elevator decides its next action
        # In real scenarios, elevators wait for a short time at each floor - we're simulating this behavior
        async def delayed_direction_update():
            # Wait for doors to open/close and passengers to move, using time from config
            door_operation_time = self.CONFIG["timing"]["door_operation"]
            await asyncio.sleep(door_operation_time)
            
            # Handle direction conflicts
            # If a direction conflict was previously detected, prioritize internal requests now that the elevator has stopped
            if self._direction_conflict:
                logger.info("Direction conflict detected, prioritizing internal requests")
                self._direction_conflict = False  # Reset conflict flag
                # Re-evaluate direction with higher priority
                await self._update_direction(True)
            else:
                # Normal direction update
                await self._update_direction()
                
        # Create async task to handle delayed direction update
        asyncio.create_task(delayed_direction_update())
    
    def _schedule_update_direction(self, force: bool = False) -> None:
        """
        Schedule an update of the elevator direction.
        
        This method handles the asynchronous execution of direction updates,
        creating a task in the event loop if one is available.
        
        Args:
            force: If True, force a direction update even if the elevator is already running
        """
        try:
            # Skip if already running and not forced
            if self._is_running and not force:
                logger.debug("Elevator is already running, skip _update_direction", 
                            extra={"is_running": self._is_running})
                return
                
            # Try to create an async task
            loop = asyncio.get_running_loop()
            asyncio.create_task(self._update_direction(force))
        except RuntimeError:
            # In test environments, there might not be a running event loop
            logger.debug("No running event loop, skip _update_direction")
    
    async def _update_direction(self, force: bool = False) -> None:
        """
        Update the elevator direction and start movement if needed.
        
        This method decides which direction the elevator should move next
        based on the current state and pending requests.
        
        Args:
            force: If True, force a direction update even if the elevator is already running
        """
        # Check if there's a direction conflict that requires immediate stop
        current_elevator_status = self.internal_control.get_current_status()
        if force and self._direction_conflict and current_elevator_status == ElevatorStatus.Running:
            logger.info("Forcing elevator to stop to handle direction conflict")
            # Elevator will stop at the current floor, then on_stop will trigger to handle the remaining logic
            # Set running state to non-running to prevent other operations from interfering
            self._is_running = False
            return
            
        # Skip if elevator is already running and not forced
        if (self.internal_control.get_current_status() == ElevatorStatus.Running or self._is_running) and not force:
            return
        
        current_floor = self.internal_control.get_current_floor()
        
        # Check if there are any pending requests
        has_requests = bool(self.target_floors or self.up_requests or self.down_requests)
        if not has_requests:
            logger.info("No pending requests, elevator remains idle", 
                       extra={"floor": current_floor, "action": "idle"})
            self._current_direction = None
            return
        
        # Priority check for internal requests (target_floors)
        # If there are internal requests, move in the correct direction immediately regardless of previous direction
        higher_target_floors = [f for f in self.target_floors if f > current_floor]
        lower_target_floors = [f for f in self.target_floors if f < current_floor]
        
        if higher_target_floors and not lower_target_floors:
            # If there are target requests for higher floors, move up
            next_direction = ElevatorDirection.Up
            logger.info(f"Prioritizing internal requests: Choosing UP direction to target floors {higher_target_floors}")
        elif lower_target_floors and not higher_target_floors:
            # If there are target requests for lower floors, move down
            next_direction = ElevatorDirection.Down
            logger.info(f"Prioritizing internal requests: Choosing DOWN direction to target floors {lower_target_floors}")
        elif higher_target_floors and lower_target_floors:
            # If there are internal requests in both directions, calculate optimal direction
            up_score = self._calculate_direction_score(current_floor, ElevatorDirection.Up)
            down_score = self._calculate_direction_score(current_floor, ElevatorDirection.Down)
            
            if up_score > down_score:
                next_direction = ElevatorDirection.Up
                logger.info(f"Prioritizing internal requests: Choosing UP direction based on scores: UP={up_score}, DOWN={down_score}")
            else:
                next_direction = ElevatorDirection.Down
                logger.info(f"Prioritizing internal requests: Choosing DOWN direction based on scores: UP={up_score}, DOWN={down_score}")
        else:
            # No internal requests, use existing logic to determine direction
            next_direction = self._determine_direction(current_floor)
        
        # If direction cannot be determined, check if we should maintain current direction
        if next_direction is None:
            # If there are pending requests but no direction was determined,
            # try to maintain the last known direction if possible
            if has_requests and self._current_direction is not None:
                logger.warning("Using last known direction due to indeterminate state", 
                            extra={"floor": current_floor, "direction": str(self._current_direction)})
                next_direction = self._current_direction
            else:
                logger.warning("Could not determine direction, elevator remains idle", 
                            extra={"floor": current_floor, "action": "idle"})
                return
            
        # Set running state
        self._is_running = True
        
        # Start elevator movement
        try:
            if next_direction == ElevatorDirection.Up:
                logger.info("Starting elevator movement: UP", 
                           extra={"floor": current_floor, "direction": "up", "action": "move"})
                self.internal_control.start_move_up()
            else:
                logger.info("Starting elevator movement: DOWN", 
                           extra={"floor": current_floor, "direction": "down", "action": "move"})
                self.internal_control.start_move_down()
            
            # Update current direction
            self._current_direction = next_direction
        except Exception as e:
            # Reset running state on failure
            self._is_running = False
            logger.error(f"Failed to start elevator movement: {e}", 
                        exc_info=True, 
                        extra={"floor": current_floor, "action": "move_failed"})
            raise
    
    def _determine_direction(self, current_floor: int) -> Optional[ElevatorDirection]:
        """
        Determine the optimal elevator movement direction based on modern scheduling algorithms.
        
        This algorithm is based on the following professional elevator scheduling principles:
        1. Direction priority: Prioritize serving requests in the current direction
        2. Proximity priority: For requests in the same direction, prioritize closer floors
        3. Request type priority: Internal requests take precedence over external requests
        4. Efficient path planning: Choose paths that minimize total wait time
        
        Args:
            current_floor: Current elevator floor
            
        Returns:
            The determined movement direction, or None if no direction can be determined
        """
        # Get information about different types of requests
        higher_target_floors = [f for f in self.target_floors if f > current_floor]
        lower_target_floors = [f for f in self.target_floors if f < current_floor]
        higher_up_requests = [f for f in self.up_requests if f > current_floor]
        lower_up_requests = [f for f in self.up_requests if f < current_floor]
        higher_down_requests = [f for f in self.down_requests if f > current_floor]
        lower_down_requests = [f for f in self.down_requests if f < current_floor]
        
        # Log all pending floor requests for debugging
        logger.info(f"Pending requests: UP_HIGHER={higher_up_requests}, UP_LOWER={lower_up_requests}, " +
                   f"DOWN_HIGHER={higher_down_requests}, DOWN_LOWER={lower_down_requests}, " +
                   f"TARGET_HIGHER={higher_target_floors}, TARGET_LOWER={lower_target_floors}")
        
        # Modification 1: Prioritize internal button requests (TARGET)
        # If there are internal target floor requests, prioritize these requests
        if higher_target_floors or lower_target_floors:
            # If moving up or no direction set, and there are higher target floors, continue up
            if (self._current_direction == ElevatorDirection.Up or self._current_direction is None) and higher_target_floors:
                logger.info(f"Prioritizing internal requests: Choosing UP direction to target floors {higher_target_floors}")
                return ElevatorDirection.Up
                
            # If moving down or no direction set, and there are lower target floors, continue down
            elif (self._current_direction == ElevatorDirection.Down or self._current_direction is None) and lower_target_floors:
                logger.info(f"Prioritizing internal requests: Choosing DOWN direction to target floors {lower_target_floors}")
                return ElevatorDirection.Down
                
            # If direction is unclear but there are internal requests, decide based on the nearest internal request
            elif higher_target_floors and not lower_target_floors:
                logger.info(f"Prioritizing internal requests: Choosing UP direction to target floors {higher_target_floors}")
                return ElevatorDirection.Up
            elif lower_target_floors and not higher_target_floors:
                logger.info(f"Prioritizing internal requests: Choosing DOWN direction to target floors {lower_target_floors}")
                return ElevatorDirection.Down
            elif higher_target_floors and lower_target_floors:
                # If there are internal requests in both directions, maintain current direction or calculate optimal direction
                if self._current_direction == ElevatorDirection.Up:
                    logger.info(f"Prioritizing internal requests: Maintaining UP direction to target floors {higher_target_floors}")
                    return ElevatorDirection.Up
                elif self._current_direction == ElevatorDirection.Down:
                    logger.info(f"Prioritizing internal requests: Maintaining DOWN direction to target floors {lower_target_floors}")
                    return ElevatorDirection.Down
                else:
                    # When direction is not clear, calculate best direction
                    up_score = self._calculate_direction_score(current_floor, ElevatorDirection.Up)
                    down_score = self._calculate_direction_score(current_floor, ElevatorDirection.Down)
                    
                    if up_score > down_score:
                        logger.info(f"Prioritizing internal requests: Choosing UP direction based on scores: UP={up_score}, DOWN={down_score}")
                        return ElevatorDirection.Up
                    else:
                        logger.info(f"Prioritizing internal requests: Choosing DOWN direction based on scores: UP={up_score}, DOWN={down_score}")
                        return ElevatorDirection.Down
        
        # Original logic starts here
        # Check conditions for continuing existing direction
        if self._current_direction == ElevatorDirection.Up:
            # If elevator is moving up and there are any requests above, continue up
            if higher_target_floors or higher_up_requests or higher_down_requests:
                logger.info(f"Continuing UP direction from floor {current_floor} to serve pending requests")
                return ElevatorDirection.Up
            # If no requests above but requests below, change direction to down
            elif lower_target_floors or lower_down_requests or lower_up_requests:
                logger.info(f"Changing direction to DOWN from floor {current_floor} as no higher requests exist")
                return ElevatorDirection.Down
        elif self._current_direction == ElevatorDirection.Down:
            # If elevator is moving down and there are any requests below, continue down
            if lower_target_floors or lower_down_requests or lower_up_requests:
                logger.info(f"Continuing DOWN direction from floor {current_floor} to serve pending requests")
                return ElevatorDirection.Down
            # If no requests below but requests above, change direction to up
            elif higher_target_floors or higher_up_requests or higher_down_requests:
                logger.info(f"Changing direction to UP from floor {current_floor} as no lower requests exist")
                return ElevatorDirection.Up
        
        # If no existing direction or above rules didn't determine direction, use comprehensive decision logic
        
        # Handle when elevator is at a floor with requests
        if current_floor in self.up_requests:
            return ElevatorDirection.Up
        if current_floor in self.down_requests:
            return ElevatorDirection.Down
            
        # Check if there are any requests
        has_higher_requests = bool(higher_target_floors or higher_up_requests or higher_down_requests)
        has_lower_requests = bool(lower_target_floors or lower_down_requests or lower_up_requests)
        
        # If there are requests above, move up
        if has_higher_requests and not has_lower_requests:
            logger.info(f"Moving UP from floor {current_floor} to serve higher requests")
            return ElevatorDirection.Up
            
        # If there are requests below, move down
        elif has_lower_requests and not has_higher_requests:
            logger.info(f"Moving DOWN from floor {current_floor} to serve lower requests")
            return ElevatorDirection.Down
            
        # If there are requests both above and below, use scheduling algorithm to determine priority direction
        elif has_higher_requests and has_lower_requests:
            return self._get_direction_from_scheduling_algorithm(current_floor)
            
        # If there are no requests, return None
        else:
            return None
    
    def _get_direction_from_scheduling_algorithm(self, current_floor: int) -> Optional[ElevatorDirection]:
        """
        Get direction from the selected scheduling algorithm.
        
        Args:
            current_floor: Current elevator floor
            
        Returns:
            The determined direction, or None if no direction can be determined
        """
        if self.scheduling_strategy == SchedulingStrategy.LOOK:
            return self._look_algorithm(current_floor)
        elif self.scheduling_strategy == SchedulingStrategy.SCAN:
            return self._scan_algorithm(current_floor)
        elif self.scheduling_strategy == SchedulingStrategy.SSTF:
            return self._shortest_seek_time_algorithm(current_floor)
        else:
            # Default to LOOK algorithm
            return self._look_algorithm(current_floor)
    
    def _look_algorithm(self, current_floor: int) -> Optional[ElevatorDirection]:
        """
        LOOK scheduling algorithm implementation.
        
        The LOOK algorithm always continues in the current direction until there are no more
        requests in that direction, then it changes direction immediately.
        
        Args:
            current_floor: Current elevator floor
            
        Returns:
            The determined direction, or None if no direction can be determined
        """
        # Special case: If elevator is at the lowest floor with down requests, move up
        if current_floor == self.min_floor and self.down_requests:
            logger.debug(f"LOOK algorithm choosing UP direction from bottom floor to serve DOWN requests")
            return ElevatorDirection.Up
            
        # Special case: If elevator is at the highest floor with up requests, move down
        if current_floor == self.max_floor and self.up_requests:
            logger.debug(f"LOOK algorithm choosing DOWN direction from top floor to serve UP requests")
            return ElevatorDirection.Down
        
        # Check if there are requests above the current floor
        has_up_requests = (
            any(f > current_floor for f in self.target_floors) or
            any(f > current_floor for f in self.up_requests)
        )
        
        # Check if there are requests below the current floor
        has_down_requests = (
            any(f < current_floor for f in self.target_floors) or
            any(f < current_floor for f in self.down_requests)
        )
        
        # Check for requests at the current floor that require specific direction handling
        has_current_floor_up = current_floor in self.up_requests
        has_current_floor_down = current_floor in self.down_requests
        
        # If there are requests in both directions
        if has_up_requests and has_down_requests:
            # The LOOK algorithm requires balancing wait times
            # Calculate the score for both directions
            up_score = self._calculate_direction_score(current_floor, ElevatorDirection.Up)
            down_score = self._calculate_direction_score(current_floor, ElevatorDirection.Down)
            
            if up_score > down_score:
                logger.debug(f"LOOK algorithm choosing UP direction (scores: UP={up_score}, DOWN={down_score})")
                return ElevatorDirection.Up
            else:
                logger.debug(f"LOOK algorithm choosing DOWN direction (scores: UP={up_score}, DOWN={down_score})")
                return ElevatorDirection.Down
        
        # If there are only up requests
        elif has_up_requests:
            logger.debug(f"LOOK algorithm choosing UP direction (only up requests)")
            return ElevatorDirection.Up
        
        # If there are only down requests
        elif has_down_requests:
            logger.debug(f"LOOK algorithm choosing DOWN direction (only down requests)")
            return ElevatorDirection.Down
        
        # If there are only current floor directional requests but no other floors
        elif has_current_floor_up:
            logger.debug(f"LOOK algorithm choosing UP direction for current floor up request")
            return ElevatorDirection.Up
        elif has_current_floor_down:
            logger.debug(f"LOOK algorithm choosing DOWN direction for current floor down request")
            return ElevatorDirection.Down
            
        # Check if there are any requests at all, even if they don't fit the above cases
        if self.up_requests or self.down_requests or self.target_floors:
            # Fall back to the previous direction if we can't determine a new one
            # This helps prevent the "Could not determine direction" warning
            if self._current_direction is not None:
                logger.debug(f"LOOK algorithm falling back to previous direction: {self._current_direction}")
                return self._current_direction
            # If no previous direction, default to going up
            logger.debug(f"LOOK algorithm defaulting to UP direction for unclear request state")
            return ElevatorDirection.Up
        
        # If there are no requests
        else:
            logger.debug(f"LOOK algorithm: no requests to service")
            return None
    
    def _scan_algorithm(self, current_floor: int, up_requests: Set[int], down_requests: Set[int], 
                       target_floors: Set[int], current_direction: Optional[ElevatorDirection] = None) -> ElevatorDirection:
        """
        Implement the SCAN algorithm (Elevator algorithm).
        
        In the SCAN algorithm, the elevator continues to travel in the same direction
        until it reaches the highest/lowest request, then reverses direction.
        
        Args:
            current_floor: Current elevator floor
            up_requests: Set of floors with UP requests
            down_requests: Set of floors with DOWN requests
            target_floors: Set of target floors selected from inside the elevator
            current_direction: Current direction of the elevator
            
        Returns:
            The direction to move (ElevatorDirection.Up or ElevatorDirection.Down)
        """
        proximity_threshold = self.CONFIG["scheduling"]["safety"]["floor_proximity_threshold"]
        
        # If at or near top floor, go down
        if current_floor >= self.max_floor - proximity_threshold:
            return ElevatorDirection.Down
        
        # If at or near bottom floor, go up
        if current_floor <= self.min_floor + proximity_threshold:
            return ElevatorDirection.Up
        
        # Continue in the same direction if there are requests in that direction
        if current_direction == ElevatorDirection.Up:
            if any(f > current_floor for f in up_requests | down_requests | target_floors):
                return ElevatorDirection.Up
            else:
                return ElevatorDirection.Down
        elif current_direction == ElevatorDirection.Down:
            if any(f < current_floor for f in up_requests | down_requests | target_floors):
                return ElevatorDirection.Down
            else:
                return ElevatorDirection.Up
            
        # Similar to LOOK, but with a preference to continue in the current direction
        if self._current_direction == ElevatorDirection.Up:
            # If already moving up, prefer to continue up
            if any(f > current_floor for f in self.target_floors) or any(f > current_floor for f in self.up_requests):
                return ElevatorDirection.Up
            # If at the top floor, change direction
            elif current_floor >= self.max_floor:
                return ElevatorDirection.Down
            # If there are no requests above but there are below, continue up to the top before changing direction
            elif any(f < current_floor for f in self.target_floors) or any(f < current_floor for f in self.down_requests):
                # Check if at or near the top floor - if so, change direction
                if current_floor >= self.max_floor - 1:
                    return ElevatorDirection.Down
                # Otherwise continue to the top
                return ElevatorDirection.Up
                
        elif self._current_direction == ElevatorDirection.Down:
            # If already moving down, prefer to continue down
            if any(f < current_floor for f in self.target_floors) or any(f < current_floor for f in self.down_requests):
                return ElevatorDirection.Down
            # If at the bottom floor, change direction
            elif current_floor <= self.min_floor:
                return ElevatorDirection.Up
            # If there are no requests below but there are above, continue down to the bottom before changing direction
            elif any(f > current_floor for f in self.target_floors) or any(f > current_floor for f in self.up_requests):
                # Check if at or near the bottom floor - if so, change direction
                if current_floor <= self.min_floor + 1:
                    return ElevatorDirection.Up
                    

    
    def _shortest_seek_time_algorithm(self, current_floor: int) -> Optional[ElevatorDirection]:
        """
        Shortest Seek Time First (SSTF) algorithm implementation.
        
        The SSTF algorithm always chooses the nearest floor with a request.
        
        Args:
            current_floor: Current elevator floor
            
        Returns:
            The determined direction, or None if no direction can be determined
        """
        # Collect all floors with requests
        requested_floors = []
        for floor in self.target_floors:
            requested_floors.append(floor)
        for floor in self.up_requests:
            requested_floors.append(floor)
        for floor in self.down_requests:
            requested_floors.append(floor)
        
        if not requested_floors:
            logger.debug(f"SSTF algorithm: no requests to service")
            return None
        
        # Find the nearest floor
        nearest_floor = min(requested_floors, key=lambda f: abs(f - current_floor))
        
        # Determine direction to the nearest floor
        if nearest_floor > current_floor:
            logger.debug(f"SSTF algorithm choosing UP direction to floor {nearest_floor}")
            return ElevatorDirection.Up
        elif nearest_floor < current_floor:
            logger.debug(f"SSTF algorithm choosing DOWN direction to floor {nearest_floor}")
            return ElevatorDirection.Down
        else:
            # If we're already at the nearest floor, check request direction
            if nearest_floor in self.up_requests:
                return ElevatorDirection.Up
            elif nearest_floor in self.down_requests:
                return ElevatorDirection.Down
            else:
                return None
    
    def _should_continue_direction(self, current_floor: int, direction: ElevatorDirection) -> bool:
        """
        Determine if the elevator should continue moving in the current direction.
        
        Args:
            current_floor: Current elevator floor
            direction: Current elevator direction
            
        Returns:
            True if the elevator should continue in the current direction, False otherwise
        """
        if direction == ElevatorDirection.Up:
            # Check if there are requests above the current floor
            has_up_requests = (
                any(f > current_floor for f in self.target_floors) or
                any(f > current_floor for f in self.up_requests)
            )
            logger.debug(f"Should continue UP: {has_up_requests}", 
                        extra={"floor": current_floor, "direction": "up", "continue": has_up_requests})
            return has_up_requests
        else:  # direction == ElevatorDirection.Down
            # Check if there are requests below the current floor
            has_down_requests = (
                any(f < current_floor for f in self.target_floors) or
                any(f < current_floor for f in self.down_requests)
            )
            logger.debug(f"Should continue DOWN: {has_down_requests}", 
                        extra={"floor": current_floor, "direction": "down", "continue": has_down_requests})
            return has_down_requests
    
    def _opposite_direction(self, direction: ElevatorDirection) -> ElevatorDirection:
        """
        Get the opposite direction.
        
        Args:
            direction: Current direction
            
        Returns:
            The opposite direction
        """
        return ElevatorDirection.Down if direction == ElevatorDirection.Up else ElevatorDirection.Up
    
    def _calculate_direction_score(self, direction: ElevatorDirection, 
                                   current_floor: int,
                                   force_evaluation: bool = False) -> Tuple[float, Set[int]]:
        """
        Calculate a score for a given direction based on pending requests.
        
        Args:
            direction: The direction to evaluate
            current_floor: The current floor of the elevator
            force_evaluation: Whether to force evaluation even if there are no requests
            
        Returns:
            Tuple of (score, floors_in_direction)
        """
        score = 0
        request_weight = self.CONFIG["scheduling"]["weights"]["request"]
        target_weight = self.CONFIG["scheduling"]["weights"]["target"]
        min_distance_factor = self.CONFIG["scheduling"]["safety"]["min_distance_factor"]
        
        # Direction scoring
        if direction == ElevatorDirection.Up:
            # Process up direction score calculation
            floors_in_direction = set()
            
            # Add all target floors above current floor
            target_floors_above = {f for f in self.target_floors if f > current_floor}
            floors_in_direction.update(target_floors_above)
            
            # Add all up requests above current floor
            up_requests_above = {f for f in self.up_requests if f > current_floor}
            floors_in_direction.update(up_requests_above)
            
            # Add all down requests above current floor
            down_requests_above = {f for f in self.down_requests if f > current_floor}
            floors_in_direction.update(down_requests_above)
            
            # If there are no floors in this direction and we're not forcing evaluation, return zero score
            if not floors_in_direction and not force_evaluation:
                return 0, set()
            
            # Calculate base score: Each target floor worth target_weight, each external request worth request_weight
            score += len(target_floors_above) * target_weight
            score += len(up_requests_above) * request_weight
            score += len(down_requests_above) * request_weight
            
            # Apply additional scoring factors
            
            # Distance factor: Higher floors get higher scores to avoid unnecessary direction changes
            distance_factor = max(min_distance_factor, current_floor - self.min_floor)  # Using min_distance_factor to avoid division by zero
            score *= distance_factor
            
            # Proximity bonus: Closest floor provides a bonus
            if floors_in_direction:
                closest_floor = min(floors_in_direction)
                proximity_bonus = request_weight / max(min_distance_factor, closest_floor - current_floor)  # Using min_distance_factor
                score += proximity_bonus
            
            return score, floors_in_direction
        
        else:  # Down direction
            # Process down direction score calculation
            floors_in_direction = set()
            
            # Add all target floors below current floor
            target_floors_below = {f for f in self.target_floors if f < current_floor}
            floors_in_direction.update(target_floors_below)
            
            # Add all down requests below current floor
            down_requests_below = {f for f in self.down_requests if f < current_floor}
            floors_in_direction.update(down_requests_below)
            
            # Add all up requests below current floor
            up_requests_below = {f for f in self.up_requests if f < current_floor}
            floors_in_direction.update(up_requests_below)
            
            # If there are no floors in this direction and we're not forcing evaluation, return zero score
            if not floors_in_direction and not force_evaluation:
                return 0, set()
            
            # Calculate base score: Each target floor worth target_weight, each external request worth request_weight
            score += len(target_floors_below) * target_weight
            score += len(down_requests_below) * request_weight
            score += len(up_requests_below) * request_weight
            
            # Apply additional scoring factors
            
            # Distance factor: Lower floors get higher scores to avoid unnecessary direction changes
            distance_factor = max(min_distance_factor, self.max_floor - current_floor)  # Using min_distance_factor to avoid division by zero
            score *= distance_factor
            
            # Proximity bonus: Closest floor provides a bonus
            if floors_in_direction:
                closest_floor = max(floors_in_direction)
                proximity_bonus = request_weight / max(min_distance_factor, current_floor - closest_floor)  # Using min_distance_factor
                score += proximity_bonus
            
            return score, floors_in_direction

    def _is_floor_in_range(self, floor: int) -> bool:
        """
        Check if a floor is within the valid range for this elevator.
        
        Args:
            floor: Floor number to check
            
        Returns:
            True if the floor is in range, False otherwise
        """
        if not isinstance(floor, int):
            return False
        return self.min_floor <= floor <= self.max_floor


class EventHandlers:
    """
    Implementation of event handlers for the elevator internal control.
    
    This class bridges between the elevator controller and the internal control,
    handling events like checking whether to stop at a floor and responding to stops.
    """
    
    def __init__(self, controller: ElevatorController) -> None:
        """
        Initialize the event handlers.
        
        Args:
            controller: The elevator controller instance
        """
        self.controller = controller
    
    def should_stop_at_floor(self, floor: int, direction: ElevatorDirection) -> bool:
        """
        Determine if the elevator should stop at a specific floor.
        
        Args:
            floor: Floor to check
            direction: Current elevator direction
            
        Returns:
            True if the elevator should stop, False otherwise
        """
        return self.controller.should_stop_at_floor(floor, direction)
    
    def on_stop(self, floor: int, direction: ElevatorDirection) -> None:
        """
        Handle elevator stop events.
        
        Args:
            floor: Floor where the elevator stopped
            direction: Direction the elevator was moving
        """
        self.controller.on_stop(floor, direction) 