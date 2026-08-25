"""
exercises/base_exercise.py

Abstract interface every exercise module must implement. RepCounter and
app.py both talk to exercises only through this interface, so adding a new
exercise (e.g. a future push-up module) never requires touching the state
machine or the UI loop -- just drop in a new BaseExercise subclass.
"""

from abc import ABC, abstractmethod


class BaseExercise(ABC):
    # Class-level metadata every concrete exercise must set.
    name: str
    down_threshold: float
    up_threshold: float

    @abstractmethod
    def get_primary_angle(self, landmarks, w: int, h: int) -> float:
        """
        Compute and return the single angle (in degrees) that drives the
        rep-counting state machine for this exercise (e.g. elbow angle for
        bicep curl, knee angle for squat).
        """
        raise NotImplementedError

    @abstractmethod
    def check_form(self, landmarks, w: int, h: int) -> dict:
        """
        Evaluate exercise-specific form rules for the current frame.

        Must check at least one condition beyond the primary rep-counting
        angle (see each subclass for its specific secondary checks).

        Returns:
            {"is_good_form": bool, "issues": [list of human-readable str]}
        """
        raise NotImplementedError

    @abstractmethod
    def get_landmarks_to_draw(self) -> list:
        """
        Returns a list of mediapipe.solutions.pose.PoseLandmark enum members
        that are relevant to this exercise, so the UI can optionally
        highlight just the joints that matter instead of the full 33-point
        skeleton.
        """
        raise NotImplementedError

    def get_rep_counter_kwargs(self) -> dict:
        """
        Convenience helper so app.py can do
        RepCounter(**exercise.get_rep_counter_kwargs()) without repeating
        each exercise's threshold values in the UI layer.
        """
        return {
            "down_threshold": self.down_threshold,
            "up_threshold": self.up_threshold,
        }
