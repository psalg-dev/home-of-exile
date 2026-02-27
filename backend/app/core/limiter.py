"""Shared slowapi rate limiter instance.

Import this module to apply per-route rate-limit decorators without
circular imports between main.py and the route modules.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

# Shared limiter — registered on app.state.limiter in main.py
limiter = Limiter(key_func=get_remote_address, default_limits=[])
