# Frontend

`frontend/` — Vite 6 + React 19 SPA, TypeScript, Tailwind CSS 4.

## Stack

| Layer | Technology |
|-------|-----------|
| Build | Vite 6 |
| UI | React 19, shadcn/ui, Radix primitives |
| Styling | Tailwind CSS 4, glass theme support |
| Router | React Router 7 |
| State | Zustand |
| Data | TanStack Query 5 |
| Tables | TanStack Table + @tanstack/react-virtual |
| Charts | Recharts |
| Maps | react-simple-maps |
| Sankey | d3-sankey |
| Export | html2canvas, jspdf, xlsx |
| Icons | lucide-react |

## Running

```bash
cd frontend && npm run dev    # port 4180
```

## Route Structure

```
/login                          Login page
/dashboard                      Layout wrapper (auth guard)
/dashboard/home                 Landing
/dashboard/sites/:siteId/*      Site analytics pages
/dashboard/dashboards           Custom dashboards
/dashboard/settings             Site management, API keys, bot config
/share/:shareId                 Public shared view
```

## Dashboard Pages (15)

overview, pages, sources, events, sessions, devices, geo, realtime, compare, retention, funnels, journeys, revenue, engagement + custom dashboard builder

All in `src/pages/dashboard/sites/`.

## Component Organization

```
src/components/
  charts/      Recharts wrappers
  data/        Data tables
  filters/     Filter bar UI
  layout/      Sidebar, Header, GlassBackground
  ui/          shadcn/ui primitives
  overview/    Overview page sections
  annotations/ Annotation UI
  export/      PDF/PNG export
  dashboard/   Dashboard builder widgets
```

## Key Libraries

| File | Purpose |
|------|---------|
| `src/lib/api.ts` | `apiFetch()` — authenticated fetch wrapper |
| `src/lib/types.ts` | TypeScript data interfaces |
| `src/lib/format.ts` | Number, percent, duration formatting |
| `src/lib/theme.ts` | Theme provider (dark/light/glass) |
| `src/hooks/use-site-query.ts` | Centralized API query hook |
| `src/hooks/use-url-state.ts` | URL state sync (period, filters) |
| `src/stores/auth.ts` | Zustand auth store (token persistence) |
```
