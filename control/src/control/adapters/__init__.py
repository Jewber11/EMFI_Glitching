"""Hardware adapters.

Replaces the old `EMFI_Interfacing` submodule + sys.path injection. Each
adapter wraps an upstream library (chipshover, chipshouter, donjon-scaffold)
or a subprocess (openocd, dslite). All adapter calls are designed to be run
inside a `control.workers.DeviceWorker` thread.
"""
