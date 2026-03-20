"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Construction } from "lucide-react";

export default function JourneysPage() {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">User Journeys</CardTitle>
          <CardDescription>
            Visualize how users navigate through your site.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Construction className="mb-3 h-8 w-8" />
            <p className="text-sm font-medium">Coming Soon</p>
            <p className="mt-1 text-xs">
              Sankey diagram of page-to-page flows and common paths.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
