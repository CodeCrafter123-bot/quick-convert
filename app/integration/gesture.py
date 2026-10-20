"""Detects "drag with Shift held" anywhere on screen from polled input state.

Pure state machine, no Qt or OS calls, so it can be unit tested. The caller polls
the physical mouse/Shift state and the cursor position, and reacts to the result:
"show" -> show the drop bubble, "hide" -> hide it.
"""

from __future__ import annotations

import math
from enum import Enum

DRAG_THRESHOLD = 12  # pixels the cursor must travel before a press counts as a drag


class GestureState(Enum):
    IDLE = "idle"
    PRESSED = "pressed"  # button down outside our windows, not (yet) a Shift-drag
    ARMED = "armed"      # bubble shown
    IGNORED = "ignored"  # press began over our own window: the app handles that itself


class DragGestureDetector:
    def __init__(self, threshold: float = DRAG_THRESHOLD):
        self.threshold = threshold
        self.state = GestureState.IDLE
        self.start: tuple[float, float] = (0.0, 0.0)
        self.moved = False

    def update(self, button_down: bool, shift_down: bool, pos: tuple[float, float],
               over_own_window: bool) -> str | None:
        if self.state is GestureState.IDLE:
            if button_down:
                if over_own_window:
                    self.state = GestureState.IGNORED
                else:
                    self.state, self.start, self.moved = GestureState.PRESSED, pos, False
            return None

        if self.state is GestureState.IGNORED:
            if not button_down:
                self.state = GestureState.IDLE
            return None

        if self.state is GestureState.PRESSED:
            if not button_down:
                self.state = GestureState.IDLE
                return None
            if not self.moved and math.dist(pos, self.start) >= self.threshold:
                self.moved = True
            if self.moved and shift_down:
                self.state = GestureState.ARMED
                return "show"
            return None

        # ARMED
        if not button_down:
            self.state = GestureState.IDLE
            return "hide"
        if not shift_down:
            self.state = GestureState.PRESSED  # pressing Shift again re-shows the bubble
            return "hide"
        return None
