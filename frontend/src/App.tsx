import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ReportPage } from "@/pages/ReportPage";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ReportPage />
    </QueryClientProvider>
  );
}
