import { useState } from "react";
import AppLink from "../../components/AppLink";
import { rentalRequest, type Lead, type LeadDispute, type Stage } from "./api";
import {
  ActionMessages,
  DataPanel,
  useRentalAction,
  useRentalData,
} from "./shared";
import { dateLabel, landlordTransitions, stageLabels } from "./workflow";

type Role = "landlord" | "tenant" | "admin";
type Navigate = (path: string) => void;

export function LeadPanel({
  token,
  role,
  onNavigate,
}: {
  token: string;
  role: Role;
  onNavigate: Navigate;
}) {
  const path =
    role === "admin"
      ? "/admin/leads"
      : role === "tenant"
        ? "/users/me/lead-enquiries"
        : "/users/me/leads";
  const resource = useRentalData<Lead[]>(path, token);
  const [stage, setStage] = useState("all");
  return (
    <DataPanel
      title={role === "tenant" ? "Your enquiry progress" : "Lead management"}
      resource={resource}
    >
      <p>
        {role === "tenant"
          ? "Follow your room enquiries and report inaccurate progress. An enquiry does not reserve a room."
          : role === "admin"
            ? "Inspect enquiry progress and history. Use Lead disputes to review challenged records."
            : "Track enquiries from first contact through viewings and rental outcomes."}
      </p>
      <label>
        Filter by stage{" "}
        <select
          value={stage}
          onChange={(event) => setStage(event.target.value)}
        >
          <option value="all">All stages</option>
          {Object.entries(stageLabels)
            .filter(([value]) => value !== "DISPUTED")
            .map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
        </select>
      </label>
      {resource.data?.length === 0 && <p>No enquiries yet.</p>}
      {resource.data &&
        resource.data.length > 0 &&
        resource.data.filter((lead) => stage === "all" || lead.stage === stage)
          .length === 0 && <p>No enquiries match this stage.</p>}
      <ul className="rental-records">
        {resource.data
          ?.filter((lead) => stage === "all" || lead.stage === stage)
          .map((lead) => (
            <LeadRecord
              key={`${lead.lead_id}-${lead.updated_at}`}
              lead={lead}
              token={token}
              role={role}
              onNavigate={onNavigate}
              reload={resource.reload}
            />
          ))}
      </ul>
    </DataPanel>
  );
}

function LeadRecord({
  lead,
  token,
  role,
  onNavigate,
  reload,
}: {
  lead: Lead;
  token: string;
  role: Role;
  onNavigate: Navigate;
  reload: () => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showDispute, setShowDispute] = useState(false);
  const [details, setDetails] = useState("");
  const action = useRentalAction();
  const title = lead.listing_title ?? `Listing #${lead.listing_id}`;
  return (
    <li className="rental-record" data-lead-id={lead.lead_id}>
      <header className="rental-section-heading">
        <div>
          <h3>{title}</h3>
          <span className="rental-status">{stageLabels[lead.stage]}</span>
          {lead.dispute_status !== "none" && (
            <p>Dispute: {lead.dispute_status}</p>
          )}
        </div>
        <small>Enquiry #{lead.lead_id}</small>
      </header>
      {lead.tenant_id && (
        <p>
          {lead.tenant_name ?? `Tenant #${lead.tenant_id}`} · Enquiry request #
          {lead.contact_request_id}
        </p>
      )}
      <p>Updated {dateLabel(lead.updated_at)}</p>
      {lead.rented_at && <p>Rental recorded {dateLabel(lead.rented_at)}</p>}
      {role !== "tenant" && lead.unsuccessful_reason && (
        <p>Outcome reason: {lead.unsuccessful_reason}</p>
      )}
      <div className="rental-actions">
        <AppLink variant="action" href={`/listings/${lead.listing_id}`} onNavigate={onNavigate}>
          View room
        </AppLink>
        {role !== "admin" && (
          <AppLink
            variant="action"
            href={`/conversations?request=${lead.contact_request_id}`}
            onNavigate={onNavigate}
          >
            Open messages
          </AppLink>
        )}
        <button
          className="secondary-button"
          type="button"
          aria-expanded={expanded}
          onClick={() => setExpanded(!expanded)}
        >
          {expanded ? "Hide history" : "View progress history"}
        </button>
        {role === "tenant" && lead.dispute_status !== "open" && (
          <button
            className="secondary-button"
            type="button"
            onClick={() => setShowDispute(!showDispute)}
            aria-expanded={showDispute}
          >
            Report inaccurate progress
          </button>
        )}
      </div>
      <ActionMessages {...action} />
      {showDispute && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void action.run(
              () =>
                rentalRequest("/reports", token, "POST", {
                  target: "lead",
                  lead_id: lead.lead_id,
                  reason: "inaccurate_info",
                  details: details.trim(),
                }),
              "Your dispute was submitted for review.",
              reload,
            );
          }}
        >
          <label>
            Explain what is inaccurate
            <textarea
              required
              minLength={10}
              maxLength={2000}
              value={details}
              onChange={(event) => setDetails(event.target.value)}
            />
          </label>
          <button
            className="primary-button"
            disabled={action.busy || details.trim().length < 10}
            type="submit"
          >
            {action.busy ? "Submitting…" : "Submit dispute"}
          </button>
        </form>
      )}
      {role === "landlord" && (
        <LandlordLeadAction lead={lead} token={token} reload={reload} />
      )}
      {expanded && (
        <LeadHistoryPanel token={token} role={role} id={lead.lead_id} />
      )}
    </li>
  );
}

function LandlordLeadAction({
  lead,
  token,
  reload,
}: {
  lead: Lead;
  token: string;
  reload: () => void;
}) {
  const options = landlordTransitions[lead.stage] ?? [];
  const [stage, setStage] = useState<Stage>(options[0] ?? lead.stage);
  const [note, setNote] = useState("");
  const [editing, setEditing] = useState(false);
  const action = useRentalAction();
  if (lead.dispute_status === "open")
    return (
      <p>
        This enquiry is under dispute review. Progress updates are paused until
        an admin decides the dispute.
      </p>
    );
  if (options.length === 0) return <p>This enquiry has a recorded outcome.</p>;
  return (
    <>
      <button
        className="secondary-button"
        type="button"
        aria-expanded={editing}
        onClick={() => setEditing(!editing)}
      >
        {editing ? "Cancel progress update" : "Edit progress"}
      </button>
      {editing && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const base = `/users/me/leads/${lead.lead_id}`;
            const path =
              stage === "RENTED"
                ? `${base}/rental`
                : stage === "UNSUCCESSFUL"
                  ? `${base}/unsuccessful`
                  : `${base}/stage`;
            const body =
              stage === "UNSUCCESSFUL"
                ? { reason: note.trim() }
                : {
                    ...(stage === "RENTED" ? {} : { stage }),
                    ...(note.trim() ? { note: note.trim() } : {}),
                  };
            void action.run(
              () =>
                rentalRequest(
                  path,
                  token,
                  stage === "RENTED" || stage === "UNSUCCESSFUL"
                    ? "POST"
                    : "PATCH",
                  body,
                ),
              "Enquiry progress updated.",
              reload,
            );
          }}
        >
          <label>
            Next stage
            <select
              value={stage}
              onChange={(event) => setStage(event.target.value as Stage)}
              disabled={action.busy}
            >
              {options.map((value) => (
                <option key={value} value={value}>
                  {stageLabels[value]}
                </option>
              ))}
            </select>
          </label>
          <label>
            {stage === "UNSUCCESSFUL"
              ? "Reason (required)"
              : "Internal note (optional)"}
            <textarea
              required={stage === "UNSUCCESSFUL"}
              maxLength={2000}
              value={note}
              onChange={(event) => setNote(event.target.value)}
            />
          </label>
          <p>
            Recording a rental outcome does not update room availability. Update
            the room separately in Listings.
          </p>
          <ActionMessages {...action} />
          <button
            className="primary-button"
            type="submit"
            disabled={action.busy || (stage === "UNSUCCESSFUL" && !note.trim())}
          >
            {action.busy
              ? "Saving…"
              : stage === "RENTED"
                ? "Record rental"
                : stage === "UNSUCCESSFUL"
                  ? "Record unsuccessful outcome"
                  : "Update progress"}
          </button>
        </form>
      )}
    </>
  );
}

function LeadHistoryPanel({
  token,
  role,
  id,
}: {
  token: string;
  role: Role;
  id: number;
}) {
  const base =
    role === "admin"
      ? "/admin/leads"
      : role === "tenant"
        ? "/users/me/lead-enquiries"
        : "/users/me/leads";
  const resource = useRentalData<Lead>(`${base}/${id}`, token);
  return (
    <DataPanel title="Progress history" resource={resource}>
      {resource.data?.history?.length === 0 && <p>No history available.</p>}
      <ol className="rental-history">
        {resource.data?.history?.map((item) => (
          <li key={item.history_id}>
            <strong>{stageLabels[item.to_stage]}</strong>
            <time dateTime={item.changed_at}>{dateLabel(item.changed_at)}</time>
            {role !== "tenant" && item.note && <p>{item.note}</p>}
          </li>
        ))}
      </ol>
    </DataPanel>
  );
}

export function AdminDisputesPanel({
  token,
  onNavigate,
}: {
  token: string;
  onNavigate: Navigate;
}) {
  const resource = useRentalData<LeadDispute[]>("/admin/lead-disputes", token);
  return (
    <DataPanel title="Open lead disputes" resource={resource}>
      {resource.data?.length === 0 && <p>No open lead disputes.</p>}
      <ul className="rental-records">
        {resource.data?.map((dispute) => (
          <DisputeRecord
            key={dispute.lead_id}
            token={token}
            dispute={dispute}
            reload={resource.reload}
            onNavigate={onNavigate}
          />
        ))}
      </ul>
    </DataPanel>
  );
}
function DisputeRecord({
  token,
  dispute,
  reload,
  onNavigate,
}: {
  token: string;
  dispute: LeadDispute;
  reload: () => void;
  onNavigate: Navigate;
}) {
  const [stage, setStage] = useState<Stage>(dispute.stage);
  const [note, setNote] = useState("");
  const [decision, setDecision] = useState("resolve");
  const action = useRentalAction();
  return (
    <li className="rental-record">
      <h3>
        {dispute.listing_title} · Enquiry #{dispute.lead_id}
      </h3>
      <p>
        {dispute.tenant_name} / {dispute.landlord_name}
      </p>
      <p>Current stage: {stageLabels[dispute.stage]}</p>
      <p>{dispute.report_details}</p>
      <p>
        Report #{dispute.report_id} · {dateLabel(dispute.report_created_at)}
      </p>
      <AppLink href={`/listings/${dispute.listing_id}`} onNavigate={onNavigate}>
        View room
      </AppLink>
      <details>
        <summary>Enquiry and report history</summary>
        <ol className="rental-history">
          {dispute.history?.map((item) => (
            <li key={item.history_id}>
              {stageLabels[item.to_stage]} · {dateLabel(item.changed_at)}
              {item.note && <p>{item.note}</p>}
            </li>
          ))}
        </ol>
        <ol className="rental-history">
          {dispute.report_history.map((item) => (
            <li key={item.history_id}>
              {item.action.replaceAll("_", " ")} · {dateLabel(item.created_at)}
              {item.note && <p>{item.note}</p>}
            </li>
          ))}
        </ol>
      </details>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(
            () =>
              rentalRequest(
                `/admin/leads/${dispute.lead_id}${decision === "dismiss" ? "/dismiss-dispute" : "/stage"}`,
                token,
                decision === "dismiss" ? "POST" : "PATCH",
                decision === "dismiss"
                  ? { reason: note.trim() }
                  : { stage, note: note.trim() },
              ),
            "Dispute decision saved.",
            reload,
          );
        }}
      >
        <label>
          Decision
          <select
            value={decision}
            onChange={(event) => setDecision(event.target.value)}
          >
            <option value="resolve">Resolve and confirm progress</option>
            <option value="dismiss">
              Dismiss dispute and keep current progress
            </option>
          </select>
        </label>
        {decision === "resolve" && (
          <label>
            Confirmed stage
            <select
              value={stage}
              onChange={(event) => setStage(event.target.value as Stage)}
            >
              {Object.entries(stageLabels)
                .filter(([value]) => value !== "DISPUTED")
                .map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
            </select>
          </label>
        )}
        <label>
          Decision reason
          <textarea
            required
            maxLength={2000}
            value={note}
            onChange={(event) => setNote(event.target.value)}
          />
        </label>
        <ActionMessages {...action} />
        <button
          className="primary-button"
          type="submit"
          disabled={action.busy || !note.trim()}
        >
          {action.busy ? "Saving…" : "Save dispute decision"}
        </button>
      </form>
    </li>
  );
}
