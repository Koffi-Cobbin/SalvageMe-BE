"""
No signal handlers needed yet for accounts. Kept as an explicit empty module
(rather than omitted) so `apps.py::ready()` has a stable import target as
the app grows — avoids a future refactor just to wire up the first signal.
"""
