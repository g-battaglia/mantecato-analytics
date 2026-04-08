import { useMemo } from "react";
import { useParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useFiltersStore } from "@/stores/filters";
import { usePreferencesStore } from "@/stores/preferences";
import { resolveDateRange, resolveGranularity } from "@/lib/date";
import { apiFetch } from "@/lib/api";
import type { BotConfig } from "./use-bot-config";

export function useDateParams() {
  const { preset, customStart, customEnd, granularity, filters } =
    useFiltersStore();
  const botFilterEnabled = usePreferencesStore((s) => s.botFilterEnabled);
  const { siteId } = useParams() as { siteId: string };
  const queryClient = useQueryClient();

  return useMemo(() => {
    const range = resolveDateRange(preset);

    const startDate =
      preset === "custom" && customStart
        ? customStart
        : range?.startDate.toISOString() ??
          new Date("2020-01-01").toISOString();
    const endDate =
      preset === "custom" && customEnd
        ? customEnd
        : range?.endDate.toISOString() ?? new Date().toISOString();

    const resolvedGran = range
      ? resolveGranularity(granularity, range)
      : "day";

    const params = new URLSearchParams({
      range: preset,
      ...(preset === "custom" ? { start: startDate, end: endDate } : {}),
      granularity: resolvedGran,
    });

    for (const filter of filters) {
      params.append("f", `${filter.column}:${filter.operator}:${filter.value}`);
    }

    // Bot filter: read config from React Query cache and pass as JSON param
    let botKey = "off";
    if (botFilterEnabled) {
      const cached = queryClient.getQueryData<{ config: BotConfig }>(["bot-config", siteId]);
      const config = cached?.config;
      if (config) {
        const configJson = JSON.stringify(config);
        params.set("bot_filter", configJson);
        botKey = configJson;
      } else {
        // No config cached yet — use a marker so backend knows to apply defaults
        params.set("bot_filter", JSON.stringify({ enabled: true }));
        botKey = "defaults";
      }
    }

    const filterKey = filters
      .map((f) => `${f.column}:${f.operator}:${f.value}`)
      .sort();

    const queryKeyParts =
      preset === "custom"
        ? [preset, startDate, endDate, resolvedGran, botKey, ...filterKey]
        : [preset, resolvedGran, botKey, ...filterKey];

    return {
      params,
      startDate,
      endDate,
      granularity: resolvedGran,
      preset,
      queryKeyParts,
    };
  }, [preset, customStart, customEnd, granularity, filters, botFilterEnabled, siteId, queryClient]);
}

export function useSiteQuery<T>(
  endpoint: string,
  queryKey: string[],
  extraParams?: Record<string, string>
) {
  const { siteId } = useParams() as { siteId: string };
  const { params, queryKeyParts } = useDateParams();

  const finalParams = useMemo(() => {
    if (!extraParams) return params;
    const p = new URLSearchParams(params);
    Object.entries(extraParams).forEach(([key, value]) => {
      p.set(key, value);
    });
    return p;
  }, [params, extraParams]);

  return useQuery<T>({
    queryKey: [
      ...queryKey,
      siteId,
      ...queryKeyParts,
      ...(extraParams ? Object.values(extraParams) : []),
    ],
    queryFn: async () => {
      const res = await apiFetch(
        `/api/sites/${siteId}/${endpoint}?${finalParams}`
      );
      if (!res.ok) throw new Error(`Failed to fetch ${endpoint}`);
      return res.json();
    },
  });
}
