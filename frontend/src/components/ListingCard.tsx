import { useState } from "react";
import type { Listing } from "../types/listing";
import AppLink from "./AppLink";

export type { Listing, ListingPhoto } from "../types/listing";

type ListingCardProps = {
  listing: Listing;
  onNavigate: (path: string) => void;
};

export default function ListingCard({ listing, onNavigate }: ListingCardProps) {
  const [imageFailed, setImageFailed] = useState(false);
  const roomType = listing.room_type.replaceAll("_", " ");
  const amount = Number(listing.monthly_rent);
  const rent = Number.isFinite(amount)
    ? new Intl.NumberFormat("en-ZA", {
        style: "currency",
        currency: "ZAR",
        maximumFractionDigits: 2,
      }).format(amount)
    : "Rent unavailable";
  const date = new Date(`${listing.date_available}T00:00:00`);
  const available = Number.isNaN(date.getTime()) ? "Ask about availability" : `Available ${new Intl.DateTimeFormat("en-ZA", { day: "numeric", month: "short", year: "numeric" }).format(date)}`;
  return (
    <article className="room-card" aria-labelledby={`listing-${listing.listing_id}`}>
      <AppLink
        className="room-card-image"
        href={`/listings/${listing.listing_id}`}
        onNavigate={onNavigate}
        aria-label={`View ${listing.title}`}
      >
        {listing.photos[0] && !imageFailed ? (
          <img
            alt={`Room interior for ${listing.title}`}
            src={listing.photos[0].url}
            loading="lazy"
            onError={() => setImageFailed(true)}
          />
        ) : (
          <div className="room-photo-placeholder">
            <span aria-hidden="true">&#8962;</span>
            <small>Your next space</small>
          </div>
        )}
        <span className="room-type-badge">{roomType}</span>
      </AppLink>
      <div className="room-card-body">
        <p className="room-card-location">{listing.area_name ?? listing.address}</p>
        <h2 id={`listing-${listing.listing_id}`}>
          <AppLink href={`/listings/${listing.listing_id}`} onNavigate={onNavigate}>
            {listing.title}
          </AppLink>
        </h2>
        <p className="room-card-description">{listing.description}</p>
        <div className="room-amenities" aria-label="Amenities">
          {listing.amenities.slice(0, 3).map(amenity => <span key={amenity}>{amenity}</span>)}
          {listing.amenities.length > 3 && <span>+{listing.amenities.length - 3}</span>}
        </div>
        <p className="room-card-availability">{available}</p>
        <div className="room-card-bottom">
          <p><strong>{rent}</strong><span> / month</span></p>
          <AppLink
            href={`/listings/${listing.listing_id}`}
            onNavigate={onNavigate}
            aria-label={`View details for ${listing.title}`}
          >
            View room &#8599;
          </AppLink>
        </div>
      </div>
    </article>
  );
}
