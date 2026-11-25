import { useState } from "react";
import type { Listing } from "../../types/listing";
import {
  rentalRequest,
  type BusinessSummary,
  type ConversionSummary,
} from "./api";
import {
  ActionMessages,
  DataPanel,
  useRentalAction,
  useRentalData,
} from "./shared";

export function BusinessPanel({
  token,
  listings,
}: {
  token: string;
  listings: Listing[];
}) {
  const summary = useRentalData<BusinessSummary>(
    "/users/me/business-dashboard",
    token,
  );
  const conversion = useRentalData<ConversionSummary>(
    "/users/me/leads/summary",
    token,
  );
  const data = summary.data;
  const titles = new Map(
    listings.map((listing) => [listing.listing_id, listing.title]),
  );
  return (
    <DataPanel title="Rental performance" resource={summary}>
      {data && (
        <>
          <dl className="rental-stats">
            {[
              ["Available rooms", data.available_rooms],
              ["Reserved rooms", data.reserved_rooms],
              ["Occupied rooms", data.occupied_rooms],
              ["Total enquiries", data.total_enquiries],
              ["New enquiries", data.new_enquiries],
              ["Active conversations", data.active_conversations],
            ].map(([label, value]) => (
              <div className="rental-stat" key={label}>
                <dt>{label}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <h3>Enquiries over the last six months</h3>
          <ul className="rental-months">
            {data.monthly_enquiries.map((month) => (
              <li key={month.month}>
                <span>{month.month}</span>
                <meter
                  aria-label={`${month.month} enquiries`}
                  min={0}
                  max={Math.max(
                    1,
                    ...data.monthly_enquiries.map((item) => item.enquiry_count),
                  )}
                  value={month.enquiry_count}
                />
                <strong>{month.enquiry_count}</strong>
              </li>
            ))}
          </ul>
          <h3>Enquiries by listing</h3>
          {data.listing_performance.length === 0 ? (
            <p>Create a listing to start tracking enquiries.</p>
          ) : (
            <div className="rental-table-wrap">
              <table>
                <thead>
                  <tr>
                    <th scope="col">Room</th>
                    <th scope="col">Enquiries</th>
                  </tr>
                </thead>
                <tbody>
                  {data.listing_performance.map((item) => (
                    <tr key={item.listing_id}>
                      <td>
                        {titles.get(item.listing_id) ??
                          `Listing #${item.listing_id}`}
                      </td>
                      <td>{item.enquiry_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      <DataPanel title="Rental conversions" resource={conversion}>
        {conversion.data && (
          <>
            <p>
              <strong>{conversion.data.conversion_rate.toFixed(1)}%</strong> of
              closed leads resulted in a rental ({conversion.data.stages.rented}{" "}
              of {conversion.data.closed_leads}).
            </p>
            <p>
              {conversion.data.total_leads} total leads ·{" "}
              {conversion.data.stages.disputed} open disputes
            </p>
          </>
        )}
      </DataPanel>
    </DataPanel>
  );
}

export function AvailabilityControl({
  token,
  listing,
  onUpdated,
}: {
  token: string;
  listing: Listing;
  onUpdated: (listing: Listing) => void;
}) {
  const [selection, setSelection] = useState(
    listing.availability_status ?? "available",
  );
  const action = useRentalAction();
  return (
    <div>
      <form
        className="rental-availability"
        onSubmit={(event) => {
          event.preventDefault();
          void action.run(async () => {
            const updated = await rentalRequest<Listing>(
              `/listings/${listing.listing_id}/availability`,
              token,
              "PATCH",
              { availability_status: selection },
            );
            onUpdated(updated);
          }, "Room availability updated.");
        }}
      >
        <label htmlFor={`availability-${listing.listing_id}`}>
          Room availability
        </label>
        <select
          id={`availability-${listing.listing_id}`}
          value={selection}
          disabled={action.busy}
          onChange={(event) =>
            setSelection(event.target.value as typeof selection)
          }
        >
          <option value="available">Available</option>
          <option value="reserved">Reserved</option>
          <option value="occupied">Occupied</option>
        </select>
        <button
          className="secondary-button"
          type="submit"
          disabled={action.busy || selection === listing.availability_status}
        >
          {action.busy ? "Saving…" : "Save availability"}
        </button>
      </form>
      <ActionMessages {...action} />
    </div>
  );
}
