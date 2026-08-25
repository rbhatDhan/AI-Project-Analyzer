"""
rep_counter.py

Exercise-agnostic state machine for counting repetitions from a single
tracked joint angle. Deliberately knows nothing about bicep curls or squats
specifically -- it just knows "down_threshold", "up_threshold", and a stream
of angles. Each exercise module supplies its own thresholds and decides
which angle to feed in (see exercises/base_exercise.py).

State machine design
---------------------
Three logical states:
    "up"            -- angle >= up_threshold (arm extended / standing)
    "down"          -- angle <= down_threshold (arm curled / squatted)
    "transitioning" -- angle is between the two thresholds

A rep is only counted when we complete a full up -> down -> up cycle (the
starting state, "up", is exercise-specific-but-consistent: both bicep curl
and squat begin from an extended/standing position, so "up" is used as the
canonical starting/counting state for both).

Debouncing
----------
Camera/pose-estimation noise means the raw angle can flicker back and forth
across a threshold for a frame or two even when the user isn't actually
moving (e.g. holding still near the down_threshold). If we counted a state
change on the very first frame that crosses a threshold, that jitter would
register as multiple spurious transitions. Instead we require the angle to
stay on the new side of the threshold for `min_frames_in_state` consecutive
frames before the state officially changes. This is a simple counter-based
debounce -- not a low-pass filter on the angle itself -- because we want to
preserve the raw angle value for form-checking while only debouncing the
*discrete state transition* used for counting.
"""


class RepCounter:
    def __init__(self, down_threshold: float, up_threshold: float, min_frames_in_state: int = 3):
        if down_threshold >= up_threshold:
            raise ValueError("down_threshold must be less than up_threshold")

        self.down_threshold = down_threshold
        self.up_threshold = up_threshold
        self.min_frames_in_state = min_frames_in_state

        # Confirmed state (what update() reports and what drives rep counting).
        # We start in "up" because both supported exercises begin from an
        # extended/standing position.
        self.state = "up"

        # Candidate state currently being debounced, and how many consecutive
        # frames it has been observed for.
        self._candidate_state = "up"
        self._candidate_count = 0

        # Rep-cycle tracking: a rep completes when we go up -> down -> up.
        # This flag is True once we've confirmed "down" and are waiting for
        # the return to "up" to close out the rep.
        self._has_been_down_this_cycle = False

        self.rep_count = 0

    def _classify_raw(self, angle: float) -> str:
        """Map a raw angle to one of the three instantaneous zones."""
        if angle >= self.up_threshold:
            return "up"
        if angle <= self.down_threshold:
            return "down"
        return "transitioning"

    def update(self, current_angle: float) -> dict:
        """
        Feed one frame's tracked angle into the state machine.

        Returns:
            {
                "state": "up" | "down" | "transitioning",   # confirmed (debounced) state
                "rep_completed": bool,                       # True only on the frame a rep closes
                "rep_count": int,                             # running total
            }
        """
        raw_state = self._classify_raw(current_angle)
        rep_completed = False

        if raw_state == self._candidate_state:
            # Still moving toward (or holding) the same candidate state --
            # extend the debounce counter.
            self._candidate_count += 1
        else:
            # Angle zone flipped -- reset debounce tracking against the new
            # candidate. This is what protects against rapid back-and-forth
            # jitter: a single noisy frame doesn't survive long enough to
            # hit min_frames_in_state before flipping back.
            self._candidate_state = raw_state
            self._candidate_count = 1

        # Only "transitioning" is allowed to be pass-through immediately --
        # dwelling in the dead zone between thresholds is expected and
        # doesn't need debouncing since it can't complete a rep on its own.
        if raw_state == "transitioning":
            self.state = "transitioning"
        elif self._candidate_count >= self.min_frames_in_state and raw_state != self.state:
            # Confirmed transition into a new stable state.
            new_state = raw_state
            if new_state == "down" and self.state != "down":
                self._has_been_down_this_cycle = True
            elif new_state == "up" and self._has_been_down_this_cycle:
                # Completed a full up -> down -> up cycle.
                self.rep_count += 1
                rep_completed = True
                self._has_been_down_this_cycle = False
            self.state = new_state
        # else: not enough consecutive frames yet (still debouncing), or the
        # confirmed state already matches raw_state -- no change to report.

        return {
            "state": self.state,
            "rep_completed": rep_completed,
            "rep_count": self.rep_count,
        }

    def reset(self):
        """Reset all counters -- used when switching exercises mid-session."""
        self.state = "up"
        self._candidate_state = "up"
        self._candidate_count = 0
        self._has_been_down_this_cycle = False
        self.rep_count = 0
