/**
 * useCurrentUser — React Query hook for /api/auth/me.
 */

import { useQuery } from "@tanstack/react-query";
import { fetchMe } from "@/api/auth";
import type { MeResponse } from "@/api/auth";

export const ME_QUERY_KEY = "me";

export function useCurrentUser() {
  return useQuery<MeResponse, Error>({
    queryKey: [ME_QUERY_KEY],
    queryFn: fetchMe,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}
