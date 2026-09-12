import mongoose from "mongoose";

const complaintSchema = new mongoose.Schema(
  {
    studentId: {
      type: mongoose.Schema.Types.ObjectId,
      ref: "User",
      required: true,
    },
    // ❌ REMOVE roomNumber from here - will get from user
    category: {
      type: String,
      enum: [
        "Electrical",
        "Plumbing",
        "Furniture",
        "Washroom",
        "WiFi",
        "Cleaning",
        "Security",
        "Other",
      ],
      required: true,
    },
    description: {
      type: String,
      required: true,
    },
    imageUrl: {
      type: String,
    },
    priority: {
      type: String,
      // "urgent" added because the Create Complaint form offers it and the
      // AI urgency-escalation feature also assigns it - it was previously
      // missing here, which would have thrown a validation error.
      enum: ["low", "medium", "high", "urgent"],
      default: "medium",
    },
    status: {
      type: String,
      enum: ["pending", "in-progress", "resolved", "cancelled"],
      default: "pending",
    },
    resolutionNote: {
      type: String,
    },
    resolvedAt: {
      type: Date,
    },
    slaDeadline: {
      type: Date,
    },
    slaStatus: {
      type: String,
      enum: ["on-time", "delayed"],
      default: "on-time",
    },
    // ✨ AI metadata - populated automatically when a complaint is created
    ai: {
      suggestedCategory: { type: String }, // what the AI thought the category should be
      suggestedPriority: { type: String }, // what the AI thought the priority should be
      isUrgent: { type: Boolean, default: false }, // safety-critical flag
      urgencyReason: { type: String },
      duplicateOf: [{ type: mongoose.Schema.Types.ObjectId, ref: "Complaint" }], // complaints the student was warned looked similar and chose to submit anyway
      analyzedAt: { type: Date },
    },
  },
  { timestamps: true }
);

// ✅ Virtual field to get room number from user
complaintSchema.virtual('roomNumber').get(function() {
  return this.studentId?.roomNumber || 'Not Assigned';
});

complaintSchema.set('toJSON', { virtuals: true });
complaintSchema.set('toObject', { virtuals: true });

const Complaint = mongoose.model("Complaint", complaintSchema);

export default Complaint;