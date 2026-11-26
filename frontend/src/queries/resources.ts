import { useEffect, useState, type SetStateAction } from "react";
import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { fetchJson } from "../api";
import { isCurrentQuerySession, queryClient, querySessionGeneration, resourceOptions } from "../queryClient";
import type { Listing } from "../types/listing";
import { fetchListingPage } from "./publicListings";

export function useDebouncedValue<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export function useResource<T>(path: string, token: string | null = null, enabled = true) {
  return useQuery({ ...resourceOptions(`/api/v1${path}`, token),
    enabled: enabled && (token === null || isCurrentQuerySession(token)),
    queryFn: (context) => fetchJson<T>(`/api/v1${path}`, {
      signal: token ? context.signal : undefined, headers: token ? { Authorization: `Bearer ${token}` } : undefined,
    }),
  });
}

export function usePublicListings(params: string, enabled = true) {
  const normalized = new URLSearchParams(params);
  normalized.sort();
  const canonical = normalized.toString();
  const path = `/api/v1/listings/search?${canonical}`;
  return useInfiniteQuery({ ...resourceOptions(path),
    queryKey: ["public", "listing-pages", canonical], enabled, initialPageParam: 0,
    // Public requests may finish across a route change. Query deduplicates StrictMode mounts.
    queryFn: ({ pageParam }) => fetchListingPage(canonical, pageParam),
    getNextPageParam: (page) => page.next_offset ?? undefined,
  });
}

export function useRoomDetails(listingId: number) {
  return useResource<Listing>(`/listings/${listingId}`);
}

export function useResourceState<T>(path: string, token: string | null, initial: T, enabled = true) {
  const query = useResource<T>(path, token, enabled);
  const generation = querySessionGeneration();
  const key = resourceOptions(`/api/v1${path}`, token).queryKey;
  return { ...query, data: query.data ?? initial,
    setData: (update: SetStateAction<T>) => {
      if (generation !== querySessionGeneration()) return;
      queryClient.setQueryData<T>(key,
        previous => typeof update === "function" ? (update as (value: T) => T)(previous ?? initial) : update);
    },
  };
}
