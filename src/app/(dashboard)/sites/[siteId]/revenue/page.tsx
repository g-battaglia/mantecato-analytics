"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Construction } from "lucide-react";

export default function RevenuePage() {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Revenue Analytics</CardTitle>
          <CardDescription>
            Track revenue from events with monetary values.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Construction className="mb-3 h-8 w-8" />
            <p className="text-sm font-medium">Coming Soon</p>
            <p className="mt-1 text-xs">
              Revenue over time, by source, by country, and ARPU.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
