from elevator_interface import InternalControlMock, ElevatorStatus, ElevatorDirection, wait
from elevator_controller import ElevatorController, EventHandlers
import logging

logger = logging.getLogger("ElevatorSystem")

class ProfessionalInternalControlMock(InternalControlMock):
    """
    Professional Elevator Internal Control Mock
    
    Implements industry-standard elevator movement logic to ensure the elevator
    correctly services all floor requests
    """
    
    async def __private_move(self, direction: ElevatorDirection) -> None:
        """
        Internal method to simulate elevator movement.
        
        Implements the following elevator movement logic:
        1. Moves the elevator floor-by-floor in the specified direction
        2. Checks at each floor whether a stop is required
        3. Ensures elevator stops correctly at boundary floors
        4. Follows the elevator controller's stop decision logic
        
        Args:
            direction: Elevator movement direction (Up or Down)
            
        Raises:
            Exception: If the elevator is already running
        """
        if self.status == ElevatorStatus.Running:
            raise Exception("Elevator is already running")

        # Update elevator status and direction        
        self.status = ElevatorStatus.Running
        self.direction = direction
        
        # Record starting position for detailed tracking
        start_floor = self.floor
        logger.info(f"Starting elevator movement from floor {start_floor}: {direction}")
        print(f"Elevator is moving {direction}")
        
        # Determine floor increment based on direction
        delta = 1 if direction == ElevatorDirection.Up else -1
        
        # Floors passed during this movement
        floors_passed = [start_floor]
        
        # Main movement loop
        while True:
            # Check if at boundary
            if (direction == ElevatorDirection.Up and self.floor >= self.max_floor) or \
               (direction == ElevatorDirection.Down and self.floor <= self.min_floor):
                logger.info(f"Reached boundary floor: {self.floor}")
                break
            
            # Calculate next floor
            next_floor = self.floor + delta
            
            # Check if floor is valid
            if next_floor < self.min_floor or next_floor > self.max_floor:
                logger.info(f"Next floor {next_floor} is out of bounds")
                break
                
            # Check if elevator should stop at next floor
            should_stop = self.event_handlers.should_stop_at_floor(next_floor, direction)
            
            # Simulate travel time
            await wait(1)
            
            # Update current floor
            previous_floor = self.floor
            self.floor = next_floor
            
            # Record floor passage
            floors_passed.append(self.floor)
            logger.debug(f"Elevator moved from floor {previous_floor} to floor {self.floor}")
            
            # Re-check stop condition after reaching new floor (to handle request changes)
            should_stop = should_stop or self.event_handlers.should_stop_at_floor(self.floor, direction)
            
            # Stop the elevator if needed
            if should_stop:
                logger.info(f"Should stop at floor {self.floor}")
                print(f"Elevator stopped at {self.floor}")
                break
                
            # Check if at boundary
            is_up_boundary = (direction == ElevatorDirection.Up and self.floor == self.max_floor)
            is_down_boundary = (direction == ElevatorDirection.Down and self.floor == self.min_floor)
            
            if is_up_boundary or is_down_boundary:
                logger.info(f"Reached limit floor {self.floor}, stopping")
                break
        
        # Update elevator status
        print(f"Elevator stopped at {self.floor}")
        self.status = ElevatorStatus.Idle
        
        # Log summary of this movement
        logger.info(f"Elevator movement summary: {direction}, from floor {start_floor} to {self.floor}, passed floors: {floors_passed}")
        
        # Notify controller that elevator has stopped
        try:
            self.event_handlers.on_stop(self.floor, direction)
        except Exception as e:
            logger.error(f"Error in on_stop handler: {e}")


class InternalControlMockWithHandlers(ProfessionalInternalControlMock):
    """
    Professional Elevator Internal Control Mock with Event Handlers
    
    Connects the elevator controller with the simulated hardware implementation,
    providing a complete elevator scheduling system
    """
    
    def __init__(self, controller: ElevatorController, min_floor: int, max_floor: int):
        """
        Initialize the elevator internal control mock with event handlers
        
        Args:
            controller: Elevator controller instance implementing scheduling algorithm
            min_floor: Minimum floor the elevator can reach
            max_floor: Maximum floor the elevator can reach
        """
        # Create event handlers from controller
        handlers = EventHandlers(controller)
        
        # Initialize base class with handlers
        super().__init__(handlers, min_floor, max_floor) 