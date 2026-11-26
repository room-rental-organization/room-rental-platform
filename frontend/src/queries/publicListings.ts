import { ApiError, fetchJson, requestJson } from "../api";
import type { Listing } from "../types/listing";

export type ListingPage = { items: Listing[]; next_offset: number | null };

export async function fetchListingPage(params: string, offset: number): Promise<ListingPage> {
  try {
    return await fetchJson<ListingPage>(`/api/v1/listings/search?${params}&offset=${offset}&limit=8`);
  } catch (error) {
    // Frontend and backend deploy independently. An older backend routes "search"
    // to its integer detail route (422), or returns 404 if no route matches.
    const oldDetailRoute = error instanceof ApiError && Array.isArray(error.detail) &&
      error.detail.some(issue => Array.isArray(issue?.loc) &&
        issue.loc[0] === "path" && issue.loc[1] === "listing_id" && issue.type === "int_parsing");
    if (!(error instanceof ApiError) || (error.statusCode !== 404 && !oldDetailRoute)) throw error;
  }
  // Temporary deployment compatibility only. The normal path never loads all rooms.
  const rooms = await requestJson<Listing[]>("/api/v1/listings");
  const query = new URLSearchParams(params);
  const search = (query.get("search") ?? "").toLowerCase();
  const minimum = query.get("minimum_rent");
  const maximum = query.get("maximum_rent");
  const type = query.get("room_type");
  const date = query.get("available_by");
  const amenities = query.getAll("amenity");
  const matching = rooms.filter(room =>
    (!search || [room.title, room.address, room.area_name ?? ""].some(value => value.toLowerCase().includes(search))) &&
    (!type || room.room_type === type) && (!minimum || Number(room.monthly_rent) >= Number(minimum)) &&
    (!maximum || Number(room.monthly_rent) <= Number(maximum)) &&
    (!date || room.date_available <= date) && amenities.every(name => room.amenities.includes(name)),
  ).sort((a, b) => query.get("sort") === "rent_asc"
    ? Number(a.monthly_rent) - Number(b.monthly_rent) || b.listing_id - a.listing_id
    : b.created_at.localeCompare(a.created_at) || b.listing_id - a.listing_id);
  return { items: matching.slice(offset, offset + 8).map(room => ({ ...room,
    description: room.description.slice(0, 240), photos: room.photos.slice(0, 1) })),
    next_offset: offset + 8 < matching.length ? offset + 8 : null };
}
