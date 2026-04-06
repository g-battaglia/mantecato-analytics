from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from rich.text import Text
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Label, Static

from mantecato_core.database import create_pool, close_pool
from mantecato_core.filters import Filter

from mantecato_cli.config import get_database_url, get_default_site, get_default_period
from mantecato_cli.helpers import (
    resolve_site_id,
    parse_date_args,
    compute_derived_stats,
    num,
    format_duration,
    format_percent,
)


class Sparkline(Static):
    values: reactive[list[int]] = reactive([])

    BARS = "▁▂▃▄▅▆▇█"

    def watch_values(self, new: list[int]) -> None:
        if not new:
            self.update("")
            return
        max_v = max(new) if new else 1
        if max_v == 0:
            max_v = 1
        chars = []
        for v in new:
            idx = min(int((v / max_v) * (len(self.BARS) - 1)), len(self.BARS) - 1)
            chars.append(self.BARS[idx])
        self.update(Text("".join(chars), style="cyan"))


class MetricCard(Static):
    def __init__(self, label: str, value: str = "-", delta: str = "", **kwargs):
        super().__init__(**kwargs)
        self.label_text = label
        self.value_text = value
        self.delta_text = delta

    def compose(self) -> ComposeResult:
        yield Label(self.label_text, classes="metric-label")
        yield Label(self.value_text, classes="metric-value")
        if self.delta_text:
            yield Label(self.delta_text, classes="metric-delta")

    def update_metric(self, value: str, delta: str = "") -> None:
        try:
            value_label = self.query_one(".metric-value", Label)
            value_label.update(value)
            if delta:
                delta_label = self.query_one(".metric-delta", Label)
                style = (
                    "green"
                    if delta.startswith("+")
                    else "red"
                    if delta.startswith("-")
                    else "dim"
                )
                delta_label.update(Text(delta, style=style))
        except Exception:
            pass


class TopList(Static):
    def __init__(self, title: str, items: list[dict] | None = None, **kwargs):
        super().__init__(**kwargs)
        self.title_text = title
        self.items_data = items or []

    def compose(self) -> ComposeResult:
        yield Label(self.title_text, classes="list-title")
        for item in self.items_data[:8]:
            yield Label(self._format_item(item), classes="list-item")

    def update_items(
        self, items: list[dict], value_key: str = "visitors", label_key: str = ""
    ) -> None:
        try:
            for widget in self.query(".list-item"):
                widget.remove()
            for item in items[:8]:
                lbl = label_key or next(iter(item.keys()), "")
                val = item.get(value_key, 0)
                text = item.get(lbl, "-")
                self.mount(
                    Label(f"  {str(text):<40} {num(val):>8}", classes="list-item")
                )
        except Exception:
            pass

    def _format_item(self, item: dict) -> str:
        if not item:
            return ""
        keys = list(item.keys())
        if len(keys) >= 2:
            return f"  {str(item[keys[0]]):<40} {num(item[keys[1]]):>8}"
        return str(item)


class DashboardApp(App):
    CSS = """
    Screen {
        layout: vertical;
    }
    #overview {
        height: 6;
        border: solid cyan;
        padding: 1;
    }
    #metrics {
        height: 3;
    }
    MetricCard {
        width: 1fr;
        text-align: center;
    }
    .metric-label {
        text-style: dim;
    }
    .metric-value {
        text-style: bold;
    }
    .metric-delta {
        text-style: italic;
    }
    #traffic {
        height: 3;
        border: solid cyan;
        padding: 0 1;
    }
    #bottom {
        height: 1fr;
    }
    #pages-panel, #sources-panel {
        width: 1fr;
        border: solid cyan;
        padding: 0 1;
    }
    #events-panel {
        height: auto;
        border: solid cyan;
        padding: 0 1;
    }
    .list-title {
        text-style: bold cyan;
    }
    #status {
        height: 1;
        dock: bottom;
    }
    """

    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("p", "cycle_period", "Period"),
    ]

    site_name: reactive[str] = reactive("")
    period_name: reactive[str] = reactive("30d")
    auto_refresh: reactive[int] = reactive(60)

    PERIODS = ["1h", "24h", "7d", "30d", "90d", "this_month", "this_year"]
    _period_idx: int = 3

    def __init__(self, site: str | None = None, period: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._site_arg = site
        self._period_arg = period

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="overview"):
            yield Label("Overview", id="overview-title")
        with Horizontal(id="metrics"):
            yield MetricCard("Visitors")
            yield MetricCard("Pageviews")
            yield MetricCard("Bounce Rate")
            yield MetricCard("Avg Duration")
            yield MetricCard("Pages/Visit")
        with Horizontal(id="traffic"):
            yield Sparkline(id="sparkline")
        with Horizontal(id="bottom"):
            with Vertical(id="pages-panel"):
                yield TopList("Top Pages")
            with Vertical(id="sources-panel"):
                yield TopList("Top Sources")
        yield Label("Loading...", id="status")
        yield Footer()

    async def on_mount(self) -> None:
        if self._period_arg:
            self.period_name = self._period_arg
        else:
            self.period_name = get_default_period()

        self._period_idx = (
            self.PERIODS.index(self.period_name)
            if self.period_name in self.PERIODS
            else 3
        )

        db_url = get_database_url()
        if not db_url:
            self.query_one("#status", Label).update(
                "Error: DATABASE_URL not configured. Run: mantecato config set database.url ..."
            )
            return

        await create_pool(dsn=db_url)

        site = self._site_arg or get_default_site()
        if site:
            self.site_name = site
            try:
                self._site_id = await resolve_site_id(site)
            except SystemExit as e:
                self.query_one("#status", Label).update(str(e))
                return
        else:
            self.query_one("#status", Label).update(
                "Error: No site configured. Run: mantecato config set defaults.site ..."
            )
            return

        self.query_one("#overview-title", Label).update(
            f"Overview: {self.site_name} ({self.period_name})"
        )
        await self._refresh_data()
        self.set_interval(self.auto_refresh, self._refresh_data)

    async def action_refresh(self) -> None:
        await self._refresh_data()

    async def action_cycle_period(self) -> None:
        self._period_idx = (self._period_idx + 1) % len(self.PERIODS)
        self.period_name = self.PERIODS[self._period_idx]
        self.query_one("#overview-title", Label).update(
            f"Overview: {self.site_name} ({self.period_name})"
        )
        await self._refresh_data()

    async def _refresh_data(self) -> None:
        try:
            date_range = parse_date_args(self.period_name)
            filters: list[Filter] = []

            from mantecato_core.queries.stats import (
                get_website_stats,
                get_top_pages,
                get_top_referrers,
            )
            from mantecato_core.queries.stats import get_pageview_time_series
            from mantecato_core.date_utils import get_comparison_range

            prev_range = get_comparison_range(date_range, "previous_period")

            current_raw, previous_raw, pages, referrers, ts = await asyncio.gather(
                get_website_stats(
                    self._site_id, date_range.start_date, date_range.end_date, filters
                ),
                get_website_stats(
                    self._site_id, prev_range.start_date, prev_range.end_date, filters
                ),
                get_top_pages(
                    self._site_id,
                    date_range.start_date,
                    date_range.end_date,
                    8,
                    filters,
                ),
                get_top_referrers(
                    self._site_id,
                    date_range.start_date,
                    date_range.end_date,
                    8,
                    filters,
                ),
                get_pageview_time_series(
                    self._site_id,
                    date_range.start_date,
                    date_range.end_date,
                    "day",
                    filters,
                ),
                return_exceptions=True,
            )

            if isinstance(current_raw, Exception):
                self.query_one("#status", Label).update(f"Error: {current_raw}")
                return

            current = (
                compute_derived_stats(current_raw)
                if not isinstance(current_raw, Exception)
                else {}
            )
            previous = (
                compute_derived_stats(previous_raw)
                if not isinstance(previous_raw, Exception)
                else {}
            )

            def pct(cur, prev):
                if cur is None or prev is None or prev == 0:
                    if cur and prev == 0 and cur > 0:
                        return "+New"
                    return "-"
                change = ((cur - prev) / prev) * 100
                return f"+{change:.1f}%" if change >= 0 else f"{change:.1f}%"

            cards = self.query(MetricCard)
            metrics = [
                ("visitors", num),
                ("pageviews", num),
                ("bounce_rate", format_percent),
                ("avg_duration", format_duration),
                ("pages_per_visit", lambda v: f"{v:.1f}" if v else "-"),
            ]

            for card, (key, fmt) in zip(cards, metrics):
                cur = current.get(key)
                prev = previous.get(key)
                card.update_metric(fmt(cur), pct(cur, prev))

            if not isinstance(ts, Exception) and ts:
                sparkline = self.query_one("#sparkline", Sparkline)
                sparkline.values = [int(t.get("pageviews", 0) or 0) for t in ts]

            if not isinstance(pages, Exception):
                pages_panel = self.query("#pages-panel TopList").first()
                pages_panel.update_items(pages, "visitors", "url_path")

            if not isinstance(referrers, Exception):
                sources_panel = self.query("#sources-panel TopList").first()
                sources_panel.update_items(referrers, "visitors", "referrer_domain")

            self.query_one("#status", Label).update(
                f"Updated: {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')} | "
                f"Auto-refresh: {self.auto_refresh}s | [r]efresh [p]eriod [q]uit"
            )

        except Exception as e:
            self.query_one("#status", Label).update(f"Error: {e}")

    async def on_unmount(self) -> None:
        await close_pool()


def run_tui(site: str | None = None, period: str | None = None) -> None:
    app = DashboardApp(site=site, period=period)
    app.run()
