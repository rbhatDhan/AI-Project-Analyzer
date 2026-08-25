"""
session_logger.py

Handles per-rep logging during a session and end-of-session report
generation (CSV + matplotlib PNG + console summary).

Kept independent of Streamlit and MediaPipe so it can be unit-tested or
reused (e.g. from a CLI version of this tool) without pulling in either.
"""

import os
from collections import Counter
from datetime import datetime

import matplotlib
matplotlib.use("Agg")  # headless backend -- required for Streamlit's server process
import matplotlib.pyplot as plt
import pandas as pd

OUTPUT_DIR = "output"


class SessionLogger:
    def __init__(self, exercise_name: str, calibration_baseline: dict | None = None):
        """
        exercise_name: display name of the exercise being logged (e.g. "Bicep Curl").
        calibration_baseline: dict of calibration values captured before the
            session started (e.g. {"primary_angle": .., "secondary_angle": ..}).
            Logged as constant columns on every row per spec section 4.4,
            so the CSV is self-contained for later analysis without needing
            a separate calibration file.
        """
        self.exercise_name = exercise_name
        self.calibration_baseline = calibration_baseline or {}
        self.rows = []
        self.session_id = datetime.now().strftime("%Y%m%d_%H%M%S")

        os.makedirs(OUTPUT_DIR, exist_ok=True)

    def log_rep(self, rep_number: int, is_good_form: bool, issues: list, primary_angle_at_completion: float):
        """Append one completed rep to the in-memory session log."""
        row = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "exercise_name": self.exercise_name,
            "rep_number": rep_number,
            "is_good_form": is_good_form,
            "issues": ";".join(issues) if issues else "",
            "primary_angle_at_completion": round(primary_angle_at_completion, 1),
        }
        # Log calibration baseline on every row (spec 4.4) so the CSV is
        # self-explanatory even if viewed in isolation.
        for key, value in self.calibration_baseline.items():
            row[f"calibration_{key}"] = round(value, 1) if isinstance(value, (int, float)) else value
        self.rows.append(row)

    def has_data(self) -> bool:
        return len(self.rows) > 0

    def _csv_path(self) -> str:
        return os.path.join(OUTPUT_DIR, f"session_{self.session_id}.csv")

    def _report_png_path(self) -> str:
        return os.path.join(OUTPUT_DIR, f"session_{self.session_id}_report.png")

    def save_csv(self) -> str:
        """Write the accumulated rows to CSV. Returns the file path."""
        df = pd.DataFrame(self.rows)
        path = self._csv_path()
        df.to_csv(path, index=False)
        return path

    def generate_report(self) -> tuple[str, str]:
        """
        Generate the end-of-session report: a two-panel matplotlib PNG
        (rep-by-rep good/bad bar chart + text summary box) and the CSV.
        Also prints a plain-text summary to the console.

        Returns (csv_path, png_path).
        """
        csv_path = self.save_csv()

        if not self.rows:
            # No reps were completed -- still produce a minimal, non-crashing
            # report rather than erroring out on an empty session.
            fig, ax = plt.subplots(figsize=(8, 4))
            ax.axis("off")
            ax.text(0.5, 0.5, "No reps were completed this session.",
                     ha="center", va="center", fontsize=14)
            png_path = self._report_png_path()
            fig.savefig(png_path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            print("\n=== Session Summary ===")
            print(f"Exercise: {self.exercise_name}")
            print("Total reps: 0")
            return csv_path, png_path

        df = pd.DataFrame(self.rows)
        total_reps = len(df)
        good_reps = int(df["is_good_form"].sum())
        good_pct = 100.0 * good_reps / total_reps

        all_issues = []
        for issues_str in df["issues"]:
            if issues_str:
                all_issues.extend(issues_str.split(";"))
        issue_counts = Counter(all_issues)
        most_common_issue = issue_counts.most_common(1)[0][0] if issue_counts else "None"

        fig, (ax_bar, ax_text) = plt.subplots(1, 2, figsize=(12, 5), gridspec_kw={"width_ratios": [3, 2]})

        # --- Subplot 1: rep number vs good/bad form bar chart ---
        colors = ["#2ca02c" if good else "#d62728" for good in df["is_good_form"]]
        ax_bar.bar(df["rep_number"], [1] * total_reps, color=colors)
        ax_bar.set_xlabel("Rep Number")
        ax_bar.set_yticks([])
        ax_bar.set_title(f"{self.exercise_name} — Form Quality by Rep")
        ax_bar.set_xticks(df["rep_number"])

        # --- Subplot 2: text summary box ---
        ax_text.axis("off")
        summary_text = (
            f"Exercise: {self.exercise_name}\n\n"
            f"Total reps: {total_reps}\n"
            f"Good-form reps: {good_reps}\n"
            f"Good-form %: {good_pct:.1f}%\n\n"
            f"Most common issue:\n{most_common_issue}"
        )
        ax_text.text(0.05, 0.95, summary_text, ha="left", va="top", fontsize=12,
                      family="monospace", transform=ax_text.transAxes)

        fig.tight_layout()
        png_path = self._report_png_path()
        fig.savefig(png_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        print("\n=== Session Summary ===")
        print(f"Exercise: {self.exercise_name}")
        print(f"Total reps: {total_reps}")
        print(f"Good-form reps: {good_reps} ({good_pct:.1f}%)")
        print(f"Most common issue: {most_common_issue}")
        print(f"CSV saved to: {csv_path}")
        print(f"Report saved to: {png_path}")

        return csv_path, png_path
