"use client";

import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Construction } from "lucide-react";

export default function FunnelsPage() {
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Funnel Analysis</CardTitle>
          <CardDescription>
            Define conversion funnels and track drop-off at each step.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
            <Construction className="mb-3 h-8 w-8" />
            <p className="text-sm font-medium">Coming Soon</p>
            <p className="mt-1 text-xs">
              Multi-step funnel builder with conversion visualization.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
