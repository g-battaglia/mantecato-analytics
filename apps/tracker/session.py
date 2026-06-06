"""Session resolution — removed for privacy-first aggregate-only mode.

Mantecato no longer tracks sessions or visitors. Every pageview is an
anonymous, independent event with no cross-request identifiers. This
module is intentionally empty — the previous session fingerprinting
logic (deterministic UUIDs from IP+UA+monthly salt, signed tokens,
visit_id rotation) violated the privacy-first mandate in PLAN.md:
no fingerprinting, no persistent identifiers, no session tracking.
"""

from __future__ import annotations
