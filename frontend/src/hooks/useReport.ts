/**
 * useReport — React Query hook for GET /api/report.
 *
 * Wraps fetchReport with a stable query key so PeriodNav, YearSelector, and
 * YoYToggle can all trigger re-fetches by changing their respective pieces of
 * state without prop-drilling.
 */

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { fetchReport, postRefresh } from "@/api/report";
import type { ReportParams, ReportResponse } from "@/api/report";

export const REPORT_QUERY_KEY = "report";

export function useReport(params: ReportParams) {
  return useQuery<ReportResponse, Error>({
    queryKey: [REPORT_QUERY_KEY, params],
    queryFn: () => fetchReport(params),
    staleTime: 55_000, // slightly under the backend's 60 s TTL
    retry: 1,
  });
}

export function useRefresh() {
  const qc = useQueryClient();
  return useMutation<void, Error>({
    mutationFn: postRefresh,
    onSuccess: () => {
      // Invalidate all report queries so the next useReport call re-fetches.
      void qc.invalidateQueries({ queryKey: [REPORT_QUERY_KEY] });
    },
  });
}
