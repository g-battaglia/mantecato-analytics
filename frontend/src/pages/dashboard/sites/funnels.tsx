import { useState } from "react";
import { useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
  CardDescription,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useDateParams } from "@/hooks/use-site-query";
import { Plus, Trash2, ArrowDown } from "lucide-react";
import { cn } from "@/lib/utils";

interface FunnelStep {
  step: number;
  label: string;
  visitors: number;
  dropoff: number;
  conversionRate: number;
}

interface StepDef {
  type: "url" | "event";
  value: string;
}

function FunnelVisualization({ steps }: { steps: FunnelStep[] }) {
  if (!steps || steps.length === 0) return null;

  const maxVisitors = steps[0]?.visitors || 1;

  return (
    <div className="space-y-1">
      {steps.map((step, i) => {
        const widthPercent = (step.visitors / maxVisitors) * 100;
        const overallConversion =
          maxVisitors > 0 ? (step.visitors / maxVisitors) * 100 : 0;

        return (
          <div key={step.step}>
            <div className="flex items-center gap-3">
              <div className="w-8 text-center text-xs font-medium text-muted-foreground">
                {step.step}
              </div>
              <div className="flex-1">
                <div
                  className="flex h-10 items-center rounded-md bg-primary/20 px-3"
                  style={{ width: `${Math.max(widthPercent, 8)}%` }}
                >
                  <span className="truncate text-xs font-medium">
                    {step.label}
                  </span>
                </div>
              </div>
              <div className="w-20 text-right text-xs tabular-nums">
                {step.visitors.toLocaleString()}
              </div>
              <div className="w-16 text-right text-xs tabular-nums text-muted-foreground">
                {overallConversion.toFixed(1)}%
              </div>
            </div>
            {i < steps.length - 1 && (
              <div className="ml-11 flex items-center gap-2 py-0.5">
                <ArrowDown className="h-3 w-3 text-muted-foreground" />
                <span className="text-[10px] text-red-500">
                  -{step.dropoff > 0 ? steps[i + 1].dropoff.toLocaleString() : 0} (
                  {steps[i + 1].conversionRate.toFixed(1)}% passed)
                </span>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function FunnelsPage() {
  const { siteId } = useParams() as { siteId: string };
  const { params: dateParams } = useDateParams();
  const [steps, setSteps] = useState<StepDef[]>([
    { type: "url", value: "" },
    { type: "url", value: "" },
  ]);
  const [windowMinutes, setWindowMinutes] = useState(60);
  const [submitted, setSubmitted] = useState(false);

  const validSteps = steps.filter((s) => s.value.trim() !== "");
  const canSubmit = validSteps.length >= 2;

  const { data, isLoading } = useQuery<FunnelStep[]>({
    queryKey: ["funnel", siteId, JSON.stringify(validSteps), windowMinutes],
    queryFn: async () => {
      const p = new URLSearchParams(dateParams);
      p.set("steps", JSON.stringify(validSteps));
      p.set("window", String(windowMinutes));
      const res = await fetch(`/api/sites/${siteId}/funnels?${p}`);
      if (!res.ok) throw new Error("Failed to fetch funnel");
      return res.json();
    },
    enabled: submitted && canSubmit,
  });

  function addStep() {
    setSteps([...steps, { type: "url", value: "" }]);
  }

  function removeStep(index: number) {
    if (steps.length <= 2) return;
    setSteps(steps.filter((_, i) => i !== index));
  }

  function updateStep(index: number, field: "type" | "value", val: string) {
    const updated = [...steps];
    updated[index] = { ...updated[index], [field]: val };
    setSteps(updated);
    setSubmitted(false);
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-2">
          <CardTitle className="text-sm font-medium">Funnel Builder</CardTitle>
          <CardDescription className="text-xs">
            Define steps to analyze conversion flow
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-3">
            {steps.map((step, i) => (
              <div key={i} className="flex items-end gap-2">
                <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted text-xs font-medium">
                  {i + 1}
                </div>
                <div className="grid flex-1 gap-1">
                  <Label className="text-[10px] text-muted-foreground">
                    Type
                  </Label>
                  <Select
                    value={step.type}
                    onValueChange={(v) => updateStep(i, "type", v)}
                  >
                    <SelectTrigger className="h-8 text-xs">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="url">URL Path</SelectItem>
                      <SelectItem value="event">Event Name</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <div className="grid flex-[2] gap-1">
                  <Label className="text-[10px] text-muted-foreground">
                    Value
                  </Label>
                  <Input
                    className="h-8 text-xs"
                    placeholder={
                      step.type === "url" ? "/checkout" : "purchase"
                    }
                    value={step.value}
                    onChange={(e) => updateStep(i, "value", e.target.value)}
                  />
                </div>
                {steps.length > 2 && (
                  <Button
                    variant="ghost"
                    size="sm"
                    className="h-8 w-8 p-0"
                    onClick={() => removeStep(i)}
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
            ))}

            <div className="flex items-center gap-2">
              <Button
                variant="outline"
                size="sm"
                className="h-8 gap-1 text-xs"
                onClick={addStep}
              >
                <Plus className="h-3.5 w-3.5" />
                Add Step
              </Button>
              <div className="flex items-center gap-1 text-xs text-muted-foreground">
                <span>Window:</span>
                <Input
                  type="number"
                  className="h-8 w-16 text-xs"
                  value={windowMinutes}
                  onChange={(e) => setWindowMinutes(Number(e.target.value))}
                  min={1}
                />
                <span>min</span>
              </div>
              <div className="flex-1" />
              <Button
                size="sm"
                className="h-8 text-xs"
                disabled={!canSubmit}
                onClick={() => setSubmitted(true)}
              >
                Run Funnel
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {submitted && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm font-medium">Results</CardTitle>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <div className="space-y-2">
                {Array.from({ length: validSteps.length }).map((_, i) => (
                  <Skeleton key={i} className="h-10 w-full" />
                ))}
              </div>
            ) : data && data.length > 0 ? (
              <div className="space-y-4">
                <FunnelVisualization steps={data} />
                <div className="flex items-center gap-4 rounded-md bg-muted/50 p-3">
                  <div className="text-xs text-muted-foreground">
                    Overall conversion:
                  </div>
                  <div className="text-sm font-semibold tabular-nums">
                    {data[0].visitors > 0
                      ? (
                          (data[data.length - 1].visitors /
                            data[0].visitors) *
                          100
                        ).toFixed(1)
                      : 0}
                    %
                  </div>
                  <div className="text-xs text-muted-foreground">
                    ({data[data.length - 1].visitors.toLocaleString()} of{" "}
                    {data[0].visitors.toLocaleString()})
                  </div>
                </div>
              </div>
            ) : (
              <p className="py-8 text-center text-sm text-muted-foreground">
                No funnel data — try different steps or a wider date range
              </p>
            )}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
