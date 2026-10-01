"""One-statement atomic folds for the hot path, after the durable event insert."""

from __future__ import annotations

from django.db import connection


def fold_visit(*, website_id, day, period, key, occurred_at, entry, threshold):
    # Expressions use the locked conflict row, not a Python read/modify/write.
    gap = "GREATEST(0, FLOOR(EXTRACT(EPOCH FROM EXCLUDED.last_seen - s.last_seen)))"
    new_visit = f"({gap} > 1800)"
    bounced = (
        "s.cur_visit_pageviews <= 1 AND "
        "(%s <= 0 OR s.cur_visit_duration_s + s.cur_page_engaged_s < %s)"
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"""INSERT INTO visitor_day_state AS s
          (id, website_id, day, period, visitor_key, entry_path, first_seen, last_seen,
           visits, bounces, cur_visit_pageviews, cur_visit_duration_s,
           cur_page_engaged_s, total_pageviews, total_duration_s)
          VALUES (gen_random_uuid(), %s::uuid, %s, %s, %s, %s, %s, %s,
                  1, 0, 1, 0, 0, 1, 0)
          ON CONFLICT (website_id, day, visitor_key) DO UPDATE SET
            visits = s.visits + CASE WHEN {new_visit} THEN 1 ELSE 0 END,
            bounces = s.bounces + CASE WHEN {new_visit} AND ({bounced}) THEN 1 ELSE 0 END,
            cur_visit_pageviews = CASE WHEN {new_visit} THEN 1 ELSE s.cur_visit_pageviews + 1 END,
            cur_visit_duration_s = CASE WHEN {new_visit} THEN 0 ELSE
              s.cur_visit_duration_s + CASE WHEN s.cur_page_engaged_s > 0
                THEN s.cur_page_engaged_s ELSE {gap}::integer END END,
            cur_page_engaged_s = 0,
            total_pageviews = s.total_pageviews + 1,
            total_duration_s = s.total_duration_s + CASE WHEN {new_visit}
              THEN s.cur_visit_duration_s + s.cur_page_engaged_s ELSE 0 END,
            entry_path = CASE WHEN {new_visit} THEN EXCLUDED.entry_path ELSE s.entry_path END,
            last_seen = EXCLUDED.last_seen""",
            [website_id, day, period, key, entry, occurred_at, occurred_at, threshold, threshold],
        )


def fold_engagement(*, website_id, day, key, occurred_at, seconds):
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE visitor_day_state SET
          cur_page_engaged_s = GREATEST(cur_page_engaged_s, %s),
          last_seen = GREATEST(last_seen, %s::timestamptz)
          WHERE website_id = %s::uuid AND day = %s AND visitor_key = %s
            AND last_seen >= %s::timestamptz - INTERVAL '30 minutes'
            AND (cur_page_engaged_s < %s OR last_seen < %s::timestamptz)""",
            [seconds, occurred_at, website_id, day, key, occurred_at, seconds, occurred_at],
        )
