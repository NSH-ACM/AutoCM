"""
═══════════════════════════════════════════════════════════════════════════
 ACM CORE — engine_wrapper.py
 High-level Python interface to the C++ physics engine.
 National Space Hackathon 2026

 This module provides a clean Python API over the compiled C++ engine
 (microservices/physics/physics_engine.cpp). It handles:
   - Importing the compiled C++ module with mock fallback
   - Type conversion and validation
   - Batch operations for constellation-wide tasks
   - Performance tracking and telemetry

 Usage:
   from core.engine_wrapper import PhysicsEngine
   engine = PhysicsEngine()
   updated = engine.propagate(objects, dt=300)
   cdms    = engine.detect_conjunctions(sats, debris, lookahead=86400)
═══════════════════════════════════════════════════════════════════════════
"""

import sys
import os
import time
from datetime import datetime, timezone
from typing import List, Dict, Optional, Any

# ── Import the C++ engine with fallback ───────────────────────────────────────
# Try the compiled C++ extension first, fall back to Python mock.

_ENGINE_TYPE = 'mock'
_engine = None

def _load_engine():
    """Load the C++ physics engine or fall back to mock."""
    global _engine, _ENGINE_TYPE

    # Use absolute path to the project root
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(current_dir)

    # 1. Try autocm_engine.so in root/core/
    core_path = os.path.join(root_dir, 'core')
    if core_path not in sys.path:
        sys.path.insert(0, core_path)

    try:
        import autocm_engine
        _engine = autocm_engine
        _ENGINE_TYPE = 'cpp'
        print(f"[EngineWrapper] ✓ autocm_engine loaded from {core_path}")
        return
    except ImportError:
        pass

    # 2. Try the Python mock in api/core/
    mock_path = os.path.join(current_dir, 'core')
    if mock_path not in sys.path:
        sys.path.insert(0, mock_path)

    try:
        import mock_physics_engine as mock_engine
        _engine = mock_engine
        _ENGINE_TYPE = 'mock'
        print(f"[EngineWrapper] ⚠ C++ engine not found — using Python mock from {mock_path}")
    except ImportError:
        print(f"[EngineWrapper] ✗ No engine or mock found. Searched {core_path} and {mock_path}")

_load_engine()


# ═══════════════════════════════════════════════════════════════════════════
#  PhysicsEngine — High-Level Interface
# ═══════════════════════════════════════════════════════════════════════════

class PhysicsEngine:
    """
    High-level Python interface to the ACM C++ physics core.

    Wraps the compiled pybind11 module with:
      - Input validation
      - Performance tracking
      - Graceful error handling
      - Batch convenience methods
    """

    def __init__(self):
        self._call_count = 0
        self._total_ms = 0.0
        self._engine_supports_epoch = True

    @property
    def engine_type(self) -> str:
        """Returns 'cpp' or 'mock' depending on which engine is loaded."""
        return _ENGINE_TYPE

    @property
    def is_cpp(self) -> bool:
        """True if the high-performance C++ engine is active."""
        return _ENGINE_TYPE == 'cpp'

    def _track(self, fn, *args, **kwargs):
        """Wrap a call with performance tracking."""
        t0 = time.monotonic()
        result = fn(*args, **kwargs)
        elapsed = (time.monotonic() - t0) * 1000
        self._call_count += 1
        self._total_ms += elapsed
        return result

    # ── Propagation ───────────────────────────────────────────────────────

    def propagate(self, objects: List[Dict], dt: float) -> List[Dict]:
        """
        Propagate orbital objects forward/backward by dt seconds.

        Args:
            objects: List of {id, r:{x,y,z}, v:{x,y,z}} in km, km/s ECI
            dt: Time step in seconds (positive=forward, negative=backward)

        Returns:
            Updated list with same schema.
        """
        if not objects:
            return []
        if abs(dt) > 86400 * 30:
            raise ValueError(f"dt={dt}s exceeds 30-day limit — likely a unit error")

        return list(self._track(_engine.propagate, objects, dt))

    def propagate_steps(self, objects: List[Dict], steps: List[float]) -> List[List[Dict]]:
        """
        Multi-step propagation. Returns snapshots after each dt.

        Args:
            objects: Initial state list
            steps: List of dt values [dt1, dt2, ...]

        Returns:
            List of object-state snapshots after each step.
        """
        snapshots = []
        current = objects
        for dt in steps:
            current = self.propagate(current, dt)
            snapshots.append(list(current))
        return snapshots

    # ── Conjunction Detection ─────────────────────────────────────────────

    def detect_conjunctions(self, satellites: List[Dict], debris: List[Dict],
                             lookahead_seconds: float = 86400,
                             epoch_iso: Optional[str] = None) -> List[Dict]:
        """
        Screen for close approaches between satellites and debris.

        Args:
            satellites: List of satellite states {id, r, v}
            debris: List of debris states {id, r, v}
            lookahead_seconds: Time window to scan (default 24h)
            epoch_iso: Optional ISO 8601 epoch for absolute TCA timestamps

        Returns:
            List of CDMs: [{satelliteId, debrisId, missDistance, probability, tca}]
            Only reports miss_distance < 5 km.
        """
        if not satellites or not debris:
            return []

        if epoch_iso is None:
            epoch_iso = datetime.now(timezone.utc).isoformat()

        if self._engine_supports_epoch:
            try:
                raw_cdms = self._track(
                    _engine.detect_conjunctions,
                    satellites, debris, lookahead_seconds, epoch_iso
                )
            except TypeError:
                self._engine_supports_epoch = False
                
        if not self._engine_supports_epoch:
            # Fallback for engines that don't accept epoch_iso
            raw_cdms = self._track(
                _engine.detect_conjunctions,
                satellites, debris, lookahead_seconds
            )

        # Normalize field names
        cdms = []
        for c in raw_cdms:
            c = dict(c)
            if 'miss_distance' in c and 'missDistance' not in c:
                c['missDistance'] = c.pop('miss_distance')
            cdms.append(c)

        return cdms

    # ── Line of Sight ─────────────────────────────────────────────────────

    def check_los(self, satellite: Dict, ground_stations: List[Dict],
                   timestamp: str) -> bool:
        """
        Check if any ground station has line-of-sight to a satellite.

        Args:
            satellite: {r:{x,y,z}} in ECI km
            ground_stations: [{lat, lon, alt_km?}] in degrees
            timestamp: ISO 8601 UTC string

        Returns:
            True if elevation >= 5° from any station.
        """
        return bool(self._track(_engine.check_los, satellite, ground_stations, timestamp))

    def check_los_batch(self, satellites: List[Dict], ground_stations: List[Dict],
                         timestamp: str) -> List[Dict]:
        """
        Batch LOS check for an entire constellation.

        Returns:
            [{id, visible, max_elevation_deg}] in input order.
        """
        try:
            return list(self._track(
                _engine.check_los_batch, satellites, ground_stations, timestamp
            ))
        except AttributeError:
            # Fallback: sequential check_los
            results = []
            for sat in satellites:
                vis = self.check_los(sat, ground_stations, timestamp)
                results.append({
                    'id': sat.get('id'),
                    'visible': vis,
                    'max_elevation_deg': 45.0 if vis else -90.0
                })
            return results

    # ── Maneuver Planning ─────────────────────────────────────────────────

    def plan_evasion(self, satellite: Dict, debris: Dict) -> Optional[Dict]:
        """
        Plan minimum-ΔV evasion burn in RTN frame.

        Returns:
            {deltaV_ECI, dvMagnitude_ms, fuelCostKg, strategy} or None
        """
        if hasattr(_engine, 'plan_evasion'):
            result = self._track(_engine.plan_evasion, satellite, debris)
            return dict(result) if result is not None else None
        return None

    def plan_recovery(self, evasion_dv: Dict, mass_kg: float) -> Dict:
        """
        Plan Hohmann-style recovery burn after evasion.

        Returns:
            {deltaV_ECI, dvMagnitude_ms, fuelCostKg}
        """
        if hasattr(_engine, 'plan_recovery'):
            return dict(self._track(_engine.plan_recovery, evasion_dv, mass_kg))

        # Fallback: simple reversal
        scale = 0.95
        return {
            'deltaV_ECI': {
                'x': -evasion_dv['x'] * scale,
                'y': -evasion_dv['y'] * scale,
                'z': -evasion_dv['z'] * scale,
            },
            'dvMagnitude_ms': 0.0,
            'fuelCostKg': 0.0,
        }

    # ── Telemetry ─────────────────────────────────────────────────────────

    def get_stats(self) -> Dict:
        """Combined engine + wrapper statistics."""
        engine_stats = {}
        if hasattr(_engine, 'get_engine_stats'):
            engine_stats = dict(_engine.get_engine_stats())

        return {
            'engine_type': _ENGINE_TYPE,
            'wrapper_calls': self._call_count,
            'wrapper_total_ms': round(self._total_ms, 2),
            'wrapper_avg_ms': round(self._total_ms / self._call_count, 3) if self._call_count > 0 else 0,
            **engine_stats,
        }


# ── Module-level singleton for convenience ─────────────────────────────────
engine = PhysicsEngine()
