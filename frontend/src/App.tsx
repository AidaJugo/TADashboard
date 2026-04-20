import { BrowserRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { ReportPage } from "@/pages/ReportPage";
import { AdminShell } from "@/pages/admin/AdminShell";
import { AdminUsersPage } from "@/pages/admin/AdminUsersPage";
import { AdminConfigPage } from "@/pages/admin/AdminConfigPage";

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
      <BrowserRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
        <Routes>
          <Route path="/" element={<ReportPage />} />
          <Route path="/admin" element={<AdminShell />}>
            <Route path="users" element={<AdminUsersPage />} />
            <Route path="config" element={<AdminConfigPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
