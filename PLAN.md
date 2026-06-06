# Introduction

Mantecato must become an analytics tool built with an absolute priority: privacy-first at all costs.

The product must be installable without cookie banners, without CMPs, without opt-ins, and without prior consent for analytics. To achieve this goal in a defensible manner across the EU, Italy, the UK, and the US, the architecture must eliminate everything that normally triggers consent obligations or increases privacy risks:

- no analytics cookies;
- no visitor/session cookies;
- no third-party cookies;
- no localStorage/sessionStorage/IndexedDB;
- no fingerprinting;
- no persistent identifiers;
- no cross-site tracking;
- no referrer/UTM/click-id analytics;
- no custom event payloads;
- no identify methods;
- no session replay;
- no visitor/session profiles.

The consequence is intentional: Mantecato must measure aggregate events, not people. Maximum accuracy is maintained for metrics measurable without identifiers. Metrics that require stable identifiers must not be simulated using technical shortcuts.

This document serves as the specification for the coding agent. If a technical choice increases accuracy but introduces consent risk, persistent tracking, or identification, it must be discarded.

## Product Goal

Mantecato must provide aggregate, cookieless, and consent-free analytics.

Metrics supported with high accuracy:

- total pageviews;
- top pages by pageviews;
- human vs. bot pageviews;
- filtered bots and classification reasons;
- realtime aggregate pageviews;
- aggregate trend over time;
- limited Umami import for supported aggregate metrics only.

Metrics intentionally not supported by the product:

- exact unique visitors;
- exact multi-page sessions/visits;
- returning visitors;
- user journeys;
- retention cohorts;
- user/session-based funnels;
- session replay;
- session lists;
- visitor profiles;
- marketing attribution.

Do not implement estimated visitor/session metrics via IP, User-Agent, screen, language, timing, or other signals. This would be disguised fingerprinting.

There is only one runtime behavior: strict cookieless aggregate analytics. Do not add product modes, feature flags, compatibility modes, or deployment modes that re-enable cookies, storage, fingerprinting, identity, or richer event payloads.

## Legal Requirements Handled as Technical Requirements

To minimize issues in the EU, Italy, the UK, and the US, the product must use the most restrictive common denominator:

- UK/PECR: analytics cookies are not considered strictly necessary by the UK regulator; therefore, the product must not use them.
- EU/ePrivacy: storing/accessing information on the terminal requires consent except under specific exemptions; to avoid relying on national exemptions, the product must not use analytics cookies or browser storage.
- Italy/Garante: first-party aggregate analytics cookies can be assimilated into technical cookies under certain conditions, but Mantecato still chooses a cookieless approach to cover the UK and conservative EU interpretations as well.
- US: avoid sale/share, targeted advertising, cross-context identifiers, and data that could turn analytics into profiling.

Allowed claim:

```text
Mantecato is a privacy-first, cookieless, aggregate web analytics tool designed
to run without analytics consent banners in EU/Italy/UK/US deployments.
```
