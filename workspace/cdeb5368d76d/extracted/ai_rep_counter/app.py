"""
app.py

Streamlit entry point for AI Rep Counter.

Flow:
    1. User picks an exercise from the sidebar and clicks "Start Session".
    2. A 5-second on-screen calibration countdown runs; the primary and
       secondary (form-check) angles are averaged over the final 2 seconds
       and stored as this user's personal baseline.
    3. Live rep counting + form checking begins, drawing the MediaPipe
       skeleton and overlaying rep count / form status on each frame.
    4. User clicks "Stop & Show Report"; the webcam is released and the
       session report (CSV + PNG) is generated and displayed in-app.

Streamlit live-video pattern -- design note
--------------------------------------------
The spec calls for "the standard pattern for live video: a while loop with
st.empty() updated each frame". A naive `while True: ... st.image(...)`
loop, however, runs as one long blocking script execution -- Streamlit
can't process a new button click (like "Stop & Show Report") until that
script call *returns*, so a literal infinite while loop would make Stop
unresponsive.

To get the "redraw a placeholder every frame" behavior the spec asks for
AND a Stop button that actually works, this app uses
`st.fragment(run_every=...)` (stable since Streamlit ~1.33, available in
the 1.37 version pinned here): the per-frame capture/inference/draw logic
lives in a fragment that Streamlit reruns on its own short timer,
independently of the rest of the page. Sidebar button clicks outside the
fragment still trigger a normal full-script rerun and are handled
immediately, so "Stop & Show Report" takes effect on the very next tick
instead of being queued behind an unbounded loop. Camera handle, exercise
instance, rep counter and logger live in `st.session_state` so they persist
across fragment reruns instead of being recreated every frame.
"""

import os
import time
import urllib.request

import cv2
import mediapipe as mp
import numpy as np
import pandas as pd
import streamlit as st
from mediapipe.tasks.python import BaseOptions
from mediapipe.tasks.python.vision import (
    PoseLandmarker,
    PoseLandmarkerOptions,
    RunningMode,
)

from exercises.bicep_curl import BicepCurl
from exercises.squat import Squat
from pose_utils import AngleSmoother, IssueDebouncer, calculate_angle, draw_pose_landmarks, get_landmark_norm_xy
from rep_counter import RepCounter
from session_logger import SessionLogger

# The `mediapipe.solutions.pose` legacy API (mp.solutions.pose / mp_drawing)
# was removed from recent mediapipe PyPI releases -- see the docstring in
# pose_landmark_enum.py. This app uses the modern `mediapipe.tasks` Pose
# Landmarker API instead, which is what current `pip install mediapipe`
# actually ships. It needs a small model file downloaded once; see
# ensure_pose_model() below.
#
# MediaPipe ships three Pose Landmarker model sizes with the same 33-point
# output but different accuracy/speed trade-offs: "lite" (fastest, least
# accurate), "full" (balanced), and "heavy" (most accurate, slowest). This
# app defaults to "full" for meaningfully better landmark accuracy than
# "lite" -- which directly improves both rep-counting (less angle noise
# feeding the state machine) and form-checking (cleaner secondary-angle
# readings) -- while still running comfortably in real time on a typical
# laptop CPU. "heavy" is available below if you want to trade some frame
# rate for even more accuracy.
POSE_MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".models")
MODEL_VARIANTS = {
    "full": {
        "filename": "pose_landmarker_full.task",
        "url": (
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_full/float16/1/pose_landmarker_full.task"
        ),
    },
    "heavy": {
        "filename": "pose_landmarker_heavy.task",
        "url": (
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_heavy/float16/1/pose_landmarker_heavy.task"
        ),
    },
    "lite": {
        "filename": "pose_landmarker_lite.task",
        "url": (
            "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
            "pose_landmarker_lite/float16/1/pose_landmarker_lite.task"
        ),
    },
}
DEFAULT_MODEL_VARIANT = "full"

# Confidence thresholds for the pose model. NOTE: these were previously
# raised to 0.6 in an attempt to reduce noisy detections, but that traded
# away real detections at the exact extreme-of-motion frames (full curl /
# full squat depth) where motion blur and joint occlusion naturally lower
# confidence -- precisely the frames rep-counting depends on. Kept at a
# more permissive 0.5 so genuine reps aren't silently dropped.
MIN_DETECTION_CONFIDENCE = 0.5
MIN_TRACKING_CONFIDENCE = 0.5
MIN_POSE_PRESENCE_CONFIDENCE = 0.5

# Requested webcam capture resolution. Most webcams will honor this (or the
# closest mode they support); a larger source frame means the video panel
# renders sharper once Streamlit stretches it to fill the page width.
CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720


def ensure_pose_model(variant: str = DEFAULT_MODEL_VARIANT) -> str:
    """
    Downloads the requested Pose Landmarker model variant to a local cache
    folder next to this script, the first time it's needed. Subsequent runs
    reuse the cached file with no network access required. Returns the
    local file path.
    """
    spec = MODEL_VARIANTS[variant]
    os.makedirs(POSE_MODEL_DIR, exist_ok=True)
    model_path = os.path.join(POSE_MODEL_DIR, spec["filename"])
    if not os.path.exists(model_path):
        try:
            urllib.request.urlretrieve(spec["url"], model_path)
        except Exception as e:
            # Clean up any partial download so a retry doesn't load a
            # truncated/corrupt model file.
            if os.path.exists(model_path):
                os.remove(model_path)
            raise RuntimeError(
                f"Couldn't download the pose model from {spec['url']} "
                f"({e}). Check your internet connection, or if you're on a "
                "restricted/corporate network, download that file manually "
                f"and save it to: {model_path}"
            ) from e
    return model_path


def create_pose_landmarker(variant: str = DEFAULT_MODEL_VARIANT) -> PoseLandmarker:
    model_path = ensure_pose_model(variant)
    options = PoseLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=model_path),
        running_mode=RunningMode.VIDEO,
        min_pose_detection_confidence=MIN_DETECTION_CONFIDENCE,
        min_tracking_confidence=MIN_TRACKING_CONFIDENCE,
        min_pose_presence_confidence=MIN_POSE_PRESENCE_CONFIDENCE,
    )
    return PoseLandmarker.create_from_options(options)


EXERCISES = {
    "Bicep Curl": BicepCurl,
    "Squat": Squat,
}

CALIBRATION_SECONDS = 5
CALIBRATION_AVERAGE_WINDOW_SECONDS = 2  # average over the final 2 seconds
NO_POSE_FRAME_LIMIT = 30
FRAME_TICK_SECONDS = 0.03  # ~30fps fragment refresh rate


# ---------------------------------------------------------------------------
# Session state setup
# ---------------------------------------------------------------------------

def init_session_state():
    defaults = {
        "phase": "idle",  # idle -> calibrating -> live -> stopped
        "exercise_name": None,
        "exercise": None,
        "model_variant": DEFAULT_MODEL_VARIANT,
        "cap": None,
        "pose": None,
        "rep_counter": None,
        "logger": None,
        "angle_smoother": None,
        "issue_debouncer": None,
        "no_pose_streak": 0,
        "last_issues": [],
        "last_good_form": True,
        "calibration_start_time": None,
        "calibration_primary_samples": [],
        "calibration_secondary_samples": [],
        "debug_raw_angle": None,
        "debug_smoothed_angle": None,
        "debug_state": None,
        "debug_raw_issues": [],
        "show_debug": True,
        "csv_path": None,
        "png_path": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def teardown_capture():
    if st.session_state.get("cap") is not None:
        st.session_state["cap"].release()
        st.session_state["cap"] = None
    if st.session_state.get("pose") is not None:
        st.session_state["pose"].close()
        st.session_state["pose"] = None


# ---------------------------------------------------------------------------
# Secondary-angle helper (used only during calibration sampling, since
# check_form()'s own secondary-angle math depends on calibration already
# being set -- see exercises/bicep_curl.py and exercises/squat.py docstrings)
# ---------------------------------------------------------------------------

def get_secondary_calibration_angle(exercise, landmarks):
    if isinstance(exercise, BicepCurl):
        side = exercise._select_side(landmarks)
        shoulder_lm, elbow_lm, wrist_lm, hip_lm = exercise._joint_points(side)
        elbow, ev = get_landmark_norm_xy(landmarks, elbow_lm)
        shoulder, sv = get_landmark_norm_xy(landmarks, shoulder_lm)
        hip, hv = get_landmark_norm_xy(landmarks, hip_lm)
        if min(ev, sv, hv) < 0.5:
            return None
        return calculate_angle(elbow, shoulder, hip)

    if isinstance(exercise, Squat):
        side = exercise._select_side(landmarks)
        shoulder_lm, hip_lm, knee_lm, _ankle_lm = exercise._joint_points(side)
        shoulder, sv = get_landmark_norm_xy(landmarks, shoulder_lm)
        hip, hv = get_landmark_norm_xy(landmarks, hip_lm)
        knee, kv = get_landmark_norm_xy(landmarks, knee_lm)
        if min(sv, hv, kv) < 0.5:
            return None
        return calculate_angle(shoulder, hip, knee)

    return None


# ---------------------------------------------------------------------------
# Per-frame fragment: this is what makes the Stop button responsive. It
# reruns on its own timer (FRAME_TICK_SECONDS) independent of the rest of
# the page, and checks st.session_state["phase"] fresh on every tick.
# ---------------------------------------------------------------------------

@st.fragment(run_every=FRAME_TICK_SECONDS)
def video_fragment():
    phase = st.session_state["phase"]
    if phase not in ("calibrating", "live"):
        return

    cap = st.session_state["cap"]
    landmarker = st.session_state["pose"]
    exercise = st.session_state["exercise"]

    ok, frame = cap.read()
    if not ok:
        st.error("Lost connection to webcam.")
        st.session_state["phase"] = "stopped"
        teardown_capture()
        return

    frame = cv2.flip(frame, 1)
    h, w, _ = frame.shape
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

    # PoseLandmarker in VIDEO mode needs a monotonically increasing
    # millisecond timestamp per frame (used for its internal tracker, not
    # wall-clock accuracy), so we just use time.time() scaled to ms.
    timestamp_ms = int(time.time() * 1000)
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
    results = landmarker.detect_for_video(mp_image, timestamp_ms)
    display_frame = frame.copy()

    if results.pose_landmarks:
        st.session_state["no_pose_streak"] = 0
        landmarks = results.pose_landmarks[0]  # first (only) detected person
        draw_pose_landmarks(display_frame, landmarks, w, h)

        if phase == "calibrating":
            _calibration_tick(exercise, landmarks, display_frame)
        else:  # phase == "live"
            _live_tick(exercise, landmarks, w, h)
    else:
        st.session_state["no_pose_streak"] += 1
        if st.session_state["no_pose_streak"] > NO_POSE_FRAME_LIMIT:
            cv2.putText(display_frame, "No person detected - please step into frame",
                        (30, h - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 0, 255), 2, cv2.LINE_AA)

    if phase == "live":
        rep_counter = st.session_state["rep_counter"]
        cv2.putText(display_frame, f"Reps: {rep_counter.rep_count}", (30, 60),
                    cv2.FONT_HERSHEY_SIMPLEX, 1.4, (255, 255, 255), 3, cv2.LINE_AA)
        if st.session_state["last_good_form"]:
            cv2.putText(display_frame, "Good form", (w - 300, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 200, 0), 2, cv2.LINE_AA)
        else:
            y = 60
            for issue in st.session_state["last_issues"]:
                cv2.putText(display_frame, issue, (max(10, w - 620), y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 255), 2, cv2.LINE_AA)
                y += 30

        if st.session_state.get("show_debug"):
            raw_a = st.session_state.get("debug_raw_angle")
            smoothed_a = st.session_state.get("debug_smoothed_angle")
            debug_state = st.session_state.get("debug_state")
            raw_issues = st.session_state.get("debug_raw_issues") or []
            down_t = exercise.down_threshold
            up_t = exercise.up_threshold
            if raw_a is not None:
                debug_lines = [
                    f"raw angle: {raw_a:.1f}  smoothed: {smoothed_a:.1f}  state: {debug_state}",
                    f"thresholds -> down<={down_t}  up>={up_t}",
                    f"raw issues (pre-debounce): {raw_issues if raw_issues else 'none'}",
                ]
                y = h - 80
                for line in debug_lines:
                    cv2.putText(display_frame, line, (20, y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 0), 1, cv2.LINE_AA)
                    y += 24

    st.image(display_frame, channels="BGR", use_column_width=True)

    if phase == "calibrating":
        remaining = CALIBRATION_SECONDS - (time.time() - st.session_state["calibration_start_time"])
        if remaining <= 0:
            _finish_calibration()
        else:
            st.info(f"Stand in starting position: {max(1, int(remaining) + 1)}...")
    elif phase == "live":
        st.metric("Reps completed", st.session_state["rep_counter"].rep_count)


def _calibration_tick(exercise, landmarks, display_frame):
    elapsed = time.time() - st.session_state["calibration_start_time"]
    cv2.putText(display_frame,
                f"Stand in starting position: {max(1, int(CALIBRATION_SECONDS - elapsed) + 1)}...",
                (30, 60), cv2.FONT_HERSHEY_SIMPLEX, 1.1, (0, 215, 255), 3, cv2.LINE_AA)

    # Only accumulate samples in the final averaging window so "getting
    # into position" frames at the start don't skew the baseline.
    if elapsed >= (CALIBRATION_SECONDS - CALIBRATION_AVERAGE_WINDOW_SECONDS):
        try:
            h_, w_ = display_frame.shape[:2]
            raw_primary_angle = exercise.get_primary_angle(landmarks, w_, h_)
            # Smooth here too (same smoother instance used in the live
            # phase) so a single noisy frame doesn't skew the personal
            # baseline the rest of the session gets compared against.
            smoothed_primary_angle = st.session_state["angle_smoother"].update(raw_primary_angle)
            st.session_state["calibration_primary_samples"].append(smoothed_primary_angle)
            secondary_angle = get_secondary_calibration_angle(exercise, landmarks)
            if secondary_angle is not None:
                st.session_state["calibration_secondary_samples"].append(secondary_angle)
        except (IndexError, ValueError):
            pass


def _finish_calibration():
    exercise = st.session_state["exercise"]
    primary_samples = st.session_state["calibration_primary_samples"]
    secondary_samples = st.session_state["calibration_secondary_samples"]

    if not primary_samples:
        st.error(
            "Couldn't get a reliable reading during calibration — make sure your "
            "full body is visible and click Start Session again."
        )
        st.session_state["phase"] = "stopped"
        teardown_capture()
        return

    avg_primary = float(np.mean(primary_samples))
    avg_secondary = float(np.mean(secondary_samples)) if secondary_samples else None

    if isinstance(exercise, BicepCurl):
        exercise.set_calibration_baseline(shoulder_angle=avg_secondary if avg_secondary is not None else 0.0)
    elif isinstance(exercise, Squat):
        exercise.set_calibration_baseline(
            knee_angle=avg_primary,
            back_angle=avg_secondary if avg_secondary is not None else 0.0,
        )

    st.session_state["rep_counter"] = RepCounter(
        **exercise.get_rep_counter_kwargs(), min_frames_in_state=2
    )
    st.session_state["logger"] = SessionLogger(
        exercise_name=exercise.name,
        calibration_baseline={"primary_angle": avg_primary, "secondary_angle": avg_secondary},
    )
    st.session_state["phase"] = "live"


def _live_tick(exercise, landmarks, w, h):
    rep_counter = st.session_state["rep_counter"]
    logger = st.session_state["logger"]
    smoother = st.session_state["angle_smoother"]
    debouncer = st.session_state["issue_debouncer"]
    try:
        raw_primary_angle = exercise.get_primary_angle(landmarks, w, h)
        # Smooth the angle before it drives the state machine (see
        # AngleSmoother docstring in pose_utils.py) -- this removes most
        # frame-to-frame landmark jitter at the source, rather than relying
        # solely on RepCounter's frame-count debounce to absorb it.
        smoothed_primary_angle = smoother.update(raw_primary_angle)
        update_result = rep_counter.update(smoothed_primary_angle)

        form_result = exercise.check_form(landmarks, w, h)
        # Debounce the raw per-frame issue list with hysteresis (see
        # IssueDebouncer docstring) so a single noisy frame doesn't flash a
        # false "bad form" warning, and a real issue doesn't flicker off
        # for one clean frame in the middle of a genuine fault.
        debounced_issues = debouncer.update(form_result["issues"])
        st.session_state["last_good_form"] = len(debounced_issues) == 0
        st.session_state["last_issues"] = debounced_issues

        # Debug snapshot -- surfaced on-screen when "Show debug overlay" is
        # checked in the sidebar, so mismatches between what you're doing
        # and what the app reports can be diagnosed from the actual numbers
        # instead of guessing.
        st.session_state["debug_raw_angle"] = raw_primary_angle
        st.session_state["debug_smoothed_angle"] = smoothed_primary_angle
        st.session_state["debug_state"] = update_result["state"]
        st.session_state["debug_raw_issues"] = form_result["issues"]

        if update_result["rep_completed"]:
            logger.log_rep(
                rep_number=update_result["rep_count"],
                is_good_form=st.session_state["last_good_form"],
                issues=st.session_state["last_issues"],
                primary_angle_at_completion=smoothed_primary_angle,
            )
    except (IndexError, ValueError):
        # Momentary bad landmark data -- skip counting/form-check this
        # frame rather than crashing the session.
        pass


# ---------------------------------------------------------------------------
# Main page
# ---------------------------------------------------------------------------

def main():
    st.set_page_config(page_title="AI Rep Counter", layout="wide")
    init_session_state()

    st.title("AI Rep Counter")
    st.caption("Real-time rep counting and form feedback using MediaPipe Pose.")

    running = st.session_state["phase"] in ("calibrating", "live")

    with st.sidebar:
        st.header("Session Controls")
        exercise_name = st.selectbox("Select exercise", list(EXERCISES.keys()), disabled=running)
        model_variant = st.selectbox(
            "Detection accuracy",
            list(MODEL_VARIANTS.keys()),
            index=list(MODEL_VARIANTS.keys()).index(st.session_state["model_variant"]),
            disabled=running,
            help=(
                "full (default): balanced accuracy/speed. heavy: most accurate, "
                "may reduce frame rate on slower machines. lite: fastest, least accurate."
            ),
        )
        st.session_state["model_variant"] = model_variant
        st.session_state["show_debug"] = st.checkbox(
            "Show debug overlay",
            value=st.session_state["show_debug"],
            help="Shows the live raw/smoothed angle, state, and pre-debounce form issues on the video, to help diagnose miscounts.",
        )
        start_clicked = st.button("Start Session", disabled=running, use_container_width=True)
        stop_clicked = st.button("Stop & Show Report", disabled=not running, use_container_width=True)

    if start_clicked and not running:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            st.error("No webcam found. Please connect a camera and try again.")
            return

        # Request a larger capture resolution so the video panel renders
        # sharper once stretched to the page width. Most webcams will honor
        # this or fall back to their closest supported mode -- either way
        # this is a request, not a guarantee, so we don't assume it landed.
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, CAPTURE_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, CAPTURE_HEIGHT)

        st.session_state["cap"] = cap
        try:
            with st.spinner("Loading pose model (first run downloads a small model file)..."):
                st.session_state["pose"] = create_pose_landmarker(model_variant)
        except Exception as e:
            st.error(str(e))
            cap.release()
            st.session_state["cap"] = None
            return
        st.session_state["exercise"] = EXERCISES[exercise_name]()
        st.session_state["exercise_name"] = exercise_name
        st.session_state["angle_smoother"] = AngleSmoother(alpha=0.6)
        st.session_state["issue_debouncer"] = IssueDebouncer(min_frames_on=3, min_frames_off=5)
        st.session_state["no_pose_streak"] = 0
        st.session_state["calibration_start_time"] = time.time()
        st.session_state["calibration_primary_samples"] = []
        st.session_state["calibration_secondary_samples"] = []
        st.session_state["csv_path"] = None
        st.session_state["png_path"] = None
        st.session_state["phase"] = "calibrating"
        st.rerun()

    if stop_clicked and running:
        logger = st.session_state["logger"]
        teardown_capture()
        st.session_state["phase"] = "stopped"
        if logger is not None:
            csv_path, png_path = logger.generate_report()
            st.session_state["csv_path"] = csv_path
            st.session_state["png_path"] = png_path
        st.rerun()

    if st.session_state["phase"] in ("calibrating", "live"):
        video_fragment()

    if st.session_state.get("csv_path") and st.session_state.get("png_path"):
        st.subheader("Session Report")
        st.image(st.session_state["png_path"])
        st.dataframe(pd.read_csv(st.session_state["csv_path"]))


if __name__ == "__main__":
    main()
