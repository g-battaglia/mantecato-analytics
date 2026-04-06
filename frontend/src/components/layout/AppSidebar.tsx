import { Link } from "react-router";
import { useLocation, useParams } from "react-router";
import {
  BarChart3,
  FileText,
  Globe,
  Monitor,
  MousePointerClick,
  Users,
  TrendingUp,
  Shuffle,
  GitCompare,
  DollarSign,
  Radio,
  LayoutDashboard,
  Filter,
  Settings,
  Timer,
} from "lucide-react";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarFooter,
  SidebarSeparator,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { SiteSelector } from "./SiteSelector";

const SITE_NAV_ITEMS = [
  { label: "Overview", href: "", icon: BarChart3, tooltip: "Key metrics at a glance: pageviews, visitors, bounce rate, and traffic trends" },
  { label: "Pages", href: "/pages", icon: FileText, tooltip: "Page-level analytics: views, time on page, bounce rate, entry and exit pages" },
  { label: "Sources", href: "/sources", icon: Globe, tooltip: "Where your traffic comes from: referrers, UTM campaigns, and channels" },
  { label: "Events", href: "/events", icon: MousePointerClick, tooltip: "Custom events tracked on your site: clicks, form submissions, and other interactions" },
  { label: "Sessions", href: "/sessions", icon: Users, tooltip: "Browse individual visitor sessions and their activity timelines" },
  { label: "Devices", href: "/devices", icon: Monitor, tooltip: "Visitor technology breakdown: browsers, operating systems, screen sizes, and languages" },
  { label: "Geo", href: "/geo", icon: Globe, tooltip: "Geographic distribution of visitors by country, region, and city" },
  { label: "Engagement", href: "/engagement", icon: Timer, tooltip: "Visit duration distribution, percentiles, time-on-page per page, and bounce rate breakdown by entry page and source" },
  { label: "Compare", href: "/compare", icon: GitCompare, tooltip: "Compare metrics between two time periods to spot trends and changes" },
  { label: "Realtime", href: "/realtime", icon: Radio, tooltip: "Live view of active visitors, current pages, and incoming events" },
];

const ADVANCED_NAV_ITEMS = [
  { label: "Retention", href: "/retention", icon: TrendingUp, tooltip: "Cohort retention analysis: how many visitors return over time" },
  { label: "Funnels", href: "/funnels", icon: Filter, tooltip: "Define multi-step funnels to measure conversion rates and drop-off points" },
  { label: "Journeys", href: "/journeys", icon: Shuffle, tooltip: "Most common page sequences visitors follow through your site" },
  { label: "Revenue", href: "/revenue", icon: DollarSign, tooltip: "Revenue analytics: total income, revenue per event, and geographic breakdown" },
];

export function AppSidebar() {
  const pathname = useLocation().pathname;
  const params = useParams();
  const siteId = params.siteId as string | undefined;
  const basePath = siteId ? `/sites/${siteId}` : "";

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader className="flex flex-row items-center gap-1 h-auto py-2 px-2">
        <SidebarTrigger className="shrink-0" />
        <div className="flex-1 min-w-0 group-data-[collapsible=icon]:hidden">
          <SiteSelector />
        </div>
      </SidebarHeader>

      <SidebarContent>

        {siteId && (
          <>
            <SidebarGroup>
              <SidebarGroupLabel>Analytics</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {SITE_NAV_ITEMS.map((item) => {
                    const href = `${basePath}${item.href}`;
                    const isActive =
                      item.href === ""
                        ? pathname === basePath
                        : pathname.startsWith(href);
                    return (
                      <SidebarMenuItem key={item.label}>
                        <SidebarMenuButton
                          asChild
                          isActive={isActive}
                          tooltip={item.label}
                        >
                          <Link to={href}>
                            <item.icon />
                            <span>{item.label}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>

            <SidebarGroup>
              <SidebarGroupLabel>Advanced</SidebarGroupLabel>
              <SidebarGroupContent>
                <SidebarMenu>
                  {ADVANCED_NAV_ITEMS.map((item) => {
                    const href = `${basePath}${item.href}`;
                    const isActive = pathname.startsWith(href);
                    return (
                      <SidebarMenuItem key={item.label}>
                        <SidebarMenuButton
                          asChild
                          isActive={isActive}
                          tooltip={item.label}
                        >
                          <Link to={href}>
                            <item.icon />
                            <span>{item.label}</span>
                          </Link>
                        </SidebarMenuButton>
                      </SidebarMenuItem>
                    );
                  })}
                </SidebarMenu>
              </SidebarGroupContent>
            </SidebarGroup>
          </>
        )}

        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton
                  asChild
                  isActive={pathname === "/dashboards"}
                  tooltip="Create and manage custom dashboards with drag-and-drop widgets"
                >
                  <Link to="/dashboards">
                    <LayoutDashboard />
                    <span>Dashboards</span>
                  </Link>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              asChild
              isActive={pathname === "/settings"}
              tooltip="Preferences: theme, default date range, number format, and timezone"
            >
              <Link to="/settings">
                <Settings />
                <span>Settings</span>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
