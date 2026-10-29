"""Runnable reference modules for Waycast.

These modules are standalone WebSocket clients that speak the Waycast Wire
protocol (ADR-0008).  They are the developer reference for writing your own
modules (A12/A24) and double as the test fixtures for the localhost
end-to-end tests.

Run them against a running hub:

    PYTHONPATH=src:examples waycast serve &
    PYTHONPATH=src:examples .venv/bin/python -m waycast_examples.echo_bell

Each module connects to ws://<hub>/ws/modules, authenticates with the
connection token, sends a capability advertisement as the first frame, and
then speaks the full-duplex frame protocol over the same multiplexed
connection.
"""
