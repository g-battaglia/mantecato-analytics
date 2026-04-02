import { Outlet, Navigate } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { SidebarProvider, SidebarInset } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/layout/AppSidebar";

/**
 * Client-side auth guard. Checks auth by hitting a lightweight endpoint
 * (/api/sites). Redirects to /login on 401.
 */
export function DashboardLayout() {
  const { isLoading, isError } = useQuery({
    queryKey: ["auth-check"],
    queryFn: async () => {
      const res = await fetch("/api/sites");
      if (res.status === 401) throw new Error("unauthorized");
      return res.json();
    },
    retry: false,
  });

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
