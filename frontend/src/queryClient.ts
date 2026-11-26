import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({ defaultOptions: { queries: {
  staleTime: 60_000, gcTime: 15 * 60_000, refetchOnWindowFocus: false,
  retry: (count, error) => count < 1 && !("statusCode" in error &&
    Number(error.statusCode) >= 400 && Number(error.statusCode) < 500),
} } });

let sessionToken: string | null = null;
let generation = 0;

export function setQuerySession(token: string | null) {
  if (token === sessionToken) return;
  sessionToken = token;
  generation += 1;
  void queryClient.cancelQueries({ queryKey: ["private"] });
  queryClient.removeQueries({ queryKey: ["private"] });
  queryClient.getMutationCache().clear();
}

export function resourceOptions(path: string, authorization: string | null = null) {
  const url = new URL(path, "https://query.invalid");
  url.searchParams.sort();
  const canonical = url.pathname + url.search;
  const privateResource = authorization !== null;
  const catalog = /^\/api\/v1\/(areas|amenities)(\?|$)/.test(canonical);
  const detail = /^\/api\/v1\/listings\/\d+$/.test(canonical);
  return {
    queryKey: privateResource ? ["private", generation,
      authorization?.replace(/^Bearer /, "") === sessionToken ? "current" : "retired", canonical]
      : ["public", canonical],
    staleTime: privateResource || detail ? 30_000 : catalog ? 30 * 60_000 : 60_000,
    gcTime: privateResource ? 5 * 60_000 : catalog ? 60 * 60_000 : detail ? 10 * 60_000 : 15 * 60_000,
  };
}

export function canCacheResource(path: string) {
  // Auth, messages, notifications and provider-derived map positions remain live.
  return !/(\/auth\/|\/map-location|\/users\/me$|\/messages|\/notifications|\/whatsapp)/.test(path);
}

export function invalidateAfterMutation(path: string, startedGeneration: number) {
  if (startedGeneration !== generation) return;
  if (/\/messages|\/notifications|\/whatsapp|\/auth\//.test(path)) return;
  void queryClient.invalidateQueries({ queryKey: ["private"] });
  if (/\/listings|\/areas|\/amenities|\/interest-opportunities|\/rental-interests|\/assistant/.test(path)) {
    void queryClient.invalidateQueries({ queryKey: ["public"] });
  }
}

export function querySessionGeneration() { return generation; }

export function isCurrentQuerySession(token: string) {
  return token.replace(/^Bearer /, "") === sessionToken;
}
