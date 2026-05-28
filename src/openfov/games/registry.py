"""Built-in game registry. Adding a game = one new file + one line here."""

from __future__ import annotations

from openfov.games.base import GameProfile
from openfov.games.iracing import IRACING_PROFILE

BUILTIN_PROFILES: tuple[GameProfile, ...] = (
    IRACING_PROFILE,
    # Future entries (DCS, MSFS, Elite Dangerous, ...) go here.
)


def get_profile(game_id: str) -> GameProfile | None:
    """Look up a profile by id slug. None if not found."""
    for p in BUILTIN_PROFILES:
        if p.id == game_id:
            return p
    return None


__all__ = ["BUILTIN_PROFILES", "get_profile"]
