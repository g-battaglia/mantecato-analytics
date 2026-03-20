"use client";

import Link from "next/link";
import { usePathname, useParams } from "next/navigation";
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
} from "@/components/ui/sidebar";
import { SiteSelector } from "./SiteSelector";

const SITE_NAV_ITEMS = [
  { label: "Overview", href: "", icon: BarChart3 },
  { label: "Pages", href: "/pages", icon: FileText },
  { label: "Sources", href: "/sources", icon: Globe },
  { label: "Events", href: "/events", icon: MousePointerClick },
  { label: "Sessions", href: "/sessions", icon: Users },
  { label: "Devices", href: "/devices", icon: Monitor },
  { label: "Geo", href: "/geo", icon: Globe },
  { label: "Compare", href: "/compare", icon: GitCompare },
  { label: "Realtime", href: "/realtime", icon: Radio },
];

const ADVANCED_NAV_ITEMS = [
  { label: "Retention", href: "/retention", icon: TrendingUp },
  { label: "Funnels", href: "/funnels", icon: Filter },
  { label: "Journeys", href: "/journeys", icon: Shuffle },
  { label: "Revenue", href: "/revenue", icon: DollarSign },
];

export function AppSidebar() {
  const pathname = usePathname();
  const params = useParams();
  const siteId = params.siteId as string | undefined;
  const basePath = siteId ? `/sites/${siteId}` : "";

  return (
    <Sidebar collapsible="icon">
      <SidebarHeader>
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton size="lg" asChild>
              <Link href="/">
                <div className="flex aspect-square size-8 items-center justify-center rounded-lg bg-primary text-primary-foreground">
                  <BarChart3 className="size-4" />
                </div>
                <div className="grid flex-1 text-left text-sm leading-tight">
                  <span className="truncate font-semibold">Mantecato</span>
                  <span className="truncate text-xs text-muted-foreground">
                    Analytics
                  </span>
                </div>
              </Link>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarHeader>

      <SidebarSeparator />

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupLabel>Site</SidebarGroupLabel>
          <SidebarGroupContent>
            <SiteSelector />
          </SidebarGroupContent>
        </SidebarGroup>

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
                          <Link href={href}>
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
                          <Link href={href}>
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
                  tooltip="Dashboards"
                >
                  <Link href="/dashboards">
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
              tooltip="Settings"
            >
              <Link href="/settings">
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
