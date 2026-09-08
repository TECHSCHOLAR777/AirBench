# Offline replay report

The repository's deterministic ledger acceptance fixtures replay and verify
signed exports without opening a network socket (`tests/test_m24_acceptance.py`).
This proves the local replay mechanism and failure behavior for fixture data.

The complete refinery/PSU run is not yet replayable because its target-host
ledger export, model identities, rendered artifact, and external signatures
have not been supplied. The release gate therefore remains blocked.
