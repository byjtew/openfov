"""Game profile abstraction. Each game (iRacing, DCS, MSFS, ...) is a
`GameProfile` describing its process names, default tuning, and output
protocol. The runtime detector polls running processes and activates the
matching profile.

v1 ships only iRacing — but the abstraction is in place so adding a game
is one new file."""

from openfov.games.base import GameDetector, GameProfile
from openfov.games.iracing import IRACING_PROFILE
from openfov.games.registry import BUILTIN_PROFILES, get_profile

__all__ = [
    "BUILTIN_PROFILES",
    "GameDetector",
    "GameProfile",
    "IRACING_PROFILE",
    "get_profile",
]
