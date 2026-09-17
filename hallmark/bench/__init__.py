"""The attack bench.

A composition root rather than an application service: it wires the enforcement point,
the adapters and the unprotected agent together to measure them against each other. It
therefore sits outside `application/`, which must not reach outward to adapters.
"""
