"""
Fixed threshold table for the leaderboard's "Hero" tiers — see
docs/LEADERBOARD_PLAN.md. Deliberately a code-defined table, not an
admin-configurable model, to keep v1 simple; tune these once real
donation-count distribution is visible after launch.
"""

HERO_TIERS = [
    (1, "Contributor"),
    (5, "Hero"),
    (15, "Champion"),
    (50, "Legend"),
]


def get_hero_tier(completed_donation_count: int) -> str | None:
    tier = None
    for threshold, name in HERO_TIERS:
        if completed_donation_count >= threshold:
            tier = name
    return tier
