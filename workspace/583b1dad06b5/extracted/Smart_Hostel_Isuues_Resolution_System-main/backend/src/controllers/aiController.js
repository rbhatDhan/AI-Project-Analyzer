import Complaint from "../models/Complaint.js";
import {
  classifyAndAssessUrgency,
  findDuplicateComplaints,
  generateInsightsSummary,
} from "../services/aiService.js";

// ================= FEATURE 1: AUTO-CLASSIFY (+ urgency preview) =================
// POST /api/ai/analyze-complaint  (any logged-in user)
// Called from the "Create Complaint" form before submit, to auto-fill
// category + priority from the free-text description.
export const analyzeComplaint = async (req, res) => {
  try {
    const { description } = req.body;

    if (!description || description.trim().length < 5) {
      return res.status(400).json({ message: "Description is too short to analyze" });
    }

    const result = await classifyAndAssessUrgency(description);

    if (!result) {
      return res.status(502).json({ message: "AI analysis unavailable, please fill in manually" });
    }

    res.json(result);
  } catch (error) {
    console.error("AI analyze error:", error.message);
    res.status(500).json({ message: "AI analysis failed, please fill in manually" });
  }
};

// ================= FEATURE 2: DUPLICATE DETECTION =================
// POST /api/ai/check-duplicates  (any logged-in user)
// Checks the new complaint's description against recent open complaints
// in the same category before letting the student submit.
export const checkDuplicates = async (req, res) => {
  try {
    const { description, category } = req.body;

    if (!description || description.trim().length < 5) {
      return res.json({ duplicates: [] });
    }

    const since = new Date(Date.now() - 14 * 24 * 60 * 60 * 1000); // last 14 days
    const query = {
      status: { $in: ["pending", "in-progress"] },
      createdAt: { $gte: since },
    };
    if (category) query.category = category;

    const candidates = await Complaint.find(query)
      .populate("studentId", "roomNumber")
      .sort({ createdAt: -1 })
      .limit(15);

    const candidateData = candidates.map((c) => ({
      id: c._id.toString(),
      description: c.description,
      roomNumber: c.studentId?.roomNumber || "Unknown",
      status: c.status,
      createdAt: c.createdAt,
    }));

    const matches = await findDuplicateComplaints(description, candidateData);

    const enriched = matches
      .map((m) => {
        const c = candidateData.find((cd) => cd.id === m.id);
        return c ? { ...c, confidence: m.confidence, reason: m.reason } : null;
      })
      .filter(Boolean);

    res.json({ duplicates: enriched });
  } catch (error) {
    console.error("Duplicate check error:", error.message);
    // Fail soft: never block complaint submission because AI is down
    res.json({ duplicates: [] });
  }
};

// ================= FEATURE 4: AI ANALYTICS SUMMARY =================
// GET /api/ai/summary?days=30  (warden/admin only)
// Aggregates complaint stats server-side (no raw personal data sent to the
// model) and asks Claude to write a short narrative summary for the
// Analytics dashboard.
export const getAiSummary = async (req, res) => {
  try {
    const days = parseInt(req.query.days, 10) || 30;
    const since = new Date(Date.now() - days * 24 * 60 * 60 * 1000);

    const complaints = await Complaint.find({ createdAt: { $gte: since } });

    const total = complaints.length;
    const resolved = complaints.filter((c) => c.status === "resolved").length;
    const pending = complaints.filter((c) => c.status === "pending").length;
    const inProgress = complaints.filter((c) => c.status === "in-progress").length;
    const cancelled = complaints.filter((c) => c.status === "cancelled").length;

    const byCategory = {};
    complaints.forEach((c) => {
      byCategory[c.category] = (byCategory[c.category] || 0) + 1;
    });

    const resolvedWithTime = complaints.filter((c) => c.status === "resolved" && c.resolvedAt);
    const avgResolutionHours = resolvedWithTime.length
      ? (
          resolvedWithTime.reduce(
            (sum, c) => sum + (new Date(c.resolvedAt) - new Date(c.createdAt)),
            0
          ) /
          resolvedWithTime.length /
          (1000 * 60 * 60)
        ).toFixed(1)
      : null;

    const slaBreaches = complaints.filter((c) => {
      if (!c.slaDeadline) return false;
      const compareDate = c.status === "resolved" ? c.resolvedAt : new Date();
      return compareDate && new Date(compareDate) > new Date(c.slaDeadline);
    }).length;

    const urgentCount = complaints.filter((c) => c.ai?.isUrgent).length;

    const stats = {
      periodDays: days,
      total,
      resolved,
      pending,
      inProgress,
      cancelled,
      byCategory,
      avgResolutionHours,
      slaBreaches,
      urgentCount,
    };

    let summary = null;
    try {
      if (total > 0) {
        summary = await generateInsightsSummary(stats);
      }
    } catch (aiErr) {
      console.error("AI summary generation failed:", aiErr.message);
    }

    res.json({ stats, summary });
  } catch (error) {
    console.error("AI summary error:", error.message);
    res.status(500).json({ message: "Failed to generate summary" });
  }
};
