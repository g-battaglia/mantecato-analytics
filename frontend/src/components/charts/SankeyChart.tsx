
import { useMemo } from "react";
import {
  sankey,
  sankeyLinkHorizontal,
  type SankeyNode,
  type SankeyLink,
} from "d3-sankey";
import { CHART_COLORS } from "@/lib/constants";
import { formatNumber } from "@/lib/format";

interface SankeyData {
  nodes: { id: string; label: string }[];
  links: { source: string; target: string; value: number }[];
}

interface SankeyChartProps {
  data: SankeyData;
  height?: number;
  /** Max nodes per column (step) before grouping into "Other" */
  maxNodesPerStep?: number;
}

type SNode = SankeyNode<{ id: string; label: string }, object>;
type SLink = SankeyLink<{ id: string; label: string }, object>;

/**
 * Build a SankeyData structure from journey path data.
 * Each step in the path creates a node "step_N:page" and links flow between consecutive steps.
 */
export function buildSankeyFromJourneys(
  journeys: { path: string[]; count: number }[],
  maxNodesPerStep = 8
): SankeyData {
  // Count links between step positions
  const linkMap = new Map<string, number>();
  const nodeSet = new Set<string>();

  for (const { path, count } of journeys) {
    for (let i = 0; i < path.length - 1; i++) {
      const sourceId = `${i}:${path[i]}`;
      const targetId = `${i + 1}:${path[i + 1]}`;
      nodeSet.add(sourceId);
      nodeSet.add(targetId);
      const key = `${sourceId}||${targetId}`;
      linkMap.set(key, (linkMap.get(key) ?? 0) + count);
    }
  }

  // Group small nodes per step into "Other"
  const stepNodes = new Map<number, Map<string, number>>();
  for (const nodeId of nodeSet) {
    const step = parseInt(nodeId.split(":")[0]);
    if (!stepNodes.has(step)) stepNodes.set(step, new Map());
    stepNodes.get(step)!.set(nodeId, 0);
  }

  // Sum up traffic per node
  for (const [key, value] of linkMap) {
    const [source] = key.split("||");
    const step = parseInt(source.split(":")[0]);
    const map = stepNodes.get(step)!;
    map.set(source, (map.get(source) ?? 0) + value);
  }
  // Also sum incoming for target nodes
  for (const [key, value] of linkMap) {
    const [, target] = key.split("||");
    const step = parseInt(target.split(":")[0]);
    const map = stepNodes.get(step)!;
    map.set(target, (map.get(target) ?? 0) + value);
  }

  // For each step, keep top N nodes, merge rest into "Other"
  const nodeRemap = new Map<string, string>();
  const finalNodes: { id: string; label: string }[] = [];

  for (const [step, nodesMap] of stepNodes) {
    const sorted = [...nodesMap.entries()].sort((a, b) => b[1] - a[1]);
    const kept = sorted.slice(0, maxNodesPerStep);
    const rest = sorted.slice(maxNodesPerStep);

    for (const [nodeId] of kept) {
      const label = nodeId.substring(nodeId.indexOf(":") + 1);
      finalNodes.push({ id: nodeId, label });
      nodeRemap.set(nodeId, nodeId);
    }

    if (rest.length > 0) {
      const otherId = `${step}:__other__`;
      finalNodes.push({ id: otherId, label: `Other (${rest.length})` });
      for (const [nodeId] of rest) {
        nodeRemap.set(nodeId, otherId);
      }
    }
  }

  // Rebuild links with remapped nodes
  const finalLinkMap = new Map<string, number>();
  for (const [key, value] of linkMap) {
    const [source, target] = key.split("||");
    const mappedSource = nodeRemap.get(source) ?? source;
    const mappedTarget = nodeRemap.get(target) ?? target;
    if (mappedSource === mappedTarget) continue; // skip self-loops
    const newKey = `${mappedSource}||${mappedTarget}`;
    finalLinkMap.set(newKey, (finalLinkMap.get(newKey) ?? 0) + value);
  }

  const links = [...finalLinkMap.entries()].map(([key, value]) => {
    const [source, target] = key.split("||");
    return { source, target, value };
  });

  return { nodes: finalNodes, links };
}

export function SankeyChart({
  data,
  height = 400,
  maxNodesPerStep: _unused,
}: SankeyChartProps) {
  const width = 800; // Fixed internal width, ResponsiveContainer handles scaling

  const { nodes, links } = useMemo(() => {
    if (data.nodes.length === 0 || data.links.length === 0) {
      return { nodes: [] as SNode[], links: [] as SLink[] };
    }

    // Build index map
    const nodeIndex = new Map(data.nodes.map((n, i) => [n.id, i]));

    const sankeyNodes = data.nodes.map((n) => ({ ...n }));
    const sankeyLinks = data.links
      .filter(
        (l) => nodeIndex.has(l.source) && nodeIndex.has(l.target)
      )
      .map((l) => ({
        source: nodeIndex.get(l.source)!,
        target: nodeIndex.get(l.target)!,
        value: l.value,
      }));

    if (sankeyLinks.length === 0) {
      return { nodes: [] as SNode[], links: [] as SLink[] };
    }

    const generator = sankey<{ id: string; label: string }, object>()
      .nodeWidth(12)
      .nodePadding(10)
      .nodeAlign((node) => {
        // Align by step number extracted from id
        const id = (node as unknown as { id: string }).id;
        return parseInt(id?.split(":")[0] ?? "0");
      })
      .extent([
        [16, 16],
        [width - 16, height - 16],
      ]);

    const result = generator({
      nodes: sankeyNodes,
      links: sankeyLinks,
    });

    return {
      nodes: result.nodes as SNode[],
      links: result.links as SLink[],
    };
  }, [data, height]);

  if (nodes.length === 0) {
    return (
      <div
        className="flex items-center justify-center text-sm text-muted-foreground"
        style={{ height }}
      >
        Not enough journey data for flow visualization
      </div>
    );
  }

  const pathGenerator = sankeyLinkHorizontal();

  return (
    <div className="w-full overflow-x-auto">
      <svg
        viewBox={`0 0 ${width} ${height}`}
        className="w-full"
        style={{ minWidth: 600, maxHeight: height }}
      >
        {/* Links */}
        <g>
          {links.map((link, i) => {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            const d = pathGenerator(link as any);
            if (!d) return null;
            const sourceNode = link.source as unknown as SNode;
            const stepIndex = parseInt(
              (sourceNode as unknown as { id: string }).id?.split(":")[0] ?? "0"
            );
            const color = CHART_COLORS[stepIndex % CHART_COLORS.length];
            return (
              <path
                key={i}
                d={d}
                fill="none"
                stroke={color}
                strokeOpacity={0.25}
                strokeWidth={Math.max((link as unknown as { width?: number }).width ?? 1, 1)}
              >
                <title>
                  {(sourceNode as unknown as { label: string }).label} →{" "}
                  {((link.target as unknown) as { label: string }).label}:{" "}
                  {formatNumber(link.value as number)}
                </title>
              </path>
            );
          })}
        </g>

        {/* Nodes */}
        <g>
          {nodes.map((node, i) => {
            const x0 = node.x0 ?? 0;
            const x1 = node.x1 ?? 0;
            const y0 = node.y0 ?? 0;
            const y1 = node.y1 ?? 0;
            const nodeHeight = y1 - y0;
            if (nodeHeight < 1) return null;

            const nodeData = node as unknown as { id: string; label: string };
            const stepIndex = parseInt(nodeData.id?.split(":")[0] ?? "0");
            const color = CHART_COLORS[stepIndex % CHART_COLORS.length];

            return (
              <g key={i}>
                <rect
                  x={x0}
                  y={y0}
                  width={x1 - x0}
                  height={nodeHeight}
                  fill={color}
                  opacity={0.8}
                  rx={2}
                >
                  <title>
                    {nodeData.label}: {formatNumber(node.value ?? 0)}
                  </title>
                </rect>
                {/* Label — show to the right of the node unless it's the last step */}
                {nodeHeight > 12 && (
                  <text
                    x={x1 + 6}
                    y={(y0 + y1) / 2}
                    dy="0.35em"
                    textAnchor="start"
                    fontSize={12}
                    fill="var(--color-foreground)"
                    className="pointer-events-none"
                  >
                    {nodeData.label.length > 28
                      ? `${nodeData.label.slice(0, 28)}...`
                      : nodeData.label}
                  </text>
                )}
              </g>
            );
          })}
        </g>

        {/* Step labels at top */}
        {(() => {
          const steps = new Set(
            nodes.map((n) =>
              parseInt(
                ((n as unknown as { id: string }).id ?? "0").split(":")[0]
              )
            )
          );
          return [...steps].sort().map((step) => {
            const stepNodes = nodes.filter(
              (n) =>
                parseInt(
                  ((n as unknown as { id: string }).id ?? "0").split(":")[0]
                ) === step
            );
            if (stepNodes.length === 0) return null;
            const avgX =
              stepNodes.reduce(
                (sum, n) => sum + ((n.x0 ?? 0) + (n.x1 ?? 0)) / 2,
                0
              ) / stepNodes.length;

            return (
              <text
                key={`step-${step}`}
                x={avgX}
                y={6}
                textAnchor="middle"
                fontSize={11}
                fontWeight={600}
                fill="var(--color-muted-foreground)"
              >
                Step {step + 1}
              </text>
            );
          });
        })()}
      </svg>
    </div>
  );
}
