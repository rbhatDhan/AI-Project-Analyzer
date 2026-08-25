"""
pose_utils.py

Shared geometry helpers used by every exercise module:
    - calculate_angle(): the joint-angle calculation that drives both rep counting
      and form checking.
    - get_landmark_xy(): converts a MediaPipe normalized landmark into pixel
      coordinates for drawing / distance checks.

Kept exercise-agnostic on purpose so bicep_curl.py and squat.py (and any future
exercise module) can both depend on it without duplicating math.
"""

import math

import cv2

from pose_landmark_enum import POSE_CONNECTIONS


def calculate_angle(a, b, c) -> float:
    """
    Compute the angle ABC (the angle at vertex b) formed by points a-b-c.

    a, b, c: each a tuple/list of (x, y) coordinates. These can be normalized
        MediaPipe coordinates (0-1) or pixel coordinates -- the angle is scale
        invariant, so either works as long as all three points use the same
        coordinate system.

    Returns the angle in degrees, in the range [0, 180].

    Implementation note: we deliberately use math.atan2 on the two vectors
    (b->a) and (b->c) rather than the law of cosines (arccos of a dot-product
    ratio). The law-of-cosines approach involves dividing by the product of
    two vector magnitudes and then calling arccos on the result; when the
    angle is near 0 or 180 degrees that ratio sits right at the edge of
    arccos's domain (+/-1), so ordinary floating point error can push it
    just outside [-1, 1] and raise a domain error / return NaN. atan2-based
    angle-of-each-vector subtraction has no such division-heavy step and
    stays numerically stable across the full 0-180 range, which matters here
    because both a fully extended elbow (~180) and a fully contracted elbow
    (~0-50) are exactly the operating points we care about.
    """
    ax, ay = a
    bx, by = b
    cx, cy = c

    # Angle of vector b->a and vector b->c relative to the x-axis
    angle_ba = math.atan2(ay - by, ax - bx)
    angle_bc = math.atan2(cy - by, cx - bx)

    angle = math.degrees(angle_ba - angle_bc)
    angle = abs(angle)

    # atan2 difference can exceed 180 (e.g. 350 degrees for what is really a
    # 10 degree angle going the "short way"), so fold it back into [0, 180].
    if angle > 180.0:
        angle = 360.0 - angle

    return angle


def get_landmark_xy(landmarks, landmark_enum, image_width: int, image_height: int):
    """
    Convert a single MediaPipe normalized landmark (x, y in [0, 1]) into pixel
    coordinates for the given image size.

    landmarks: the `landmark` list from a MediaPipe PoseLandmarkerResult /
        NormalizedLandmarkList (i.e. `results.pose_landmarks.landmark`).
    landmark_enum: a `mediapipe.solutions.pose.PoseLandmark` enum member
        (e.g. PoseLandmark.RIGHT_ELBOW). Its `.value` is used to index into
        `landmarks`.
    image_width, image_height: pixel dimensions of the frame the landmarks
        should be projected onto.

    Returns (x_px, y_px, visibility) as a 3-tuple so callers can immediately
    do a visibility check without a second lookup.
    """
    lm = landmarks[landmark_enum.value]
    x_px = lm.x * image_width
    y_px = lm.y * image_height
    return x_px, y_px, lm.visibility


def get_landmark_norm_xy(landmarks, landmark_enum):
    """
    Like get_landmark_xy but returns the raw normalized (0-1) coordinates
    instead of pixel coordinates. Angle calculations don't need pixel scale,
    so exercise modules use this for anything that feeds calculate_angle(),
    and reserve get_landmark_xy() for drawing and the pixel-distance based
    "knees past toes" check in Squat.check_form().
    """
    lm = landmarks[landmark_enum.value]
    return (lm.x, lm.y), lm.visibility


def draw_pose_landmarks(frame, landmarks, w: int, h: int, visibility_threshold: float = 0.5):
    """
    Draws the BlazePose skeleton (points + connecting lines) directly onto
    `frame` with OpenCV. Stands in for the old
    `mediapipe.solutions.drawing_utils.draw_landmarks()`, which relied on
    the `mediapipe.solutions` module that newer mediapipe releases no
    longer ship (see pose_landmark_enum.py docstring for details).

    landmarks: the `pose_landmarks[0]` list from a PoseLandmarker
        VIDEO-mode detection result (one NormalizedLandmark per BlazePose
        point, each with .x, .y, .visibility in [0, 1]).
    Mutates `frame` in place and also returns it for convenience.
    """
    for start_lm, end_lm in POSE_CONNECTIONS:
        start = landmarks[start_lm.value]
        end = landmarks[end_lm.value]
        if start.visibility < visibility_threshold or end.visibility < visibility_threshold:
            continue
        start_px = (int(start.x * w), int(start.y * h))
        end_px = (int(end.x * w), int(end.y * h))
        cv2.line(frame, start_px, end_px, (0, 255, 0), 2, cv2.LINE_AA)

    for lm in landmarks:
        if lm.visibility < visibility_threshold:
            continue
        px = (int(lm.x * w), int(lm.y * h))
        cv2.circle(frame, px, 4, (0, 128, 255), -1, cv2.LINE_AA)

    return frame


class AngleSmoother:
    """
    Exponential moving average (EMA) smoother for a single angle stream.

    Landmark noise from the pose model makes the raw per-frame angle jitter
    by a few degrees even when a joint is genuinely still. Feeding that raw
    signal into RepCounter works (the state machine's own debounce catches
    most of it), but smoothing the angle *before* it reaches the state
    machine removes the jitter at the source, which both reduces the risk
    of a borderline rep flickering across a threshold and lets the angle
    used for logging/reporting better reflect the true joint position.

    alpha controls responsiveness vs. smoothness: alpha=1.0 is no smoothing
    (pure raw signal), lower alpha smooths more but adds a little lag. 0.4
    is a reasonable middle ground for ~30fps webcam input -- smooths out
    single-frame noise spikes without meaningfully delaying real movement.
    """

    def __init__(self, alpha: float = 0.4):
        if not (0.0 < alpha <= 1.0):
            raise ValueError("alpha must be in (0, 1]")
        self.alpha = alpha
        self._value = None

    def update(self, raw_value: float) -> float:
        if self._value is None:
            self._value = raw_value
        else:
            self._value = self.alpha * raw_value + (1.0 - self.alpha) * self._value
        return self._value

    def reset(self):
        self._value = None


class IssueDebouncer:
    """
    Debounces the frame-by-frame set of form-issue strings returned by
    Exercise.check_form(), so a single noisy frame doesn't flash a
    false-positive (or false-negative) form warning on screen.

    Uses hysteresis: an issue must be present for `min_frames_on`
    consecutive frames before it's reported as confirmed, and must then be
    *absent* for `min_frames_off` consecutive frames before it's cleared.
    Requiring sustained absence (not just one clean frame) before clearing
    prevents an issue from flickering off and back on right at the boundary
    of a threshold, which is exactly the kind of noise a shaky landmark
    reading produces.
    """

    def __init__(self, min_frames_on: int = 4, min_frames_off: int = 4):
        self.min_frames_on = min_frames_on
        self.min_frames_off = min_frames_off
        self._on_counts = {}
        self._off_counts = {}
        self._confirmed = set()

    def update(self, raw_issues) -> list:
        raw_set = set(raw_issues)

        for issue in raw_set:
            self._on_counts[issue] = self._on_counts.get(issue, 0) + 1
            self._off_counts[issue] = 0
            if self._on_counts[issue] >= self.min_frames_on:
                self._confirmed.add(issue)

        for issue in list(self._confirmed):
            if issue not in raw_set:
                self._off_counts[issue] = self._off_counts.get(issue, 0) + 1
                self._on_counts[issue] = 0
                if self._off_counts[issue] >= self.min_frames_off:
                    self._confirmed.discard(issue)

        # Decay on-counts for issues that vanished before being confirmed,
        # so a brief flicker doesn't leave a stale partial count lying
        # around to combine with an unrelated later flicker.
        for issue in list(self._on_counts.keys()):
            if issue not in raw_set and issue not in self._confirmed:
                self._on_counts[issue] = 0

        return sorted(self._confirmed)

    def reset(self):
        self._on_counts.clear()
        self._off_counts.clear()
        self._confirmed.clear()
