# api/core/__init__.py
"""ACM Core — Python interface to the physics engine and autonomy logic."""

from ..engine_wrapper import PhysicsEngine, engine
from .autonomy_logic import AutonomyManager, classify_cdm, CDMSeverity, SatelliteStatus

__all__ = [
    'PhysicsEngine',
    'engine',
    'AutonomyManager',
    'classify_cdm',
    'CDMSeverity',
    'SatelliteStatus',
]
