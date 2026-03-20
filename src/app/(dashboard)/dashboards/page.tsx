"use client";

import { Header } from "@/components/layout/Header";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Construction } from "lucide-react";

export default function DashboardsPage() {
  return (
    <>
      <Header title="Custom Dashboards" />
      <div className="flex-1 p-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Custom Dashboards</CardTitle>
            <CardDescription>
              Create and manage custom dashboards with drag-and-drop widgets.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
              <Construction className="mb-3 h-8 w-8" />
              <p className="text-sm font-medium">Coming Soon</p>
              <p className="mt-1 text-xs">
                Drag-and-drop dashboard builder with configurable widgets.
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </>
  );
}
