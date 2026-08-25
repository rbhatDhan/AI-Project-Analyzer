"""
exercises/bicep_curl.py

Bicep curl exercise definition.

Primary angle: elbow angle (shoulder-elbow-wrist), right arm by default,
falling back to the left arm if the right-arm landmarks aren't reliably
visible (visibility < 0.6). We pick a side rather than averaging both arms
because most people curl with a slight dominant-arm lead and averaging two
independently-noisy angles tends to blur the down/up transition rather than
sharpening it.

Form check: shoulder angle (elbow-shoulder-hip) is compared against a
per-user calibrated baseline (captured during the 5-second calibration
phase in app.py) rather than a fixed absolute value, since "how much your
shoulder angle can open before you're swinging the weight" depends heavily
on individual shoulder mobility and stance -- see README "Design Decisions"
for the full rationale.
"""

from pose_landmark_enum import PoseLandmark

from exercises.base_exercise import BaseExercise
from pose_utils import calculate_angle, get_landmark_norm_xy, get_landmark_xy

VISIBILITY_THRESHOLD = 0.5
RIGHT_ARM_PREFERENCE_THRESHOLD = 0.6
SHOULDER_SWING_TOLERANCE_DEGREES = 20.0


class BicepCurl(BaseExercise):
    name = "Bicep Curl"
    down_threshold = 50.0   # fully curled (contracted)
    up_threshold = 160.0    # fully extended

    def __init__(self):
        # Set by app.py after the calibration phase completes. None until
        # then, in which case the shoulder-swing check is skipped (there's
        # nothing to compare against yet).
        self.calibrated_shoulder_angle = None
        # Tracks which arm we're currently reading, purely for on-screen
        # debug/drawing purposes.
        self.active_side = "RIGHT"

    def set_calibration_baseline(self, shoulder_angle: float):
        """Called once after the 5-second calibration window (see app.py)."""
        self.calibrated_shoulder_angle = shoulder_angle

    def _select_side(self, landmarks):
        """
        Returns "RIGHT" or "LEFT" depending on which arm's landmarks are
        reliably visible. Right arm is preferred; we only fall back to left
        if the right shoulder/elbow/wrist visibility drops below 0.6.
        """
        right_vis = min(
            landmarks[PoseLandmark.RIGHT_SHOULDER.value].visibility,
            landmarks[PoseLandmark.RIGHT_ELBOW.value].visibility,
            landmarks[PoseLandmark.RIGHT_WRIST.value].visibility,
        )
        if right_vis >= RIGHT_ARM_PREFERENCE_THRESHOLD:
            return "RIGHT"
        return "LEFT"

    def _joint_points(self, side: str):
        if side == "RIGHT":
            return (
                PoseLandmark.RIGHT_SHOULDER,
                PoseLandmark.RIGHT_ELBOW,
                PoseLandmark.RIGHT_WRIST,
                PoseLandmark.RIGHT_HIP,
            )
        return (
            PoseLandmark.LEFT_SHOULDER,
            PoseLandmark.LEFT_ELBOW,
            PoseLandmark.LEFT_WRIST,
            PoseLandmark.LEFT_HIP,
        )

    def get_primary_angle(self, landmarks, w: int, h: int) -> float:
        self.active_side = self._select_side(landmarks)
        shoulder_lm, elbow_lm, wrist_lm, _ = self._joint_points(self.active_side)

        shoulder, shoulder_vis = get_landmark_norm_xy(landmarks, shoulder_lm)
        elbow, elbow_vis = get_landmark_norm_xy(landmarks, elbow_lm)
        wrist, wrist_vis = get_landmark_norm_xy(landmarks, wrist_lm)

        if min(shoulder_vis, elbow_vis, wrist_vis) < VISIBILITY_THRESHOLD:
            # Landmarks too unreliable this frame -- return a neutral angle
            # (mid-range) so the state machine sees "transitioning" rather
            # than a false down/up spike from garbage coordinates.
            return (self.down_threshold + self.up_threshold) / 2.0

        return calculate_angle(shoulder, elbow, wrist)

    def check_form(self, landmarks, w: int, h: int) -> dict:
        issues = []
        side = self.active_side
        shoulder_lm, elbow_lm, wrist_lm, hip_lm = self._joint_points(side)

        elbow, elbow_vis = get_landmark_norm_xy(landmarks, elbow_lm)
        shoulder, shoulder_vis = get_landmark_norm_xy(landmarks, shoulder_lm)
        hip, hip_vis = get_landmark_norm_xy(landmarks, hip_lm)

        if min(elbow_vis, shoulder_vis, hip_vis) < VISIBILITY_THRESHOLD:
            # Per spec section 7: skip form-checking this frame rather than
            # computing an angle from unreliable landmarks.
            return {"is_good_form": True, "issues": []}

        shoulder_angle = calculate_angle(elbow, shoulder, hip)

        if self.calibrated_shoulder_angle is not None:
            drift = abs(shoulder_angle - self.calibrated_shoulder_angle)
            if drift > SHOULDER_SWING_TOLERANCE_DEGREES:
                issues.append("Upper arm is swinging — keep your elbow pinned to your side")

        return {"is_good_form": len(issues) == 0, "issues": issues}

    def get_landmarks_to_draw(self) -> list:
        # Draw both arms' relevant joints so switching active side mid-set
        # (e.g. visibility dropping briefly) doesn't cause the skeleton
        # overlay to flicker missing points.
        return [
            PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER,
            PoseLandmark.LEFT_ELBOW, PoseLandmark.RIGHT_ELBOW,
            PoseLandmark.LEFT_WRIST, PoseLandmark.RIGHT_WRIST,
            PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP,
        ]
