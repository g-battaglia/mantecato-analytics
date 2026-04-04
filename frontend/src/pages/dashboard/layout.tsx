import { Outlet, Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";
import { useAuthStore } from "@/stores/auth";
import { apiFetch } from "@/lib/api";

/**
 * Client-side auth guard. Redirects to /login if no token or if the
 * token is invalid (401 from /api/sites).
 */
export function DashboardLayout() {
  const token = useAuthStore((s) => s.token);

  const { isLoading, isError } = useQuery({
    queryKey: ["auth-check"],
    queryFn: async () => {
      const res = await apiFetch("/api/sites");
      if (!res.ok) throw new Error("unauthorized");
      return res.json();
    },
    retry: false,
    enabled: !!token,
  });

  if (!token) return <Navigate to="/login" replace />;
  if (isLoading) return null;
  if (isError) return <Navigate to="/login" replace />;

  return (
    <SidebarProvider>
      <AppSidebar />
      <SidebarInset>
        <Outlet />
      </SidebarInset>
    </SidebarProvider>
  );
}
