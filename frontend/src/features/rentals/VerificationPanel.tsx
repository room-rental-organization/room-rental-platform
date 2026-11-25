import { useState } from "react";
import type { Listing } from "../../types/listing";
import {
  rentalRequest,
  type PublicTrust,
  type Verification,
  type VerificationHistory,
  type VerificationStatus,
  type VerificationType,
} from "./api";
import {
  ActionMessages,
  DataPanel,
  useRentalAction,
  useRentalData,
} from "./shared";
import { dateLabel, verificationLabels } from "./workflow";

export function LandlordVerificationPanel({ token }: { token: string }) {
  const requests = useRentalData<Verification[]>(
    "/users/me/trust-verifications",
    token,
  );
  const listings = useRentalData<Listing[]>("/users/me/listings", token);
  const [type, setType] = useState<VerificationType>("identity");
  const [listingId, setListingId] = useState("");
  const [evidence, setEvidence] = useState("");
  const [trustListingId, setTrustListingId] = useState("");
  const trustListing =
    listings.data?.find(
      (listing) => String(listing.listing_id) === trustListingId,
    ) ?? listings.data?.[0];
  const action = useRentalAction();
  const blocked = requests.data?.some(
    (request) =>
      request.verification_type === type &&
      request.listing_id === (type === "identity" ? null : Number(listingId)) &&
      (request.status === "pending" || request.status === "needs_information"),
  );
  const eligible =
    listings.data?.filter(
      (listing) => !["removed", "closed"].includes(listing.status),
    ) ?? [];
  return (
    <DataPanel title="Trust and verification" resource={requests}>
      <p>
        Request an identity or property authorization review. Your supporting
        statement is private to platform administrators.
      </p>
      <form
        className="rental-feature-form"
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(
            () =>
              rentalRequest("/users/me/trust-verifications", token, "POST", {
                verification_type: type,
                ...(type === "property_authorization"
                  ? { listing_id: Number(listingId) }
                  : {}),
                evidence_statement: evidence.trim(),
              }),
            "Verification submitted for review.",
            () => {
              setEvidence("");
              requests.reload();
            },
          );
        }}
      >
        <label>
          Verification type
          <select
            value={type}
            onChange={(event) =>
              setType(event.target.value as VerificationType)
            }
          >
            <option value="identity">Landlord identity</option>
            <option value="property_authorization">
              Property authorization
            </option>
          </select>
        </label>
        {type === "property_authorization" && (
          <>
            {listings.loading && <p role="status">Loading your listings…</p>}
            <ActionMessages error={listings.error} />
            {listings.error && (
              <button
                className="secondary-button"
                type="button"
                onClick={listings.reload}
              >
                Retry listings
              </button>
            )}
            <label>
              Room
              <select
                required
                value={listingId}
                onChange={(event) => setListingId(event.target.value)}
              >
                <option value="">Select a room</option>
                {eligible.map((listing) => (
                  <option value={listing.listing_id} key={listing.listing_id}>
                    {listing.title}
                  </option>
                ))}
              </select>
            </label>
            {!listings.loading && !listings.error && eligible.length === 0 && (
              <p>
                Create an eligible listing before requesting property
                authorization.
              </p>
            )}
          </>
        )}
        <label>
          Supporting statement
          <textarea
            required
            minLength={10}
            maxLength={1000}
            value={evidence}
            onChange={(event) => setEvidence(event.target.value)}
            placeholder="Explain how an administrator can verify your identity or authorization to rent this property."
          />
        </label>
        {blocked && (
          <p>
            A request for this subject is already awaiting action. Review its
            status below.
          </p>
        )}
        <ActionMessages {...action} />
        <button
          className="primary-button"
          type="submit"
          disabled={
            action.busy ||
            requests.loading ||
            requests.error !== null ||
            blocked ||
            evidence.trim().length < 10 ||
            (type === "property_authorization" &&
              !eligible.some(
                (listing) => listing.listing_id === Number(listingId),
              ))
          }
        >
          {action.busy ? "Submitting…" : "Request verification"}
        </button>
      </form>
      <h3>Your requests</h3>
      {requests.data?.length === 0 && (
        <p>You have not submitted any verification requests.</p>
      )}
      <ul className="rental-records">
        {requests.data?.map((request) => (
          <VerificationRecord
            key={`${request.request_id}-${request.updated_at}`}
            request={request}
            token={token}
            admin={false}
            reload={requests.reload}
          />
        ))}
      </ul>
      <h3>Your property trust status</h3>
      {listings.loading && <p role="status">Loading your properties…</p>}
      <ActionMessages error={listings.error} />
      {listings.error && (
        <button className="secondary-button" type="button" onClick={listings.reload}>
          Retry your properties
        </button>
      )}
      {listings.data?.length === 0 && (
        <p>Create a listing to view its trust status here.</p>
      )}
      {trustListing && (
        <>
          <label>
            Property trust summary
            <select
              value={String(trustListing.listing_id)}
              onChange={(event) => setTrustListingId(event.target.value)}
            >
              {listings.data?.map((listing) => (
                <option value={listing.listing_id} key={listing.listing_id}>
                  {listing.title}
                </option>
              ))}
            </select>
          </label>
          <LandlordTrustPanel
            token={token}
            listingId={trustListing.listing_id}
            key={trustListing.listing_id}
          />
        </>
      )}
    </DataPanel>
  );
}

export function AdminVerificationPanel({ token }: { token: string }) {
  const [filter, setFilter] = useState<VerificationStatus | "all">("pending");
  const requests = useRentalData<Verification[]>(
    `/admin/trust-verifications${filter === "all" ? "" : `?status=${filter}`}`,
    token,
  );
  return (
    <DataPanel title="Verification review" resource={requests}>
      <label>
        Request status{" "}
        <select
          value={filter}
          onChange={(event) => setFilter(event.target.value as typeof filter)}
        >
          <option value="all">All statuses</option>
          {Object.entries(verificationLabels).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
      {requests.data?.length === 0 && <p>No requests match this status.</p>}
      <ul className="rental-records">
        {requests.data?.map((request) => (
          <VerificationRecord
            key={`${request.request_id}-${request.updated_at}`}
            request={request}
            token={token}
            admin
            reload={requests.reload}
          />
        ))}
      </ul>
    </DataPanel>
  );
}

function VerificationRecord({
  request,
  token,
  admin,
  reload,
}: {
  request: Verification;
  token: string;
  admin: boolean;
  reload: () => void;
}) {
  const [evidence, setEvidence] = useState("");
  const [decision, setDecision] = useState("approve");
  const [reason, setReason] = useState("");
  const [history, setHistory] = useState(false);
  const action = useRentalAction();
  return (
    <li className="rental-record">
      <h3>
        {request.verification_type === "identity"
          ? "Landlord identity"
          : `Property authorization · Listing #${request.listing_id}`}
      </h3>
      <p>
        Request #{request.request_id}
        {admin ? ` · Account #${request.user_id}` : ""}
      </p>
      <span className="rental-status">
        {verificationLabels[request.status]}
      </span>
      <p>Submitted {dateLabel(request.submitted_at)}</p>
      {request.expires_at && <p>Expires {dateLabel(request.expires_at)}</p>}
      {admin && (
        <p>
          <strong>Supporting statement:</strong> {request.evidence_statement}
        </p>
      )}
      {request.decision_reason && (
        <p>
          <strong>Administrator note:</strong> {request.decision_reason}
        </p>
      )}
      {admin && request.status === "pending" && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void action.run(
              () =>
                rentalRequest(
                  `/admin/trust-verifications/${request.request_id}/decision`,
                  token,
                  "POST",
                  { action: decision, reason: reason.trim() },
                ),
              "Verification decision saved.",
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
              <option value="approve">Approve</option>
              <option value="reject">Reject</option>
              <option value="request_information">
                Request more information
              </option>
            </select>
          </label>
          <label>
            Decision reason
            <textarea
              required
              maxLength={1000}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            />
          </label>
          <button
            className="primary-button"
            type="submit"
            disabled={action.busy || !reason.trim()}
          >
            {action.busy ? "Saving…" : "Save verification decision"}
          </button>
        </form>
      )}
      {!admin && ["rejected", "needs_information"].includes(request.status) && (
        <form
          onSubmit={(event) => {
            event.preventDefault();
            void action.run(
              () =>
                rentalRequest(
                  `/users/me/trust-verifications/${request.request_id}/resubmit`,
                  token,
                  "POST",
                  { evidence_statement: evidence.trim() },
                ),
              "Updated statement submitted for review.",
              reload,
            );
          }}
        >
          <label>
            Updated supporting statement
            <textarea
              required
              minLength={10}
              maxLength={1000}
              value={evidence}
              onChange={(event) => setEvidence(event.target.value)}
            />
          </label>
          <button
            className="primary-button"
            disabled={action.busy || evidence.trim().length < 10}
            type="submit"
          >
            {action.busy ? "Submitting…" : "Resubmit for review"}
          </button>
        </form>
      )}
      <ActionMessages {...action} />
      {admin && (
        <button
          className="secondary-button"
          type="button"
          aria-expanded={history}
          onClick={() => setHistory(!history)}
        >
          {history ? "Hide audit history" : "View audit history"}
        </button>
      )}
      {history && admin && (
        <VerificationAudit token={token} id={request.request_id} />
      )}
    </li>
  );
}

function VerificationAudit({ token, id }: { token: string; id: number }) {
  const history = useRentalData<VerificationHistory[]>(
    `/admin/trust-verifications/${id}/history`,
    token,
  );
  return (
    <DataPanel title="Verification audit history" resource={history}>
      <ol className="rental-history">
        {history.data?.map((item) => (
          <li key={item.history_id}>
            {item.action.replaceAll("_", " ")} · Account #{item.actor_user_id}
            <time dateTime={item.created_at}>{dateLabel(item.created_at)}</time>
            {item.note && <p>{item.note}</p>}
          </li>
        ))}
      </ol>
      {history.data?.length === 0 && <p>No audit history recorded.</p>}
    </DataPanel>
  );
}

function LandlordTrustPanel({
  listingId,
  token,
}: {
  listingId: number;
  token: string;
}) {
  const resource = useRentalData<PublicTrust>(
    `/listings/${listingId}/trust`,
    token,
  );
  const status = {
    verified: "Verified",
    under_review: "Under review",
    unverified: "Unverified",
  };
  return (
    <DataPanel title="Landlord and property trust" resource={resource}>
      {resource.data && (
        <>
          <dl className="profile-list">
            <div>
              <dt>Account phone</dt>
              <dd>
                {resource.data.phone_verified ? "Verified" : "Unverified"}
              </dd>
            </div>
            <div>
              <dt>Landlord identity</dt>
              <dd>{status[resource.data.identity_status]}</dd>
            </div>
            <div>
              <dt>Property authorization</dt>
              <dd>{status[resource.data.property_authorization_status]}</dd>
            </div>
            <div>
              <dt>Listing verification</dt>
              <dd>{status[resource.data.listing_verification_status]}</dd>
            </div>
            <div>
              <dt>Active listings</dt>
              <dd>{resource.data.active_listing_count}</dd>
            </div>
            <div>
              <dt>Account created</dt>
              <dd>{dateLabel(resource.data.account_created_at)}</dd>
            </div>
          </dl>
          <p>
            This summary is private to your landlord account and applies to the selected property.
          </p>
        </>
      )}
    </DataPanel>
  );
}
