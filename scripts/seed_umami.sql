-- ============================================================================
-- seed_umami.sql — Idempotent test data for Mantecato v3 development
-- Target: development-container container (Apple Container, NEVER production)
--
-- Usage:
--   container exec development-container psql -U postgres -d umami -f /dev/stdin < scripts/seed_umami.sql
--   container exec development-container psql -U postgres -d umami -c "\i /tmp/seed_umami.sql"
--
-- This script TRUNCATES all tables and re-inserts fresh test data.
-- Safe to run multiple times. NEVER run on production.
-- ============================================================================

BEGIN;

-- ---------------------------------------------------------------------------
-- Step 1: Truncate all tables (respecting FK order)
-- ---------------------------------------------------------------------------
TRUNCATE TABLE
    event_data,
    revenue,
    session_data,
    website_event,
    session,
    report,
    segment,
    team_user,
    website,
    team,
    "user"
CASCADE;

-- ---------------------------------------------------------------------------
-- Step 2: Base entities — team, users, team_user, websites
-- ---------------------------------------------------------------------------
INSERT INTO team (id, name, access_code, created_at, updated_at) VALUES
    ('a0000000-0000-0000-0000-000000000001', 'Mantecato Team', 'mtk-team-code', now(), now());

-- Password for ALL test users: "password"
-- bcrypt hash generated with bcrypt 4.x, cost 12
INSERT INTO "user" (id, username, password, role, created_at, updated_at) VALUES
    ('b0000000-0000-0000-0000-000000000001', 'admin',
     '$2b$12$.OuBviLQsP4n5NJDfmrigO21L7hjcOo6rKS8hlT9eeQsNp9TDL0LS',
     'admin', '2025-01-15 10:00:00+00', '2025-01-15 10:00:00+00'),
    ('b0000000-0000-0000-0000-000000000002', 'analyst',
     '$2b$12$.OuBviLQsP4n5NJDfmrigO21L7hjcOo6rKS8hlT9eeQsNp9TDL0LS',
     'user', '2025-02-01 09:00:00+00', '2025-02-01 09:00:00+00'),
    ('b0000000-0000-0000-0000-000000000003', 'viewer',
     '$2b$12$.OuBviLQsP4n5NJDfmrigO21L7hjcOo6rKS8hlT9eeQsNp9TDL0LS',
     'view-only', '2025-03-01 11:00:00+00', '2025-03-01 11:00:00+00');

INSERT INTO team_user (team_user_id, team_id, user_id, role, created_at) VALUES
    ('c0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001',
     'b0000000-0000-0000-0000-000000000001', 'owner', now()),
    ('c0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001',
     'b0000000-0000-0000-0000-000000000002', 'member', now()),
    ('c0000000-0000-0000-0000-000000000003', 'a0000000-0000-0000-0000-000000000001',
     'b0000000-0000-0000-0000-000000000003', 'member', now());

INSERT INTO website (id, name, domain, user_id, team_id, created_at, is_deleted) VALUES
    ('d0000000-0000-0000-0000-000000000001', 'Mantecato Docs', 'docs.mantecato.io',
     'b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001',
     '2025-01-15 10:00:00+00', false),
    ('d0000000-0000-0000-0000-000000000002', 'Mantecato Blog', 'blog.mantecato.io',
     'b0000000-0000-0000-0000-000000000001', 'a0000000-0000-0000-0000-000000000001',
     '2025-02-01 09:00:00+00', false),
    ('d0000000-0000-0000-0000-000000000003', 'Client Portal', 'app.example.com',
     'b0000000-0000-0000-0000-000000000002', 'a0000000-0000-0000-0000-000000000001',
     '2025-03-01 11:00:00+00', false);

-- ---------------------------------------------------------------------------
-- Step 3: Sessions — 600 sessions over 60 days
--   Distribution: 60% docs, 25% blog, 15% app
--   Time decay: more sessions in recent days (exponential bias)
-- ---------------------------------------------------------------------------
INSERT INTO session (
    session_id, website_id, browser, os, device, screen, language,
    country, region, city, distinct_id, created_at
)
SELECT
    gen_random_uuid(),
    (ARRAY[
        'd0000000-0000-0000-0000-000000000001'::uuid,
        'd0000000-0000-0000-0000-000000000002'::uuid,
        'd0000000-0000-0000-0000-000000000003'::uuid
    ])[CASE
        WHEN random() < 0.60 THEN 1
        WHEN random() < 0.85 THEN 2
        ELSE 3
    END],
    -- Real Umami stores geo/device on `session` only (not website_event), with
    -- detect-browser / ua-parser-js vocabulary: os like 'macOS'/'Windows 10/11',
    -- device lowercase incl. 'laptop'. The importer normalises these onto
    -- Mantecato's live tracker vocabulary.
    (ARRAY['Chrome','Chrome','Chrome','Firefox','Safari','Edge'])[floor(random()*6+1)::int],
    (ARRAY['Windows 10/11','macOS','macOS','Linux','Android','iOS'])[floor(random()*6+1)::int],
    CASE WHEN random() < 0.45 THEN 'desktop'
         WHEN random() < 0.60 THEN 'laptop'
         WHEN random() < 0.85 THEN 'mobile'
         ELSE 'tablet' END,
    (ARRAY['1920x1080','1440x900','2560x1440','1366x768','390x844','768x1024'])
        [floor(random()*6+1)::int],
    (ARRAY['en-US','en-GB','it-IT','de-DE','fr-FR','es-ES','ja','pt-BR'])
        [floor(random()*8+1)::int],
    (ARRAY['IT','US','US','US','DE','FR','GB','ES','JP','BR','NL','CA','AU','IN'])
        [floor(random()*14+1)::int],
    (ARRAY['Lazio','California','New York','Texas','Bavaria','Ile-de-France',
               'England','Madrid','Tokyo','Sao Paulo','Noord-Holland','Ontario',
               'New South Wales','Maharashtra'])
        [floor(random()*14+1)::int],
    (ARRAY['Rome','San Francisco','New York','Austin','Munich','Paris',
               'London','Madrid','Tokyo','Sao Paulo','Amsterdam','Toronto',
               'Sydney','Mumbai'])
        [floor(random()*14+1)::int],
    'user_' || (i % 180 + 1)::text,
    now() - (60 - (60 * pow(random(), 1.5)))::int * interval '1 day'
           - (random() * 86400)::int * interval '1 second'
FROM generate_series(1, 600) AS s(i);

-- ---------------------------------------------------------------------------
-- Step 4: Pageviews (event_type=1) — 5 per session on average = 3000
--   Each session gets 2-8 pageviews, spaced 10s-5min apart
-- ---------------------------------------------------------------------------
-- NB: real Umami `website_event` has NO geo/device columns — they live on
-- `session` and the importer LEFT JOINs to pull them.
INSERT INTO website_event (
    event_id, website_id, session_id, visit_id, created_at,
    url_path, url_query, referrer_path, referrer_query, referrer_domain,
    page_title, event_type, event_name, tag, hostname,
    utm_source, utm_medium, utm_campaign, utm_content, utm_term
)
SELECT
    gen_random_uuid(),
    s.website_id,
    s.session_id,
    gen_random_uuid() AS visit_id,
    s.created_at + (row_number() OVER (PARTITION BY s.session_id ORDER BY pv.n)
        * (10 + floor(random()*290))::int * interval '1 second') AS created_at,
    (ARRAY[
        '/', '/docs/getting-started', '/docs/api-reference', '/docs/installation',
        '/docs/configuration', '/pricing', '/about', '/contact', '/changelog',
        '/blog/2025-announcements', '/blog/performance-tips', '/blog/release-v3',
        '/docs/queries/overview', '/docs/queries/sessions', '/features',
        '/docs/deployment', '/docs/authentication', '/blog', '/docs',
        '/app/dashboard', '/app/analytics', '/app/settings'
    ])[floor(random()*22+1)::int],
    CASE WHEN random() < 0.15 THEN 'ref=sidebar' ELSE NULL END,
    CASE WHEN random() < 0.3 THEN '/' ELSE NULL END,
    NULL,
    (ARRAY[
        'google.com', 'google.com', 'google.com',
        'twitter.com', 'linkedin.com', 'github.com',
        'facebook.com', 'reddit.com', NULL, NULL, NULL, NULL
    ])[floor(random()*12+1)::int],
    (ARRAY[
        'Getting Started', 'API Reference', 'Installation Guide',
        'Configuration', 'Pricing', 'About Us', 'Contact', 'Changelog',
        'Announcements', 'Performance Tips', 'Release v3',
        'Queries Overview', 'Sessions Queries', 'Features',
        'Deployment', 'Authentication', 'Blog', 'Documentation',
        'Dashboard', 'Analytics', 'Settings'
    ])[floor(random()*21+1)::int],
    1,
    NULL,
    NULL,
    CASE s.website_id
        WHEN 'd0000000-0000-0000-0000-000000000001'::uuid THEN 'docs.mantecato.io'
        WHEN 'd0000000-0000-0000-0000-000000000002'::uuid THEN 'blog.mantecato.io'
        ELSE 'app.example.com' END,
    CASE WHEN random() < 0.12 THEN 'google' ELSE NULL END,
    CASE WHEN random() < 0.12 THEN 'cpc'
         WHEN random() < 0.06 THEN 'social' ELSE NULL END,
    CASE WHEN random() < 0.08 THEN 'brand_launch_2025'
         WHEN random() < 0.04 THEN 'docs_update' ELSE NULL END,
    NULL,
    NULL
FROM session s
CROSS JOIN LATERAL generate_series(1, 2 + floor(random()*7)::int) AS pv(n);

-- ---------------------------------------------------------------------------
-- Step 5: Custom events (event_type=2) — ~300 events
--   signup, purchase, newsletter, download, button_click, search
-- ---------------------------------------------------------------------------
INSERT INTO website_event (
    event_id, website_id, session_id, visit_id, created_at,
    url_path, url_query, referrer_path, referrer_query, referrer_domain,
    page_title, event_type, event_name, tag, hostname,
    utm_source, utm_medium, utm_campaign, utm_content, utm_term
)
SELECT
    gen_random_uuid(),
    s.website_id,
    s.session_id,
    gen_random_uuid(),
    s.created_at + (random() * 600)::int * interval '1 second',
    (ARRAY['/pricing', '/app/dashboard', '/docs/getting-started', '/about', '/app/analytics'])
        [floor(random()*5+1)::int],
    NULL, NULL, NULL, NULL,
    NULL,
    2,
    (ARRAY['signup', 'purchase', 'newsletter', 'download', 'button_click', 'search'])
        [floor(random()*6+1)::int],
    CASE WHEN random() < 0.3 THEN 'conversion' ELSE NULL END,
    CASE s.website_id
        WHEN 'd0000000-0000-0000-0000-000000000001'::uuid THEN 'docs.mantecato.io'
        WHEN 'd0000000-0000-0000-0000-000000000002'::uuid THEN 'blog.mantecato.io'
        ELSE 'app.example.com' END,
    NULL, NULL, NULL, NULL, NULL
FROM session s
WHERE random() < 0.50
LIMIT 300;

-- ---------------------------------------------------------------------------
-- Step 6: Event data — properties for custom events
-- ---------------------------------------------------------------------------
INSERT INTO event_data (
    event_data_id, website_id, website_event_id,
    data_key, string_value, number_value, date_value, data_type, created_at
)
SELECT
    gen_random_uuid(),
    ev.website_id,
    ev.event_id,
    (ARRAY['plan', 'amount', 'currency', 'source', 'query', 'category'])
        [floor(random()*6+1)::int],
    (ARRAY['pro', 'starter', 'enterprise', 'free', 'organic', 'paid', 'docs'])
        [floor(random()*7+1)::int],
    CASE WHEN random() < 0.4 THEN (random() * 500)::numeric(10,2) ELSE NULL END,
    NULL,
    CASE WHEN random() < 0.6 THEN 1 ELSE 2 END,
    ev.created_at
FROM website_event ev
WHERE ev.event_type = 2
  AND random() < 0.65;

-- ---------------------------------------------------------------------------
-- Step 7: Revenue — ~80 entries tied to purchase events
-- ---------------------------------------------------------------------------
INSERT INTO revenue (
    revenue_id, website_id, session_id, event_id, event_name,
    revenue, currency, created_at
)
SELECT
    gen_random_uuid(),
    ev.website_id,
    ev.session_id,
    ev.event_id,
    'purchase',
    (ARRAY[9.99, 29.99, 49.99, 99.00, 199.00, 499.00])
        [floor(random()*6+1)::int]::numeric,
    (ARRAY['EUR','USD','USD','USD','GBP','JPY'])[floor(random()*6+1)::int],
    ev.created_at
FROM website_event ev
WHERE ev.event_name = 'purchase'
  AND random() < 0.75;

-- ---------------------------------------------------------------------------
-- Step 8: Reports — dashboards, saved views, annotations, API keys
-- ---------------------------------------------------------------------------
INSERT INTO report (id, user_id, website_id, name, type, description, parameters, created_at, updated_at) VALUES
    ('e0000000-0000-0000-0000-000000000001',
     'b0000000-0000-0000-0000-000000000001',
     'd0000000-0000-0000-0000-000000000001',
     'Main Dashboard', 'mantecato-dashboard',
     'Primary analytics dashboard',
     '{"widgets": ["overview", "top-pages", "sources", "geo-map"], "layout": "grid"}'::jsonb,
     now() - interval '30 days', now()),

    ('e0000000-0000-0000-0000-000000000002',
     'b0000000-0000-0000-0000-000000000001',
     'd0000000-0000-0000-0000-000000000002',
     'Blog Performance', 'mantecato-dashboard',
     'Blog content analytics',
     '{"widgets": ["overview", "top-pages", "referrers"], "layout": "grid"}'::jsonb,
     now() - interval '15 days', now()),

    ('e0000000-0000-0000-0000-000000000003',
     'b0000000-0000-0000-0000-000000000002',
     'd0000000-0000-0000-0000-000000000001',
     'Weekly comparison', 'mantecato-saved-view',
     'Compare this week vs last week',
     '{"period": "7d", "compare": true, "filters": {}}'::jsonb,
     now() - interval '10 days', now()),

    ('e0000000-0000-0000-0000-000000000004',
     'b0000000-0000-0000-0000-000000000001',
     'd0000000-0000-0000-0000-000000000001',
     'v3 launch spike', 'mantecato-annotation',
     'Traffic spike from v3 announcement',
     '{"date": "2025-04-15", "color": "#4F46E5"}'::jsonb,
     now() - interval '20 days', now()),

    ('e0000000-0000-0000-0000-000000000005',
     'b0000000-0000-0000-0000-000000000001',
     NULL,
     'CLI key', 'api-key',
     'API key for CLI access',
     '{"hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000", "scopes": ["read"]}'::jsonb,
     now() - interval '5 days', now()),

    ('e0000000-0000-0000-0000-000000000006',
     'b0000000-0000-0000-0000-000000000001',
     'd0000000-0000-0000-0000-000000000001',
     'Default bot config', 'mantecato-bot-config',
     'Bot detection rules',
     '{"patterns": ["bot", "crawler", "spider"], "exclude_user_agents": ["Googlebot"]}'::jsonb,
     now() - interval '25 days', now()),

    ('e0000000-0000-0000-0000-000000000007',
     'b0000000-0000-0000-0000-000000000002',
     'd0000000-0000-0000-0000-000000000003',
     'Monthly export', 'mantecato-scheduled-export',
     'Monthly PDF report',
     '{"format": "pdf", "recurrence": "monthly", "email": "analyst@example.com"}'::jsonb,
     now() - interval '7 days', now());

-- ---------------------------------------------------------------------------
-- Step 9: Segments — saved filter groups
-- ---------------------------------------------------------------------------
INSERT INTO segment (id, website_id, name, type, name_filters, modifier, created_at, updated_at) VALUES
    ('f0000000-0000-0000-0000-000000000001',
     'd0000000-0000-0000-0000-000000000001',
     'Mobile users', 'session',
     '{"filters": [{"column": "device", "operator": "eq", "value": "mobile"}]}'::jsonb,
     'include',
     now() - interval '20 days', now()),
    ('f0000000-0000-0000-0000-000000000002',
     'd0000000-0000-0000-0000-000000000001',
     'EU traffic', 'session',
     '{"filters": [{"column": "country", "operator": "in", "value": ["IT","DE","FR","ES","NL","GB"]}]}'::jsonb,
     'include',
     now() - interval '15 days', now());

-- ---------------------------------------------------------------------------
-- Step 10: Session data — custom properties for some sessions
-- ---------------------------------------------------------------------------
INSERT INTO session_data (
    session_data_id, website_id, session_id,
    data_key, string_value, number_value, date_value, data_type,
    distinct_id, created_at
)
SELECT
    gen_random_uuid(),
    s.website_id,
    s.session_id,
    (ARRAY['subscription', 'company_size', 'industry', 'ab_test_variant'])
        [floor(random()*4+1)::int],
    (ARRAY['free', 'pro', 'enterprise', 'startup', 'smb', 'tech', 'finance'])
        [floor(random()*7+1)::int],
    CASE WHEN random() < 0.3 THEN floor(random()*1000)::numeric ELSE NULL END,
    NULL,
    1,
    s.distinct_id,
    s.created_at
FROM session s
WHERE random() < 0.15;

COMMIT;

-- ---------------------------------------------------------------------------
-- Verification counts
-- ---------------------------------------------------------------------------
SELECT '=== Seed verification ===' AS info;

SELECT 'website' AS tbl, count(*) FROM website
UNION ALL SELECT '"user"', count(*) FROM "user"
UNION ALL SELECT 'team', count(*) FROM team
UNION ALL SELECT 'team_user', count(*) FROM team_user
UNION ALL SELECT 'session', count(*) FROM session
UNION ALL SELECT 'website_event', count(*) FROM website_event
UNION ALL SELECT 'event_data', count(*) FROM event_data
UNION ALL SELECT 'report', count(*) FROM report
UNION ALL SELECT 'revenue', count(*) FROM revenue
UNION ALL SELECT 'segment', count(*) FROM segment
UNION ALL SELECT 'session_data', count(*) FROM session_data
ORDER BY 1;
