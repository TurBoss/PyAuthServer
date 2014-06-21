from network.structures import factory_dict

from game_system.enums import InputEvents
from game_system.inputs import IInputStatusLookup
from game_system.math import clamp

from bge import events, logic, render
from mathutils import Vector

__all__ = ['BGEInputStatusLookup', 'BGEMouseManager']


class BGEInputStatusLookup(IInputStatusLookup):
    """BGE interface for Input Status lookups"""

    def __init__(self):
        self._event_list_containing = factory_dict(self._get_containing_events)

    def __call__(self, event):
        bge_event = self._convert_to_bge_event(event)
        device_events = self._event_list_containing[bge_event].events
        return device_events[bge_event] in (logic.KX_INPUT_ACTIVE, logic.KX_INPUT_JUST_ACTIVATED)

    @staticmethod
    def _convert_to_bge_event(event):
        """Parse an InputEvent and return BGE event code

        :param event: :py:code:`bge_game_system.enums.InputEvent` code
        """
        try:
            event_name = InputEvents[event]
        except KeyError:
            raise ValueError("No such event {} is supported by this library".format(event_name))

        try:
            return getattr(events, event_name)

        except AttributeError as err:
            raise LookupError("No event with name {} was found in platform event list".format(event_name)) from err

    @staticmethod
    def _get_containing_events(event):
        """Return the events dictionary for the host device for an event type

        :param event: BGE event
        """
        keyboard = logic.keyboard
        return keyboard if event in keyboard.events else logic.mouse


class BGEMouseManager:

    def __init__(self, locked=True, interpolation=1):
        self.window_size = Vector((render.getWindowWidth(), render.getWindowHeight()))
        self.center = Vector(((self.window_size.x//2)/self.window_size.x,
                              (self.window_size.y//2)/self.window_size.y))
        self.locked = locked
        self.interpolation = interpolation

        self._delta_position = Vector((0.0, 0.0))
        self._last_position = self.position

    @property
    def delta_position(self):
        return self._delta_position

    @property
    def position(self):
        return Vector(logic.mouse.position)

    @position.setter
    def position(self, position):
        screen_x = round(position[0] * self.window_size.x)
        screen_y = round(position[1] * self.window_size.y)
        # Use render method to ensure accurate centering
        render.setMousePosition(screen_x, screen_y)

    @property
    def visible(self):
        return logic.mouse.visible

    @visible.setter
    def visible(self, state):
        logic.mouse.visible = state

    def update(self):
        self.position.x = clamp(0, 1, self.position.x)
        self.position.y = clamp(0, 1, self.position.y)
        delta_position = self._last_position - self.position

        self._delta_position = self._delta_position.lerp(delta_position, self.interpolation)

        if self.locked:
            # As mouse position isn't actually (0.5, 0.5)
            self.position = self.center.copy()
            last_position = self.center.copy()

        else:
            last_position = self.position.copy()

        self._last_position = last_position