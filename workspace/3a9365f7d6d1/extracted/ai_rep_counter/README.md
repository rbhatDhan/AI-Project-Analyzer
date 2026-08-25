# AI Rep Counter

A real-time webcam application that uses MediaPipe Pose to count exercise
repetitions (Bicep Curl or Squat) via a joint-angle state machine, checks
your form as you go, and produces a session report (CSV + chart) when
you're done. Built with OpenCV for video capture/drawing, MediaPipe for
pose landmarks, and Streamlit for the UI.

## Setup

```bash
pip install -r requirements.txt
streamlit run app.py
```

A webcam is required. On first run, pick an exercise from the sidebar and
click **Start Session** — you'll get a 5-second calibration countdown
("Stand in starting position: 5... 4... 3... 2... 1...") before live
tracking begins. Click **Stop & Show Report** at any time to end the
session and see your results (also saved to `output/`).

## Project Structure

```
ai_rep_counter/
├── requirements.txt
├── app.py                  # Streamlit entry point (UI + live video loop)
├── pose_utils.py            # calculate_angle(), landmark helpers
├── exercises/
│   ├── base_exercise.py     # BaseExercise abstract interface
│   ├── bicep_curl.py        # BicepCurl(BaseExercise)
│   └── squat.py              # Squat(BaseExercise)
├── rep_counter.py            # Exercise-agnostic RepCounter state machine
├── session_logger.py         # Per-rep CSV logging + PNG report generation
└── output/                   # Session CSVs and PNG reports land here
```

## Design Decisions

**Why angle-based tracking instead of raw frame classification?**
A frame classifier (e.g. a CNN trained to output "up" / "down" / "mid" per
frame) would need a labeled training set per exercise, wouldn't generalize
to a new exercise without retraining, and gives no natural handle on *form*
— you'd need a second model for that too. Computing a joint angle from
MediaPipe's already-detected landmarks is essentially free, generalizes
immediately to any exercise you can describe as "some joint moving between
two angular states" (curls, squats, push-ups, lateral raises, ...), and the
exact same angle used for rep counting can be reused or extended for form
checks (e.g. the shoulder and back angles here). It's also fully
interpretable — you can explain *why* a rep counted or didn't, frame by
frame, which matters a lot for debugging and for explaining the system to
someone else.

**Why does the state machine debounce with `min_frames_in_state`?**
MediaPipe's landmark estimates aren't perfectly stable frame to frame —
small tracking jitter can make a joint angle hover right at a threshold and
cross it multiple times in a row even though the person isn't actually
moving. If we counted a state transition the instant the angle crossed a
threshold, that jitter would register as several rapid up/down transitions
instead of zero. Requiring the angle to stay on the new side of the
threshold for several consecutive frames before accepting the transition
filters that out, at the cost of a small, imperceptible bit of latency
(a few frames) before a rep registers.

**Why calibration instead of fixed thresholds?**
Two people with different limb proportions, shoulder mobility, or camera
angle will have genuinely different "neutral" joint angles even when both
are doing the exercise correctly. The rep-counting thresholds themselves
(down/up angle) are kept fixed per the spec, since "fully curled" and
"fully extended" are reasonably universal end-states. But form checks like
"is your shoulder angle drifting" only make sense relative to *that
person's own starting posture* — a fixed absolute threshold would flag
naturally mobile shoulders as bad form for one person and miss real
swinging in someone who starts more rigid. Calibrating against the user's
own baseline makes the form feedback personalized instead of one-size-fits-none.

**Trade-off: single primary angle vs. multi-signal fusion**
Using one angle (elbow or knee) to drive rep counting keeps the state
machine simple, fast, and easy to reason about and debug — there's exactly
one number to look at. The cost is that it's blind to anything that angle
doesn't capture: a bicep curl could theoretically "complete" via elbow
angle alone even if the whole rep was done with terrible form, which is
why form-checking is handled as a *separate* signal (shoulder angle,
back angle, knee-vs-toe position) rather than folding everything into one
fused score. A more sophisticated version could fuse multiple joint angles
into a single weighted "rep confidence" signal, which would be more robust
to a single noisy landmark, at the cost of being much harder to tune and
explain.

**What's next**
- Multi-exercise generalization: right now BicepCurl and Squat each
  hand-pick their primary/secondary joints; a config-driven exercise
  definition (angle triplets + thresholds specified as data, not code)
  would let new exercises be added without writing a new Python class.
- Form scoring instead of binary good/bad: right now `check_form()` returns
  a boolean plus a list of issues. A continuous 0-100 form score (e.g.
  based on how far into the "bad" zone each metric drifted) would give
  richer session-over-session progress tracking than a strict pass/fail.
- Multi-signal fusion for rep counting itself (see trade-off above), to
  reduce sensitivity to any single landmark's noise.

## Known Limitations

- The live video loop uses Streamlit's `st.fragment(run_every=...)` (see
  the comment at the top of `app.py`) rather than a literal blocking
  `while` loop, because a truly blocking loop would make the Stop button
  unresponsive — Streamlit can't process a new button click while a script
  call is still running. The fragment achieves the same "redraw a
  placeholder every frame" behavior while keeping Stop responsive.
- Calibration and rep-counting both require a full, well-lit view of the
  relevant joints; heavy occlusion or extreme camera angles will fall back
  to skipped-frame form checks (see Section 7 error handling) rather than
  producing bad data.
