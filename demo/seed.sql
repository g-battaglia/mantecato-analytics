-- Mantecato Demo: ACME Inc. sample data
-- Realistic analytics data for screenshots

-- ─── Schema (minimal Umami tables) ───

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS website (
  website_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  domain TEXT,
  share_id TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS session (
  session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  website_id UUID NOT NULL REFERENCES website(website_id),
  hostname TEXT,
  browser TEXT,
  os TEXT,
  device TEXT,
  screen TEXT,
  language TEXT,
  country TEXT,
  region TEXT,
  city TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS website_event (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  website_id UUID NOT NULL REFERENCES website(website_id),
  session_id UUID NOT NULL REFERENCES session(session_id),
  visit_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL,
  event_type INT NOT NULL DEFAULT 1, -- 1=pageview, 2=custom event
  event_name TEXT,
  url_path TEXT,
  page_title TEXT,
  referrer_domain TEXT,
  hostname TEXT DEFAULT 'acme-inc.com',
  utm_source TEXT,
  utm_medium TEXT,
  utm_campaign TEXT,
  utm_content TEXT,
  utm_term TEXT,
  tag TEXT
);

CREATE TABLE IF NOT EXISTS event_data (
  event_data_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  website_event_id UUID NOT NULL,
  website_id UUID NOT NULL,
  data_key TEXT NOT NULL,
  string_value TEXT,
  number_value NUMERIC,
  created_at TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS report (
  report_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL,
  website_id UUID,
  type TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  description TEXT NOT NULL DEFAULT '',
  parameters JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Umami stores user accounts here
CREATE TABLE IF NOT EXISTS umami_user (
  user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL, -- bcrypt hash
  role TEXT DEFAULT 'admin',
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Link users to websites
CREATE TABLE IF NOT EXISTS team (
  team_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS team_user (
  team_user_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES team(team_id),
  user_id UUID NOT NULL,
  role TEXT DEFAULT 'member',
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE TABLE IF NOT EXISTS team_website (
  team_website_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  team_id UUID NOT NULL REFERENCES team(team_id),
  website_id UUID NOT NULL REFERENCES website(website_id),
  created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for performance
CREATE INDEX IF NOT EXISTS idx_we_website_created ON website_event(website_id, created_at);
CREATE INDEX IF NOT EXISTS idx_we_session ON website_event(session_id);
CREATE INDEX IF NOT EXISTS idx_we_visit ON website_event(visit_id);
CREATE INDEX IF NOT EXISTS idx_session_website ON session(website_id);
CREATE INDEX IF NOT EXISTS idx_ed_event ON event_data(website_event_id);

-- ─── Demo Data ───

-- Admin user: demo / demo (bcrypt hash of "demo")
INSERT INTO umami_user (user_id, username, password, role) VALUES
  ('00000000-0000-0000-0000-000000000001', 'demo', '$2b$10$BUPcx7.NiT2F0wmaFcN4JODFKJmCx7R5K0BQZQ3YWqHhLXm3yVHi', 'admin');

-- Team
INSERT INTO team (team_id, name) VALUES
  ('00000000-0000-0000-0000-000000000010', 'ACME Team');
INSERT INTO team_user (team_id, user_id, role) VALUES
  ('00000000-0000-0000-0000-000000000010', '00000000-0000-0000-0000-000000000001', 'owner');

-- Website
INSERT INTO website (website_id, name, domain, share_id) VALUES
  ('aaaaaaaa-0000-0000-0000-000000000001', 'ACME Inc.', 'acme-inc.com', 'acme-public');
INSERT INTO team_website (team_id, website_id) VALUES
  ('00000000-0000-0000-0000-000000000010', 'aaaaaaaa-0000-0000-0000-000000000001');

-- ─── Generate sessions + events ───
-- We use generate_series + random() to create realistic traffic over the last 90 days.

DO $$
DECLARE
  site_id UUID := 'aaaaaaaa-0000-0000-0000-000000000001';
  sess_id UUID;
  visit_uuid UUID;
  ev_time TIMESTAMPTZ;
  pages TEXT[] := ARRAY[
    '/', '/products', '/products/rocket-launcher', '/products/anvil',
    '/products/giant-magnet', '/products/portable-hole', '/pricing',
    '/about', '/about/team', '/about/careers',
    '/blog', '/blog/how-to-catch-roadrunner', '/blog/best-desert-gadgets',
    '/blog/anvil-safety-guide', '/blog/rocket-science-101',
    '/docs', '/docs/getting-started', '/docs/api-reference',
    '/docs/tutorials', '/docs/faq',
    '/contact', '/signup', '/login', '/dashboard',
    '/case-studies', '/case-studies/coyote-corp', '/case-studies/desert-tech'
  ];
  titles TEXT[] := ARRAY[
    'ACME Inc. — Home', 'Products', 'Rocket Launcher', 'Anvil Pro',
    'Giant Magnet', 'Portable Hole', 'Pricing',
    'About Us', 'Our Team', 'Careers',
    'Blog', 'How to Catch a Roadrunner', 'Best Desert Gadgets 2026',
    'Anvil Safety Guide', 'Rocket Science 101',
    'Documentation', 'Getting Started', 'API Reference',
    'Tutorials', 'FAQ',
    'Contact', 'Sign Up', 'Login', 'Dashboard',
    'Case Studies', 'Coyote Corp', 'Desert Tech'
  ];
  referrers TEXT[] := ARRAY[
    NULL, NULL, NULL, NULL, NULL,  -- 5x direct (most common)
    'google.com', 'google.com', 'google.com', 'google.com',  -- 4x google
    'duckduckgo.com', 'duckduckgo.com',
    'bing.com', 'bing.com',
    'twitter.com', 'linkedin.com', 'reddit.com',
    'github.com', 'producthunt.com', 'hackernews.com',
    'facebook.com', 'youtube.com'
  ];
  browsers TEXT[] := ARRAY[
    'Chrome', 'Chrome', 'Chrome', 'Chrome', 'Chrome',  -- 50%
    'Safari', 'Safari', 'Safari',  -- 30%
    'Firefox', 'Edge'  -- 20%
  ];
  oses TEXT[] := ARRAY[
    'Windows', 'Windows', 'Windows',
    'Mac OS', 'Mac OS', 'Mac OS',
    'iOS', 'iOS',
    'Android', 'Linux'
  ];
  devices TEXT[] := ARRAY[
    'desktop', 'desktop', 'desktop', 'desktop', 'desktop',
    'desktop', 'desktop',
    'mobile', 'mobile', 'tablet'
  ];
  countries TEXT[] := ARRAY[
    'US', 'US', 'US', 'US',  -- 40%
    'GB', 'GB',  -- 20%
    'DE', 'DE',  -- 20%
    'FR', 'CA', 'AU', 'IT', 'ES', 'NL', 'JP', 'BR', 'IN', 'SG', 'SE', 'KR'
  ];
  regions_by_country JSONB := '{
    "US": ["California", "New York", "Texas", "Florida", "Washington", "Illinois", "Massachusetts"],
    "GB": ["England", "Scotland", "Wales"],
    "DE": ["Bavaria", "Berlin", "Hamburg", "Hesse"],
    "FR": ["Ile-de-France", "Provence", "Auvergne"],
    "CA": ["Ontario", "British Columbia", "Quebec"],
    "AU": ["New South Wales", "Victoria"],
    "IT": ["Lazio", "Lombardy", "Tuscany"],
    "JP": ["Tokyo", "Osaka"],
    "BR": ["Sao Paulo", "Rio de Janeiro"],
    "IN": ["Maharashtra", "Karnataka"]
  }';
  cities_map JSONB := '{
    "California": ["San Francisco", "Los Angeles", "San Jose"],
    "New York": ["New York City", "Brooklyn", "Buffalo"],
    "Texas": ["Austin", "Houston", "Dallas"],
    "England": ["London", "Manchester", "Bristol"],
    "Bavaria": ["Munich", "Nuremberg"],
    "Berlin": ["Berlin"],
    "Ile-de-France": ["Paris"],
    "Ontario": ["Toronto", "Ottawa"],
    "New South Wales": ["Sydney"],
    "Lazio": ["Rome"],
    "Tokyo": ["Tokyo"],
    "Sao Paulo": ["Sao Paulo"]
  }';
  events TEXT[] := ARRAY[
    'signup_click', 'signup_click', 'signup_click',
    'pricing_view', 'pricing_view',
    'demo_request', 'demo_request',
    'download_pdf', 'newsletter_subscribe',
    'contact_form', 'video_play', 'share_click'
  ];
  utm_sources TEXT[] := ARRAY[NULL, NULL, NULL, NULL, NULL, NULL,
    'google', 'google', 'twitter', 'linkedin', 'newsletter', 'producthunt'];
  utm_mediums TEXT[] := ARRAY[NULL, NULL, NULL, NULL, NULL, NULL,
    'cpc', 'organic', 'social', 'social', 'email', 'referral'];
  utm_campaigns TEXT[] := ARRAY[NULL, NULL, NULL, NULL, NULL, NULL,
    'spring-2026', 'brand', 'launch', 'b2b-outreach', 'weekly-digest', 'ph-launch'];
  languages TEXT[] := ARRAY[
    'en-US', 'en-US', 'en-US', 'en-GB', 'en-GB',
    'de-DE', 'de-DE', 'fr-FR', 'es-ES', 'ja-JP',
    'pt-BR', 'it-IT', 'nl-NL', 'ko-KR', 'sv-SE'
  ];
  screens TEXT[] := ARRAY[
    '1920x1080', '1920x1080', '1920x1080',
    '1440x900', '1440x900',
    '2560x1440', '1366x768',
    '390x844', '412x915', '768x1024'
  ];

  day_offset INT;
  hour_slot INT;
  sessions_today INT;
  pages_in_visit INT;
  page_idx INT;
  country_pick TEXT;
  region_pick TEXT;
  city_pick TEXT;
  region_arr JSONB;
  city_arr JSONB;
  i INT;
  j INT;
  ev_idx INT;
  utm_idx INT;
BEGIN
  -- Generate 90 days of data
  FOR day_offset IN 0..89 LOOP
    -- More traffic on weekdays, less on weekends
    IF EXTRACT(DOW FROM (now() - (day_offset || ' days')::interval)) IN (0, 6) THEN
      sessions_today := 30 + floor(random() * 20)::int;
    ELSE
      sessions_today := 60 + floor(random() * 40)::int;
    END IF;

    -- Recent days have more traffic (growth trend)
    IF day_offset < 14 THEN
      sessions_today := sessions_today + 20;
    ELSIF day_offset < 30 THEN
      sessions_today := sessions_today + 10;
    END IF;

    FOR i IN 1..sessions_today LOOP
      sess_id := gen_random_uuid();
      visit_uuid := gen_random_uuid();
      hour_slot := (CASE
        WHEN random() < 0.05 THEN floor(random() * 6)::int          -- 0-5 (night)
        WHEN random() < 0.4 THEN 8 + floor(random() * 4)::int       -- 8-11 (morning)
        WHEN random() < 0.7 THEN 12 + floor(random() * 5)::int      -- 12-16 (afternoon)
        ELSE 17 + floor(random() * 5)::int                           -- 17-21 (evening)
      END);
      ev_time := date_trunc('day', now()) - (day_offset || ' days')::interval
                 + (hour_slot || ' hours')::interval
                 + (floor(random() * 60) || ' minutes')::interval;

      -- Pick geo
      country_pick := countries[1 + floor(random() * array_length(countries, 1))::int];
      region_arr := regions_by_country->country_pick;
      IF region_arr IS NOT NULL AND jsonb_array_length(region_arr) > 0 THEN
        region_pick := region_arr->>floor(random() * jsonb_array_length(region_arr))::int;
      ELSE
        region_pick := NULL;
      END IF;
      city_arr := cities_map->region_pick;
      IF city_arr IS NOT NULL AND jsonb_array_length(city_arr) > 0 THEN
        city_pick := city_arr->>floor(random() * jsonb_array_length(city_arr))::int;
      ELSE
        city_pick := NULL;
      END IF;

      -- Create session
      INSERT INTO session (session_id, website_id, hostname, browser, os, device, screen, language, country, region, city, created_at)
      VALUES (
        sess_id, site_id, 'acme-inc.com',
        browsers[1 + floor(random() * array_length(browsers, 1))::int],
        oses[1 + floor(random() * array_length(oses, 1))::int],
        devices[1 + floor(random() * array_length(devices, 1))::int],
        screens[1 + floor(random() * array_length(screens, 1))::int],
        languages[1 + floor(random() * array_length(languages, 1))::int],
        country_pick, region_pick, city_pick, ev_time
      );

      -- Pageviews (1-6 pages per visit)
      pages_in_visit := 1 + floor(random() * 5)::int;
      utm_idx := 1 + floor(random() * array_length(utm_sources, 1))::int;

      FOR j IN 1..pages_in_visit LOOP
        page_idx := 1 + floor(random() * array_length(pages, 1))::int;
        INSERT INTO website_event (website_id, session_id, visit_id, created_at, event_type, url_path, page_title, referrer_domain, hostname, utm_source, utm_medium, utm_campaign)
        VALUES (
          site_id, sess_id, visit_uuid,
          ev_time + ((j - 1) * 15 + floor(random() * 30)) * interval '1 second',
          1, -- pageview
          pages[page_idx],
          titles[page_idx],
          CASE WHEN j = 1 THEN referrers[1 + floor(random() * array_length(referrers, 1))::int] ELSE NULL END,
          'acme-inc.com',
          CASE WHEN j = 1 THEN utm_sources[utm_idx] ELSE NULL END,
          CASE WHEN j = 1 THEN utm_mediums[utm_idx] ELSE NULL END,
          CASE WHEN j = 1 THEN utm_campaigns[utm_idx] ELSE NULL END
        );
      END LOOP;

      -- Custom events (30% of sessions)
      IF random() < 0.3 THEN
        ev_idx := 1 + floor(random() * array_length(events, 1))::int;
        INSERT INTO website_event (event_id, website_id, session_id, visit_id, created_at, event_type, event_name, url_path, hostname)
        VALUES (
          gen_random_uuid(), site_id, sess_id, visit_uuid,
          ev_time + (pages_in_visit * 20) * interval '1 second',
          2, -- custom event
          events[ev_idx],
          pages[1 + floor(random() * array_length(pages, 1))::int],
          'acme-inc.com'
        );

        -- Add event properties for some events
        IF events[ev_idx] = 'signup_click' THEN
          INSERT INTO event_data (website_event_id, website_id, data_key, string_value)
          VALUES (
            (SELECT event_id FROM website_event WHERE session_id = sess_id AND event_type = 2 ORDER BY created_at DESC LIMIT 1),
            site_id,
            'plan',
            (ARRAY['free', 'pro', 'enterprise'])[1 + floor(random() * 3)::int]
          );
        ELSIF events[ev_idx] = 'demo_request' THEN
          INSERT INTO event_data (website_event_id, website_id, data_key, string_value)
          VALUES (
            (SELECT event_id FROM website_event WHERE session_id = sess_id AND event_type = 2 ORDER BY created_at DESC LIMIT 1),
            site_id,
            'company_size',
            (ARRAY['1-10', '11-50', '51-200', '200+'])[1 + floor(random() * 4)::int]
          );
        END IF;
      END IF;

    END LOOP;
  END LOOP;

  RAISE NOTICE 'Demo data generated: 90 days of traffic for ACME Inc.';
END $$;
