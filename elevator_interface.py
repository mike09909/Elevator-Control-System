from enum import Enum
from typing import Protocol, Callable, Optional, NoReturn
import asyncio

# Configuration constants
# Time it takes for the elevator to travel between floors (in seconds)
TRAVEL_TIME = 1  # in seconds


class ElevatorStatus(Enum):
    """
    Represents the operational status of the elevator.
    
    Attributes:
        Idle: The elevator is stopped at a floor and not moving
        Running: The elevator is currently moving between floors
    """
    Idle = 'Idle'
    Running = 'Running'


class ElevatorDirection(Enum):
    """
    Represents the direction of elevator movement.
    
    Attributes:
        Up: The elevator is moving upward
        Down: The elevator is moving downward
    """
    Up = 'Up'
    Down = 'Down'


class InternalControlEventHandlers(Protocol):
    """
    Protocol defining event handlers required by elevator internal control.
    
    This interface must be implemented by any class that wants to handle
    elevator internal control events such as deciding when to stop at a floor
    and handling stop events.
    """
    should_stop_at_floor: Callable[[int, ElevatorDirection], bool]
    on_stop: Callable[[int, ElevatorDirection], None]


class InternalControl(Protocol):
    """
    Protocol defining the interface for elevator internal control.
    
    This interface is provided by the hardware team and includes methods
    for getting elevator status and controlling its movement.
    """
    def get_current_status(self) -> ElevatorStatus: 
        """Get the current operational status of the elevator"""
        ...

    def get_current_direction(self) -> ElevatorDirection: 
        """Get the current direction of elevator movement"""
        ...

    def get_current_floor(self) -> int: 
        """Get the current floor where the elevator is located"""
        ...

    def start_move_up(self) -> None: 
        """Command the elevator to start moving upward"""
        ...

    def start_move_down(self) -> None: 
        """Command the elevator to start moving downward"""
        ...


async def wait(rounds: int) -> None:
    """
    Helper function to simulate time passing during elevator operation.
    
    Args:
        rounds: Number of time units to wait (multiplied by TRAVEL_TIME)
    """
    await asyncio.sleep(rounds * TRAVEL_TIME)


class InternalControlMock(InternalControl):
    """
    Mock implementation of the elevator internal control.
    
    This class simulates elevator hardware behavior, providing a software
    simulation of an actual elevator for testing and development purposes.
    It implements the InternalControl protocol.
    """
    status: ElevatorStatus = ElevatorStatus.Idle
    direction: ElevatorDirection = ElevatorDirection.Up
    floor: int = 0

    def __init__(self, event_handlers: InternalControlEventHandlers, min_floor: int, max_floor: int) -> None:
        """
        Initialize the internal control mock.
        
        Args:
            event_handlers: The event handlers object that will handle internal control events
            min_floor: The lowest floor the elevator can reach
            max_floor: The highest floor the elevator can reach
        """
        self.event_handlers = event_handlers
        self.min_floor = min_floor
        self.max_floor = max_floor

    def get_current_status(self) -> ElevatorStatus:
        """
        Get the current operational status of the elevator.
        
        Returns:
            The current elevator status (Idle or Running)
        """
        return self.status

    def get_current_floor(self) -> int:
        """
        Get the current floor where the elevator is located.
        
        Returns:
            The current floor number
        """
        return self.floor

    def get_current_direction(self) -> ElevatorDirection:
        """
        Get the current direction of elevator movement.
        
        Returns:
            The current elevator direction (Up or Down)
        """
        return self.direction

    async def __private_move(self, direction: ElevatorDirection) -> None:
        """
        Internal method to simulate elevator movement.
        
        This method simulates the physical movement of the elevator, including
        time delays for travel between floors and checks for when to stop.
        
        Args:
            direction: The direction of movement (Up or Down)
            
        Raises:
            Exception: If the elevator is already running
        """
        if self.status == ElevatorStatus.Running:
            raise Exception("Elevator is already running")

        self.status = ElevatorStatus.Running
        print(f"Elevator is moving {direction}")

        self.direction = direction
        delta = 1 if direction == ElevatorDirection.Up else -1

        while (direction == ElevatorDirection.Up and self.floor < self.max_floor) or \
                (direction == ElevatorDirection.Down and self.floor > self.min_floor):
            # Check if the elevator should stop at the next floor
            should_stop = self.event_handlers.should_stop_at_floor(self.floor + delta, direction)
            # Simulate the time it takes to move to the next floor
            await wait(1)
            # Update the current floor
            self.floor += delta
            # If the elevator should stop at this floor, break the loop
            if should_stop:
                break

        print(f"Elevator stopped at {self.floor}")
        self.status = ElevatorStatus.Idle
        # Notify event handlers that the elevator has stopped
        self.event_handlers.on_stop(self.floor, direction)

    def start_move_down(self) -> None:
        """
        Command the elevator to start moving downward.
        
        Creates a new asynchronous task to move the elevator downward.
        """
        asyncio.create_task(self.__private_move(ElevatorDirection.Down))

    def start_move_up(self) -> None:
        """
        Command the elevator to start moving upward.
        
        Creates a new asynchronous task to move the elevator upward.
        """
        asyncio.create_task(self.__private_move(ElevatorDirection.Up))


# Elevator scenario reference for testing:
# Elevator is idle at F0
# User A request DOWN from F9 => Elevator should starting to move up
# Elevator is moving up, currently reaching F3
# User B request UP from F5 => Elevator should stop at F5
# User C request UP from F2 => Elevator should ignore/queue this request for now
# Elevator is moving up, currently stop at F5, User B is in, User B request to F8 => Elevator should stop at F8 first
# User D request DOWN from F15 => Elevator should skip F9, and go to F15 directly
# Elevator is moving up, currently stop at F15, User D is in , USer D request to F11
# Elebator is moving down, currently stop at F11, USer D is out
# Elevator is moving down, currenlty stop at F9, USer A is in, USer A request to F0
# Elevator is moving down, currenlty stop at F0, USer A is out
# Elevator is moveing up, currently stop at F2, USer C is in