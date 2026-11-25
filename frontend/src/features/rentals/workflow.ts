import type { Stage } from "./api";
import type { ContactRequest } from "../../api";

export const enquiryStatusLabels: Record<ContactRequest["status"], string> = {
  pending: "Awaiting response",
  approved: "Accepted",
  rejected: "Declined",
  cancelled: "Cancelled",
};

export const stageLabels: Record<Stage | "DISPUTED", string> = {
  NEW: "New enquiry",
  CONTACTED: "Contacted",
  VIEWING_SCHEDULED: "Viewing scheduled",
  VIEWING_COMPLETED: "Viewing completed",
  INTERESTED: "Interested",
  RENTED: "Rented",
  UNSUCCESSFUL: "Unsuccessful",
  DISPUTED: "Disputed (historical)",
};
export const landlordTransitions: Partial<Record<Stage, Stage[]>> = {
  NEW: ["CONTACTED", "UNSUCCESSFUL"],
  CONTACTED: ["VIEWING_SCHEDULED", "INTERESTED", "UNSUCCESSFUL"],
  VIEWING_SCHEDULED: ["VIEWING_COMPLETED", "UNSUCCESSFUL"],
  VIEWING_COMPLETED: ["INTERESTED", "UNSUCCESSFUL"],
  INTERESTED: ["RENTED", "UNSUCCESSFUL"],
};
export const verificationLabels = {
  pending: "Awaiting review",
  needs_information: "More information needed",
  approved: "Approved",
  rejected: "Rejected",
};
export function dateLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime())
    ? "Date unavailable"
    : new Intl.DateTimeFormat("en-ZA", {
        dateStyle: "medium",
        timeStyle: "short",
      }).format(date);
}
