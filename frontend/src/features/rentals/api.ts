import { requestJson, type ReportHistoryRecord } from "../../api";

export type Stage =
  | "NEW"
  | "CONTACTED"
  | "VIEWING_SCHEDULED"
  | "VIEWING_COMPLETED"
  | "INTERESTED"
  | "RENTED"
  | "UNSUCCESSFUL";
export type DisputeStatus = "none" | "open" | "resolved" | "dismissed";
export interface LeadHistory {
  history_id: number;
  from_stage: Stage | "DISPUTED" | null;
  to_stage: Stage | "DISPUTED";
  changed_at: string;
  actor_user_id?: number;
  note?: string | null;
}
export interface Lead {
  lead_id: number;
  contact_request_id: number;
  listing_id: number;
  tenant_id?: number;
  landlord_id?: number;
  listing_title?: string;
  listing_address?: string;
  tenant_name?: string;
  landlord_name?: string;
  stage: Stage;
  dispute_status: DisputeStatus;
  rented_at: string | null;
  unsuccessful_reason?: string | null;
  created_at: string;
  updated_at: string;
  history?: LeadHistory[];
}
export interface LeadDispute extends Lead {
  report_id: number;
  report_status: string;
  report_reason: string;
  report_details: string | null;
  report_created_at: string;
  report_history: ReportHistoryRecord[];
}
export interface ConversionSummary {
  total_leads: number;
  closed_leads: number;
  conversion_rate: number;
  stages: Record<Lowercase<Stage> | "disputed", number>;
}
export interface BusinessSummary {
  total_listings: number;
  available_rooms: number;
  occupied_rooms: number;
  reserved_rooms: number;
  total_enquiries: number;
  new_enquiries: number;
  active_conversations: number;
  listing_performance: { listing_id: number; enquiry_count: number }[];
  monthly_enquiries: { month: string; enquiry_count: number }[];
}
export type VerificationType = "identity" | "property_authorization";
export type VerificationStatus =
  "pending" | "needs_information" | "approved" | "rejected";
export interface Verification {
  request_id: number;
  verification_type: VerificationType;
  listing_id: number | null;
  user_id?: number;
  evidence_statement?: string;
  status: VerificationStatus;
  decision_reason: string | null;
  expires_at: string | null;
  submitted_at: string;
  updated_at: string;
}
export interface VerificationHistory {
  history_id: number;
  actor_user_id: number;
  action: string;
  note: string | null;
  created_at: string;
}
export type TrustStatus = "verified" | "under_review" | "unverified";
export interface PublicTrust {
  phone_verified: boolean;
  identity_status: TrustStatus;
  property_authorization_status: TrustStatus;
  listing_verification_status: TrustStatus;
  active_listing_count: number;
  account_created_at: string;
}

export function rentalRequest<T>(
  path: string,
  token: string | null,
  method = "GET",
  body?: unknown,
  signal?: AbortSignal,
): Promise<T> {
  return requestJson<T>(`/api/v1${path}`, {
    method,
    signal,
    headers: token === null ? undefined : { Authorization: `Bearer ${token}` },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
