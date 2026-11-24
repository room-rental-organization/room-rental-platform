import { useState, type ChangeEvent } from "react";

import GoogleAddressSearch, {
  type GoogleAddressSelection,
} from "./GoogleAddressSearch";
import type { Amenity } from "../types/listing";
import "./SearchFilters.css";

export type ListingFilters = {
  location: string;
  roomType: string;
  minimumRent: string;
  maximumRent: string;
  amenities: string[];
};

type SearchFiltersProps = {
  amenities: Amenity[];
  availableBy: string;
  filters: ListingFilters;
  onAvailabilityChange: (value: string) => void;
  onChange: (filters: ListingFilters) => void;
  onLocationSelected: (selection: GoogleAddressSelection) => void;
  onRadiusChange: (radius: 5 | 10) => void;
  radius: 5 | 10;
  hasLocationSelection: boolean;
};

export default function SearchFilters({
  amenities,
  availableBy,
  filters,
  onAvailabilityChange,
  onChange,
  onLocationSelected,
  onRadiusChange,
  radius,
  hasLocationSelection,
}: SearchFiltersProps) {
  const [advancedOpen, setAdvancedOpen] = useState(false);
  function updateField(
    field: keyof ListingFilters,
    value: string,
  ): void {
    onChange({ ...filters, [field]: value });
  }

  function updateRent(
    field: "minimumRent" | "maximumRent",
    event: ChangeEvent<HTMLInputElement>,
  ): void {
    const value = event.currentTarget.value;
    if (value === "" || Number(value) >= 0) {
      updateField(field, value);
    }
  }

  function toggleAmenity(name: string, checked: boolean): void {
    const selected = new Set(filters.amenities);
    if (checked) {
      selected.add(name);
    } else {
      selected.delete(name);
    }
    onChange({ ...filters, amenities: Array.from(selected) });
  }

  return (
    <section aria-label="Filter listings" className="discovery-search">
      <div className="search-primary">
        <div className="search-location"><label className="field-label" htmlFor="room-location">Where would you like to live?</label><input id="room-location" type="search" placeholder="Try Sandton, Rosebank or your suburb" value={filters.location} onChange={(event) => updateField("location", event.target.value)} /></div>
        <label>Room type<select value={filters.roomType} onChange={(event) => updateField("roomType", event.target.value)}><option value="">Any room type</option><option value="single_room">Single room</option><option value="shared_room">Shared room</option><option value="bachelor_flat">Bachelor flat</option><option value="self_contained">Self-contained</option></select></label>
        <label>Monthly budget (R)<input type="number" min="0" placeholder="Your maximum" value={filters.maximumRent} onChange={(event) => updateRent("maximumRent", event)} /></label>
        <button type="button" className="filter-toggle" aria-expanded={advancedOpen} aria-controls="advanced-room-filters" onClick={() => setAdvancedOpen(!advancedOpen)}>Filters {filters.amenities.length > 0 ? `(${filters.amenities.length})` : "+"}</button>
      </div>
      <div id="advanced-room-filters" hidden={!advancedOpen} className="search-advanced">
        <div className="search-advanced-grid"><div><p className="field-label">Search near a place</p>{advancedOpen && <GoogleAddressSearch value={filters.location} onChange={(value) => updateField("location", value)} onResultSelected={onLocationSelected} />}</div>
        <label>Distance<select value={radius} disabled={!hasLocationSelection} onChange={(event) => onRadiusChange(event.target.value === "10" ? 10 : 5)}><option value={5}>Within 5 km</option><option value={10}>Within 10 km</option></select><small>{hasLocationSelection ? "Distance from your selected place." : "Select a place to search by distance."}</small></label>
        <label>Minimum rent (R)<input type="number" min="0" placeholder="No minimum" value={filters.minimumRent} onChange={(event) => updateRent("minimumRent", event)} /></label>
        <label>Move in by<input type="date" value={availableBy} onChange={(event) => onAvailabilityChange(event.target.value)} /></label></div>
        <fieldset className="amenity-picker"><legend>Make yourself at home</legend>{amenities.map((amenity) => <label key={amenity.amenity_id}><input type="checkbox" checked={filters.amenities.includes(amenity.name)} onChange={(event) => toggleAmenity(amenity.name, event.target.checked)} />{amenity.name}</label>)}</fieldset>
        <button type="button" className="text-button" onClick={() => { onChange({ location: "", roomType: "", minimumRent: "", maximumRent: "", amenities: [] }); onAvailabilityChange(""); onRadiusChange(5); }}>Clear all filters</button>
      </div>
    </section>
  );
}
