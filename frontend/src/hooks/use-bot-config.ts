import { useParams } from "react-router";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";

export interface BotConfig {
  enabled: boolean;
  knownBots: boolean;
  emptyUa: boolean;
  clusterDetection: boolean;
  clusterBounceThreshold: number;
  clusterMinSize: number;
  zeroEngagement: boolean;
  minDuration: number;
  missingScreen: boolean;
  missingLanguage: boolean;
  highVelocityThreshold: number;
  excludedCountries: string[];
}

interface BotConfigResponse {
  id: string | null;
  websiteId: string;
  config: BotConfig;
  createdAt: string | null;
  updatedAt: string | null;
}

export const DEFAULT_BOT_CONFIG: BotConfig = {
  enabled: false,
  knownBots: true,
  emptyUa: true,
  clusterDetection: true,
  clusterBounceThreshold: 90,
  clusterMinSize: 100,
  zeroEngagement: false,
  minDuration: 0,
  missingScreen: false,
  missingLanguage: false,
  highVelocityThreshold: 60,
  excludedCountries: [],
};

export function useBotConfig() {
  const { siteId } = useParams() as { siteId: string };
  const queryClient = useQueryClient();

  const query = useQuery<BotConfigResponse>({
    queryKey: ["bot-config", siteId],
    queryFn: async () => {
      const res = await apiFetch(`/api/sites/${siteId}/bot-config`);
      if (!res.ok) throw new Error("Failed to fetch bot config");
      return res.json();
    },
    staleTime: 5 * 60 * 1000,
  });

  const mutation = useMutation({
    mutationFn: async (config: BotConfig) => {
      const res = await apiFetch(`/api/sites/${siteId}/bot-config`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(config),
      });
      if (!res.ok) throw new Error("Failed to save bot config");
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["bot-config", siteId], data);
      queryClient.invalidateQueries({ queryKey: ["bot-config", siteId] });
    },
  });

  const resetMutation = useMutation({
    mutationFn: async () => {
      const res = await apiFetch(`/api/sites/${siteId}/bot-config/reset`, {
        method: "POST",
      });
      if (!res.ok) throw new Error("Failed to reset bot config");
      return res.json();
    },
    onSuccess: (data) => {
      queryClient.setQueryData(["bot-config", siteId], data);
      queryClient.invalidateQueries({ queryKey: ["bot-config", siteId] });
    },
  });

  const config = query.data?.config ?? DEFAULT_BOT_CONFIG;

  return {
    config,
    isLoading: query.isLoading,
    save: mutation.mutate,
    isSaving: mutation.isPending,
    reset: resetMutation.mutate,
    isResetting: resetMutation.isPending,
  };
}
