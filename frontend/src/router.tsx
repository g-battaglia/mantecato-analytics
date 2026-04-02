import { Routes, Route, Navigate } from "react-router";
import { DashboardLayout } from "@/pages/dashboard/layout";
import { SiteLayout } from "@/pages/dashboard/sites/layout";
import { LoginPage } from "@/pages/login";
import { SharePage } from "@/pages/share";

import { HomePage } from "@/pages/dashboard/home";
import { OverviewPage } from "@/pages/dashboard/sites/overview";
import { PagesPage } from "@/pages/dashboard/sites/pages";
import { SourcesPage } from "@/pages/dashboard/sites/sources";
import { EventsPage } from "@/pages/dashboard/sites/events";
import { SessionsPage } from "@/pages/dashboard/sites/sessions";
import { DevicesPage } from "@/pages/dashboard/sites/devices";
import { GeoPage } from "@/pages/dashboard/sites/geo";
import { RealtimePage } from "@/pages/dashboard/sites/realtime";
import { ComparePage } from "@/pages/dashboard/sites/compare";
import { RetentionPage } from "@/pages/dashboard/sites/retention";
import { FunnelsPage } from "@/pages/dashboard/sites/funnels";
import { JourneysPage } from "@/pages/dashboard/sites/journeys";
import { EngagementPage } from "@/pages/dashboard/sites/engagement";
import { RevenuePage } from "@/pages/dashboard/sites/revenue";
import { DashboardsPage } from "@/pages/dashboard/dashboards";
import { DashboardDetailPage } from "@/pages/dashboard/dashboards/detail";
import { SettingsPage } from "@/pages/dashboard/settings";

export function AppRouter() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/share/:shareId" element={<SharePage />} />

      {/* Protected dashboard routes */}
      <Route element={<DashboardLayout />}>
        <Route index element={<HomePage />} />

        {/* Site-level routes: header with site name, filter bar, scrollable content */}
        <Route path="sites/:siteId" element={<SiteLayout />}>
          <Route index element={<OverviewPage />} />
          <Route path="pages" element={<PagesPage />} />
          <Route path="sources" element={<SourcesPage />} />
          <Route path="events" element={<EventsPage />} />
          <Route path="sessions" element={<SessionsPage />} />
          <Route path="devices" element={<DevicesPage />} />
          <Route path="geo" element={<GeoPage />} />
          <Route path="realtime" element={<RealtimePage />} />
          <Route path="compare" element={<ComparePage />} />
          <Route path="retention" element={<RetentionPage />} />
          <Route path="funnels" element={<FunnelsPage />} />
          <Route path="journeys" element={<JourneysPage />} />
          <Route path="engagement" element={<EngagementPage />} />
          <Route path="revenue" element={<RevenuePage />} />
        </Route>

        <Route path="dashboards" element={<DashboardsPage />} />
        <Route path="dashboards/:dashboardId" element={<DashboardDetailPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
