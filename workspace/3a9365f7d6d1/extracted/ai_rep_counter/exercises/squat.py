"""
exercises/squat.py

Squat exercise definition.

Primary angle: knee angle (hip-knee-ankle), using whichever side (left/right)
has better landmark visibility this frame -- unlike the bicep curl, squats
are naturally bilateral and roughly symmetric, so we don't need a fixed
"preferred" side; we just pick whichever leg the camera currently sees best.

Form checks (two secondary conditions, both mandatory per spec):
    1. Back angle (shoulder-hip-knee) must not drop below 45 degrees at any
       point in the rep -- a proxy for excessive forward lean.
    2. Knee x-coordinate must not extend more than 40px beyond the ankle
       (toe) x-coordinate at the bottom of the squat -- a proxy for "knees
       traveling too far past the toes".
"""

from pose_landmark_enum import PoseLandmark

from exercises.base_exercise import BaseExercise
from pose_utils import calculate_angle, get_landmark_norm_xy, get_landmark_xy

VISIBILITY_THRESHOLD = 0.5
BACK_LEAN_MIN_DEGREES = 45.0
KNEE_PAST_TOE_TOLERANCE_PX = 40.0
# How close to the bottom of the squat (as a fraction of the way from
# up_threshold down to down_threshold) we require before running the
# knee-past-toe pixel check, since that check is only meaningful near full
# depth -- checking it at the top of the rep would flag normal standing
# posture as an error.
BOTTOM_OF_SQUAT_ANGLE_MARGIN_DEGREES = 15.0


class Squat(BaseExercise):
    name = "Squat"
    down_threshold = 90.0    # deep squat
    up_threshold = 160.0     # standing

    def __init__(self):
        self.calibrated_knee_angle = None
        self.calibrated_back_angle = None
        self.active_side = "RIGHT"

    def set_calibration_baseline(self, knee_angle: float, back_angle: float):
        """Called once after the 5-second calibration window (see app.py)."""
        self.calibrated_knee_angle = knee_angle
        self.calibrated_back_angle = back_angle

    def _select_side(self, landmarks):
        right_vis = min(
            landmarks[PoseLandmark.RIGHT_HIP.value].visibility,
            landmarks[PoseLandmark.RIGHT_KNEE.value].visibility,
            landmarks[PoseLandmark.RIGHT_ANKLE.value].visibility,
        )
        left_vis = min(
            landmarks[PoseLandmark.LEFT_HIP.value].visibility,
            landmarks[PoseLandmark.LEFT_KNEE.value].visibility,
            landmarks[PoseLandmark.LEFT_ANKLE.value].visibility,
        )
        return "RIGHT" if right_vis >= left_vis else "LEFT"

    def _joint_points(self, side: str):
        if side == "RIGHT":
            return (
                PoseLandmark.RIGHT_SHOULDER,
                PoseLandmark.RIGHT_HIP,
                PoseLandmark.RIGHT_KNEE,
                PoseLandmark.RIGHT_ANKLE,
            )
        return (
            PoseLandmark.LEFT_SHOULDER,
            PoseLandmark.LEFT_HIP,
            PoseLandmark.LEFT_KNEE,
            PoseLandmark.LEFT_ANKLE,
        )

    def get_primary_angle(self, landmarks, w: int, h: int) -> float:
        self.active_side = self._select_side(landmarks)
        _, hip_lm, knee_lm, ankle_lm = self._joint_points(self.active_side)

        hip, hip_vis = get_landmark_norm_xy(landmarks, hip_lm)
        knee, knee_vis = get_landmark_norm_xy(landmarks, knee_lm)
        ankle, ankle_vis = get_landmark_norm_xy(landmarks, ankle_lm)

        if min(hip_vis, knee_vis, ankle_vis) < VISIBILITY_THRESHOLD:
            return (self.down_threshold + self.up_threshold) / 2.0

        return calculate_angle(hip, knee, ankle)

    def check_form(self, landmarks, w: int, h: int) -> dict:
        issues = []
        side = self.active_side
        shoulder_lm, hip_lm, knee_lm, ankle_lm = self._joint_points(side)

        shoulder, shoulder_vis = get_landmark_norm_xy(landmarks, shoulder_lm)
        hip, hip_vis = get_landmark_norm_xy(landmarks, hip_lm)
        knee, knee_vis = get_landmark_norm_xy(landmarks, knee_lm)
        ankle, ankle_vis = get_landmark_norm_xy(landmarks, ankle_lm)

        if min(shoulder_vis, hip_vis, knee_vis, ankle_vis) < VISIBILITY_THRESHOLD:
            # Per spec section 7: skip form-checking this frame rather than
            # computing garbage angles from unreliable landmarks.
            return {"is_good_form": True, "issues": []}

        # --- Check 1: back angle / forward lean ---
        back_angle = calculate_angle(shoulder, hip, knee)
        if back_angle < BACK_LEAN_MIN_DEGREES:
            issues.append("Back leaning too far forward — keep your chest up")

        # --- Check 2: knees past toes, only near the bottom of the squat ---
        knee_angle = calculate_angle(hip, knee, ankle)
        near_bottom = knee_angle <= (self.down_threshold + BOTTOM_OF_SQUAT_ANGLE_MARGIN_DEGREES)
        if near_bottom:
            knee_px, _, knee_px_vis = get_landmark_xy(landmarks, knee_lm, w, h)
            ankle_px, _, ankle_px_vis = get_landmark_xy(landmarks, ankle_lm, w, h)
            if min(knee_px_vis, ankle_px_vis) >= VISIBILITY_THRESHOLD:
                # Note: this is a magnitude check (not signed), since which
                # direction "past the toe" is depends on which way the
                # person is facing the camera.
                knee_past_toe_px = abs(knee_px - ankle_px)
                if knee_past_toe_px > KNEE_PAST_TOE_TOLERANCE_PX:
                    issues.append("Knees going too far past toes")

        return {"is_good_form": len(issues) == 0, "issues": issues}

    def get_landmarks_to_draw(self) -> list:
        return [
            PoseLandmark.LEFT_SHOULDER, PoseLandmark.RIGHT_SHOULDER,
            PoseLandmark.LEFT_HIP, PoseLandmark.RIGHT_HIP,
            PoseLandmark.LEFT_KNEE, PoseLandmark.RIGHT_KNEE,
            PoseLandmark.LEFT_ANKLE, PoseLandmark.RIGHT_ANKLE,
        ]
