// sla.js
// Computes whether a complaint is "on-time" or "delayed" relative to its
// slaDeadline. The stored `slaStatus` field on the model used to default
// to "on-time" and was never recalculated, so every complaint looked
// on-time forever. This helper makes SLA status live/accurate:
//   - resolved complaints: compare resolvedAt vs slaDeadline (was it fixed in time?)
//   - open complaints: compare now vs slaDeadline (is it overdue right now?)
//   - cancelled complaints: not counted against SLA

export const computeSlaStatus = (complaint) => {
  if (!complaint.slaDeadline) return "on-time";
  const deadline = new Date(complaint.slaDeadline);

  if (complaint.status === "resolved") {
    const resolvedAt = complaint.resolvedAt ? new Date(complaint.resolvedAt) : new Date();
    return resolvedAt <= deadline ? "on-time" : "delayed";
  }

  if (complaint.status === "cancelled") {
    return "on-time";
  }

  // pending / in-progress: is it overdue right now?
  return new Date() <= deadline ? "on-time" : "delayed";
};
