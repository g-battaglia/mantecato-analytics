# Report: v4/next rispetto a main

Data analisi originale: 2026-06-07 · Aggiornamento bonifica: 2026-06-08

---

## Aggiornamento 2026-06-08 — stato post-bonifica

La diagnostica più sotto (2026-06-07) fotografava una branch "a metà": modello dati
privacy-first già rimosso, ma contratti pubblici (API, CLI, tracker, client, test)
ancora legati alle feature eliminate. Da allora la riscrittura è stata completata e
l'ecosistema riallineato. Stato attuale verificato:

### Verifiche finali (tutte verdi)

- `manage.py check` → 0 issue (solo il warning voluto su `ALLOWED_HOSTS='*'`).
- `makemigrations --check --dry-run` → **No changes detected** (migration 0012 allineata ai model).
- Suite Python `pytest tests/` su Postgres → **815 passed, 27 skipped, 0 failed**
  (i 27 skip sono i test "live DB" che richiedono un DB di sviluppo seedato su localhost).
- Test SDK Python (`packages/mantecato-client`, con extra `dev`) → **38 passed**.
- Test JS → `@mantecato/tracker` **12/12**, `@mantecato/tracker-react` **4/4**.
- Build tracker (`npm run build`) → ok, `dist/` riproducibile e allineata ai sorgenti.
- Smoke end-to-end di tutte le route web su Postgres vuoto (nuovo `tests/test_route_smoke.py`):
  `/`, `/pages`, `/sections`, `/events`, `/devices`, `/geo`, `/compare`, `/heatmap`,
  `/realtime` (+ partial e overview tabs) → **14/14 a 200**.

Punto di partenza di questa sessione: 175 failure nella suite Python. Tutti risolti
aggiornando i test alle nuove shape/firme privacy-first ed eliminando i test delle
feature rimosse (sources, sessions, retention, funnels, journeys, revenue, engagement).

### Bug reali di prodotto trovati e corretti

Due bug che mandavano in 500 / rendevano vuota la UI, scoperti durante la verifica route:

1. `templates/analytics/_overview_bottom.html` usava `{% view_query %}` senza
   `{% load fmt %}` (il `{% load %}` non si propaga ai template inclusi) → la pagina
   Overview andava in 500. Corretto: `{% load i18n fmt %}`.
2. `templates/analytics/_realtime_data.html` leggeva `active.count`, ma il contesto
   (da `get_overview_data`) fornisce `realtime` → la card "Active Pageviews" restava
   sempre vuota. Corretto in `realtime.count`.

### Stato dei finding originali

- #1 Migration incomplete → **risolto** (`makemigrations --check` pulito; 0012 presente).
- #2 Query engine svuotato con chiamanti vivi → **parziale**: query engine ripulito e
  coerente, **ma la CLI resta legacy** (vedi follow-up sotto).
- #3 API espone endpoint rimossi → **risolto** (solo overview/pages/events/devices/geo/
  compare/realtime risolvono; gli altri non esistono più).
- #4 Tracker JS rompe l'API documentata → **risolto** (test JS verdi, README aggiornati).
- #5 Filtri UI / bot filter incoerenti → **risolto**: bot filter ora event-level reale
  (`bot_reason` + paesi esclusi), non più no-op; filtri allineati alla whitelist.
- #6 Import Umami copia tabelle rimosse → **risolto** (servizi import aggiornati).
- #7 Test suite inaffidabile → **risolto** (suite verde; SDK e JS verdi).
- Secondari (SDK, types, docstring) → **risolti** (SDK espone solo i metodi superstiti;
  test SDK riscritti; docs senza riferimenti legacy residui).

### Follow-up aperto: bonifica CLI (non incluso in questa sessione)

La CLI (`cli/mantecato_cli/commands/analytics.py` e `queries.py`) espone ancora ~19
comandi per feature rimosse (`sources`, `sessions`, `retention`, `funnels`, `journeys`,
`revenue`, `engagement`, `top-referrers`, `top-events`, `next-pages`, `page-referrers`,
`event-properties`, `session-activity`, `channels`, `utm`, `clickids`, `hostnames`,
`referrer-pages`). Hanno import lazy, quindi **non rompono la suite di test**, ma
**crashano in `ImportError` a runtime quando invocati**. La CLI non è stata toccata dal
refactor privacy-first. Bonificarla è un intervento a sé:

- rimuovere i comandi morti (o trasformarli in stub che spiegano la rimozione);
- abbassare l'asserzione `assert len(app.registered_commands) >= 45` in
  `tests/test_cli.py` (oggi i comandi sono 46; rimuovendo i morti scendono a ~27).

È una scelta di prodotto (eliminare vs stub) e cambia la superficie CLI, quindi lasciata
alla conferma esplicita prima di procedere.

### Commit/push

Non ancora eseguiti: in attesa di conferma. Tutte le modifiche sono nel working tree di
`v4/next`.

---

## Diagnostica originale (2026-06-07)

Data analisi: 2026-06-07

## Sintesi

`v4/next` non ha un merge-base con `main`, quindi il confronto utile e' tra i due tree (`git diff main v4/next`). Il diff e' molto ampio: 57 file modificati, circa 1.141 righe aggiunte e 9.469 righe rimosse.

La branch non sembra una normale evoluzione incrementale di `main`: e' una riscrittura "privacy-first aggregate-only" che rimuove sessioni, eventi custom, referrer, UTM, revenue, funnel, journey, retention e gran parte del query engine. Il problema principale non e' solo la rimozione: l'ecosistema attorno non e' stato aggiornato in modo coerente. Restano API, CLI, template, documentazione, test e client che promettono o chiamano funzioni non piu' esistenti, oppure ricevono risposte vuote.

## Verifiche eseguite

- `git diff --stat main v4/next`
  - 57 file cambiati
  - 1.141 insertions
  - 9.469 deletions
- `env SECRET_KEY=test uv run --no-sync python manage.py check`
  - Passa, con warning su `ALLOWED_HOSTS='*'`.
- `env SECRET_KEY=test uv run --no-sync python manage.py makemigrations --check --dry-run`
  - Fallisce: Django vuole generare `0012_remove_websiteevent_idx_we_session_id_and_more.py`.
  - Indica migration non sincronizzate con i model.
- `env SECRET_KEY=test uv run --no-sync pytest -q`
  - Fallisce in collection per `ImportPathMismatchError` tra `tests/conftest.py` e `packages/mantecato-client/tests/conftest.py`.
- `env SECRET_KEY=test uv run --no-sync pytest tests -q`
  - 793 passed, 106 failed, 60 errors, 71 skipped.
  - Molti failure sono aspettative su pagine/funzioni rimosse.
  - Gli errori DB partono da migration SQL PostgreSQL-only eseguita su SQLite (`ALTER TABLE ... ALTER COLUMN ... SET DEFAULT now()`), che va separata dalle regressioni v4.
- `env SECRET_KEY=test uv run --no-sync pytest packages/mantecato-client/tests -q --import-mode=importlib`
  - Non parte: manca `httpx`.
- `npm test`
  - `@mantecato/tracker`: 16 failed / 50.
  - `@mantecato/tracker-react`: 1 failed / 4.
- `npm run build`
  - Passa.

## Evidenze dagli screenshot

Screenshot: `/Users/giacomo/Desktop/Screenshot 2026-06-07 alle 23.38.34.png`

L'overview attesa mostra 6 KPI box:

- Pageviews
- Visitors
- Visits
- Bounce Rate
- Avg Duration
- Pages / Visit

In `v4/next` il template sarebbe ancora capace di renderizzarli se `stats` li contenesse:

- `templates/analytics/_overview_metrics.html:4`
- `templates/analytics/_overview_metrics.html:8`
- `templates/analytics/_overview_metrics.html:9`
- `templates/analytics/_overview_metrics.html:10`
- `templates/analytics/_overview_metrics.html:11`
- `templates/analytics/_overview_metrics.html:12`
- `templates/analytics/_overview_metrics.html:13`

Il taglio reale avviene nel service: `_stats_with_change()` ora ritorna solo `pageviews`.

- `apps/analytics/services.py:46`
- `apps/analytics/services.py:52`

E il query engine dichiara esplicitamente di non calcolare piu' visitor, session, bounce e time-on-site.

- `core/mantecato_core/queries/stats.py:3`
- `core/mantecato_core/queries/stats.py:64`

Quindi i box mancanti non sono un semplice problema grafico: i dati non vengono piu' prodotti.

Screenshot: `/Users/giacomo/Desktop/Screenshot 2026-06-07 alle 23.39.06.png`

La sidebar attesa contiene queste voci:

- Analytics: Overview, Pages, Sections, Sources, Events, Sessions, Devices, Geo, Engagement, Compare, Realtime
- Advanced: Retention, Funnels, Journeys, Revenue
- Dashboards

In `v4/next`, `templates/base.html` espone solo:

- Overview
- Pages
- Sections
- Devices
- Geo
- Compare
- Heatmap
- Realtime
- Dashboards

Riferimenti:

- `templates/base.html:138`
- `templates/base.html:140`
- `templates/base.html:142`
- `templates/base.html:144`
- `templates/base.html:146`
- `templates/base.html:148`
- `templates/base.html:150`
- `templates/base.html:152`
- `templates/base.html:157`

Le voci mancanti sono state rimosse insieme alle rotte web:

- `apps/analytics/urls.py:3`
- `apps/analytics/urls.py:31`

Questo conferma il problema centrale: `v4/next` non ha solo bug locali, ha eliminato parti importanti della superficie prodotto visibile in `main`.

## Findings critici

### 1. Migration schema distruttiva e incompleta

`apps/core/migrations/0010_privacy_first_aggregate_only.py` elimina tabelle e colonne centrali:

- `Segment`, `Revenue`, `SessionData`, `EventData`, `Session`
- `website_event.session_id`, `visit_id`, `referrer_*`, `event_name`, `tag`, `screen`, `language`, `utm_*`, click IDs

Riferimenti:

- `apps/core/migrations/0010_privacy_first_aggregate_only.py:21`
- `apps/core/migrations/0010_privacy_first_aggregate_only.py:23`
- `apps/core/migrations/0010_privacy_first_aggregate_only.py:29`
- `apps/core/migrations/0010_privacy_first_aggregate_only.py:38`

Impatto:

- Perdita dati irreversibile per sessioni, eventi custom, revenue, attribution e segmenti.
- Upgrade da `main` rompe la semantica del prodotto.
- Non c'e' una strategia di migrazione dati o compatibilita.

In piu', le migration sono incoerenti con i model correnti. `makemigrations --check --dry-run` richiede una migration 0012 per rimuovere indici vecchi (`idx_we_session_id`, `idx_we_visit_id`, `idx_we_event_hot`, ecc.) e ricreare `idx_we_pageview_hot`. Questo e' un problema bloccante per CI/deploy.

### 2. Query engine svuotato ma chiamanti ancora vivi

Diversi moduli del query engine sono ridotti a solo docstring/stub:

- `core/mantecato_core/queries/events.py:1`
- `core/mantecato_core/queries/sessions.py:1`
- `core/mantecato_core/queries/sources.py:1`
- `core/mantecato_core/queries/revenue.py:1`

Pero' la CLI importa ancora funzioni da quei moduli:

- `cli/mantecato_cli/commands/queries.py:129` importa `get_top_referrers`
- `cli/mantecato_cli/commands/queries.py:149` importa `get_top_events`
- `cli/mantecato_cli/commands/queries.py:170` importa `get_next_pages`, `get_page_referrers`, `get_time_on_page_distribution`
- `cli/mantecato_cli/commands/queries.py:238` importa `get_event_properties`, `get_event_time_series`
- `cli/mantecato_cli/commands/queries.py:307` importa `get_session_activity`
- `cli/mantecato_cli/commands/queries.py:321` importa `get_channel_metrics`

Impatto:

- Comandi CLI esistenti falliscono a runtime con `ImportError`.
- L'interfaccia pubblica del query engine non e' stata deprecata, e' stata spezzata.

### 3. Web UI ridotta, ma API pubblica ancora espone endpoint rimossi

Le rotte web rimuovono pagine come sources, events, sessions, retention, funnels, journeys, revenue, engagement:

- `apps/analytics/urls.py:3`
- `apps/analytics/urls.py:31`

Ma le API JSON continuano a pubblicare endpoint per quelle feature:

- `apps/api/urls.py:42` sources
- `apps/api/urls.py:43` events
- `apps/api/urls.py:44` sessions
- `apps/api/urls.py:48` retention
- `apps/api/urls.py:49` funnels
- `apps/api/urls.py:50` journeys
- `apps/api/urls.py:51` revenue
- `apps/api/urls.py:52` engagement

E i service dietro quegli endpoint tornano dati vuoti:

- `apps/analytics/services.py:299` sessions
- `apps/analytics/services.py:303` events
- `apps/analytics/services.py:307` sources
- `apps/analytics/services.py:311` retention
- `apps/analytics/services.py:315` funnels
- `apps/analytics/services.py:319` journeys
- `apps/analytics/services.py:323` revenue
- `apps/analytics/services.py:327` engagement

Impatto:

- Client API ricevono `200 OK` con dati vuoti invece di un errore esplicito.
- Questo maschera regressioni e puo' far sembrare che un sito non abbia dati.
- Contratto API incompatibile con `main` ma senza versioning.

### 4. Tracker JS rompe la API pubblica documentata

In `main`, il tracker esponeva `event`, `revenue`, `send`, `identify`, `track(name, data)`, cache token e payload con `screen`, `language`, `referrer`. In `v4/next`, `Tracker` contiene solo `pageview`, `track`, `enable`, `disable`, `isEnabled`, `destroy`:

- `packages/tracker/src/tracker.ts:69`
- `packages/tracker/src/tracker.ts:281`

Il README continua pero' a documentare feature rimosse:

- `packages/tracker/README.md:7` revenue tracking
- `packages/tracker/README.md:9` sessioni via `x-umami-cache`
- `packages/tracker/README.md:10` identify
- `packages/tracker/README.md:43` data-umami-event
- `packages/tracker/README.md:106` pageview con referrer
- `packages/tracker/README.md:107` custom event
- `packages/tracker/README.md:108` revenue
- `packages/tracker/README.md:109` identify
- `packages/tracker/README.md:210` compatibilita Umami

`npm test` conferma la rottura:

- `@mantecato/tracker`: 16 test falliti su 50.
- `@mantecato/tracker-react`: 1 test fallito su 4.

Esempi di failure:

- `tracker.event is not a function`
- `tracker.revenue is not a function`
- `tracker.identify is not a function`
- manca `payload.language`
- manca `payload.referrer`
- non viene piu' gestito `x-umami-cache`
- non viene rispettato `disabled: true` dal server

### 5. Filtri UI e bot filter sono incoerenti

La whitelist backend accetta solo:

- `url_path`, `page_title`, `hostname`, `browser`, `os`, `device`, `country`

Riferimento:

- `core/mantecato_core/filters.py:15`

Ma la UI mostra ancora filtri rimossi:

- `templates/components/_filter_bar.html:97` screen
- `templates/components/_filter_bar.html:98` UTM source
- `templates/components/_filter_bar.html:99` UTM medium
- `templates/components/_filter_bar.html:100` UTM campaign
- `templates/components/_filter_bar.html:101` tag

Il bot filter e' ancora esposto in UI:

- `templates/components/_filter_bar.html:140`

Ma backend e' un no-op:

- `core/mantecato_core/filters.py:53`
- `core/mantecato_core/filters.py:63`
- `core/mantecato_core/filters.py:88`

Impatto:

- L'utente puo' selezionare filtri che non faranno nulla.
- Il bot filter sembra attivo ma non filtra.
- Rischio alto di analytics falsate.

### 6. Import Umami ancora copia tabelle eliminate

`apps/core/services.py` continua a definire import Umami per tabelle rimosse:

- `apps/core/services.py:48` session
- `apps/core/services.py:50` event_data
- `apps/core/services.py:51` session_data
- `apps/core/services.py:52` revenue
- `apps/core/services.py:53` segment
- `apps/core/services.py:60` `_DATA_TABLES` include `sessions`, `event_data`, `session_data`, `revenue`
- `apps/core/services.py:231` `replace_target_data()` cancella da tabelle che non esistono piu'

Impatto:

- Import data-only puo' fallire con `relation does not exist`.
- Anche se non fallisce subito, la logica importa dati che lo schema v4 non puo' piu' rappresentare.
- UI di import promette ancora un comportamento non compatibile con v4.

### 7. Test suite non allineata e non usabile come gate affidabile

Problemi osservati:

- `pytest -q` globale fallisce in collection per conflitto `tests.conftest`.
- `pytest tests -q` produce 106 failure e 60 errori.
- Gli errori DB su SQLite derivano da migration PostgreSQL-only gia' presenti, ma in v4 diventano ancora piu' difficili da distinguere dai regression failure.
- `packages/mantecato-client/tests` non parte per dipendenza mancante `httpx`.
- I test JS falliscono per API pubbliche rimosse.

Impatto:

- La branch non ha una CI verde riproducibile.
- I failure veri vengono confusi con debito di setup.
- Prima di correggere funzionalita, serve riallineare test e matrice supportata.

## Problemi secondari

- `packages/mantecato-client/src/mantecato_client/analytics.py` continua a esporre metodi per retention, funnels, journeys, revenue e simili, mentre backend e schema non li supportano piu'.
- `templates/analytics/*.html` contiene ancora pagine non raggiungibili o semantica obsoleta per sessioni, eventi, revenue.
- `core/mantecato_core/types.py` mantiene TypedDict per entita' non piu' supportate (`SourceRow`, `EventRow`, `SessionRow`, `RevenueRow`), creando falsa documentazione interna.
- `apps/api/views.py` docstring e response docs descrivono metriche visitors/visits/bounce/revenue non piu' calcolate.

## Raccomandazione

Prima di fare fix puntuali, va scelta una direzione:

1. Ripristinare compatibilita con `main`.
   - Reintrodurre schema session/event/revenue/referrer/UTM.
   - Ripristinare query engine, rotte web, API, tracker API e importer.
   - Mantenere eventualmente un privacy mode configurabile.

2. Accettare il prodotto aggregate-only.
   - Versionare come breaking change.
   - Rimuovere davvero API/CLI/client/docs/template/test delle feature eliminate.
   - Rendere gli endpoint rimossi `410 Gone` o eliminarli in una v4 API versionata.
   - Sistemare migrations e import Umami per importare solo `website_event` compatibile.
   - Aggiornare tracker README, test e TypeScript API.
   - Rimuovere bot filter o implementarlo su dati aggregate disponibili.

Allo stato attuale, `v4/next` e' a meta': ha rimosso il modello dati di `main`, ma conserva molti contratti pubblici. Questo spiega la percezione di branch "estremamente buggata": molte feature non falliscono in modo esplicito, ma sono diventate no-op, dati vuoti o import/runtime error.
