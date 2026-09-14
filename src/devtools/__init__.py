"""Development-only tools that are deliberately outside the shipped core.

Nothing in this package is installed with AirBench.  It exists so integration
tests and local demos can exercise provider adapters that are not allowed in the
frozen, no-egress ``contracts`` package (for example the opt-in Gemini REST
adapter).  The runtime never imports from here.
"""
