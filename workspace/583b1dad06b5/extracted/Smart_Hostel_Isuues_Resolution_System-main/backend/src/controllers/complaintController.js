import Complaint from "../models/Complaint.js";
import Notification from "../models/Notification.js";
import User from "../models/User.js";
import { classifyAndAssessUrgency } from "../services/aiService.js";
import { computeSlaStatus } from "../utils/sla.js";

// ================= CREATE =================
export const createComplaint = async (req, res) => {
  try {
    const { category, description, priority, duplicateOf } = req.body;

    const user = await User.findById(req.user.id);
    if (!user) {
      return res.status(404).json({ message: "User not found" });
    }

    let slaHours = 72;
    if (category === "Electrical" || category === "Plumbing") {
      slaHours = 48;
    }

    let finalPriority = priority || "medium";
    const aiMeta = { analyzedAt: new Date() };

    // 🤖 FEATURE 3: AI safety/urgency check - runs server-side on every
    // complaint (independent of whatever the student picked) so a
    // genuinely dangerous issue can never slip through as "low priority".
    // If the AI service is unreachable (no API key, network issue, etc.)
    // this fails soft and the complaint is still created normally.
    try {
      const aiResult = await classifyAndAssessUrgency(description);
      if (aiResult) {
        aiMeta.suggestedCategory = aiResult.category;
        aiMeta.suggestedPriority = aiResult.priority;
        aiMeta.isUrgent = aiResult.isUrgent;
        aiMeta.urgencyReason = aiResult.reason;

        if (aiResult.isUrgent) {
          finalPriority = "urgent";
          slaHours = Math.min(slaHours, 6); // escalate SLA deadline for safety-critical issues
        }
      }
    } catch (aiError) {
      console.error("AI urgency check skipped:", aiError.message);
    }

    // Student was shown possible duplicates and chose "Submit anyway"
    if (Array.isArray(duplicateOf) && duplicateOf.length > 0) {
      aiMeta.duplicateOf = duplicateOf;
    }

    const slaDeadline = new Date(Date.now() + slaHours * 60 * 60 * 1000);

    const complaint = await Complaint.create({
      studentId: req.user.id,
      category,
      description,
      priority: finalPriority,
      slaDeadline,
      ai: aiMeta,
    });

    // ✅ Add phone to populated fields
    const populatedComplaint = await Complaint.findById(complaint._id)
      .populate("studentId", "name email roomNumber phone"); // Added phone

    res.status(201).json({
      message: "Complaint created successfully",
      complaint: populatedComplaint,
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "Server error" });
  }
};

// ================= MY COMPLAINTS =================
export const getMyComplaints = async (req, res) => {
  try {
    const complaints = await Complaint.find({
      studentId: req.user.id,
    })
      .populate("studentId", "name email roomNumber phone") // ✅ Added phone
      .sort({ createdAt: -1 });

    // Live SLA status: recompute on every read instead of trusting the
    // stored (and previously never-updated) slaStatus field.
    const withLiveSla = complaints.map((c) => {
      const obj = c.toObject();
      obj.slaStatus = computeSlaStatus(obj);
      return obj;
    });

    res.json(withLiveSla);
  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "Server error" });
  }
};

// ================= ALL COMPLAINTS =================
export const getAllComplaints = async (req, res) => {
  try {
    const complaints = await Complaint.find()
      .populate("studentId", "name email roomNumber phone") // ✅ Added phone
      .sort({ createdAt: -1 });

    const withLiveSla = complaints.map((c) => {
      const obj = c.toObject();
      obj.slaStatus = computeSlaStatus(obj);
      return obj;
    });

    res.json(withLiveSla);
  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "Server error" });
  }
};

// ================= UPDATE STATUS =================
export const updateComplaintStatus = async (req, res) => {
  try {
    const { status } = req.body;

    const complaint = await Complaint.findById(req.params.id);

    if (!complaint) {
      return res.status(404).json({ message: "Not found" });
    }

    complaint.status = status;

    if (status === "resolved") {
      complaint.resolvedAt = new Date();
    }

    // Lock in the final SLA verdict now that the status has changed
    complaint.slaStatus = computeSlaStatus(complaint);

    await complaint.save();

    await Notification.create({
      userId: complaint.studentId,
      message: `Your complaint (${complaint.category}) is now ${status}`,
    });

    res.json({ message: "Updated", complaint });
  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "Server error" });
  }
};

// ================= CANCEL =================
export const cancelComplaint = async (req, res) => {
  try {
    const complaint = await Complaint.findById(req.params.id);

    if (!complaint) {
      return res.status(404).json({ message: "Not found" });
    }

    if (complaint.status === "resolved") {
      return res.status(400).json({ message: "Cannot cancel resolved complaints" });
    }

    complaint.status = "cancelled";
    await complaint.save();

    await Notification.create({
      userId: complaint.studentId,
      message: `Your complaint (${complaint.category}) has been cancelled`,
    });

    res.json({ message: "Cancelled", complaint });
  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "Server error" });
  }
};

// ================= EDIT =================
export const editComplaint = async (req, res) => {
  try {
    const { category, description } = req.body;

    const complaint = await Complaint.findById(req.params.id);

    if (!complaint) {
      return res.status(404).json({ message: "Complaint not found" });
    }

    if (complaint.studentId.toString() !== req.user.id) {
      return res.status(403).json({ message: "Unauthorized" });
    }

    const createdTime = new Date(complaint.createdAt).getTime();
    const currentTime = Date.now();
    const diffMinutes = (currentTime - createdTime) / (1000 * 60);

    if (diffMinutes > 15) {
      return res.status(400).json({
        message: "Edit time expired (only within 15 minutes)",
      });
    }

    complaint.category = category || complaint.category;
    complaint.description = description || complaint.description;

    await complaint.save();

    // ✅ Add phone to populated fields
    const populatedComplaint = await Complaint.findById(complaint._id)
      .populate("studentId", "name email roomNumber phone"); // Added phone

    res.json({
      message: "Complaint updated successfully",
      complaint: populatedComplaint,
    });
  } catch (error) {
    console.error(error);
    res.status(500).json({ message: "Server error" });
  }
};