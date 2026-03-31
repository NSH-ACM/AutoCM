"""
Python wrapper for the AutoCM C++ physics engine.
Provides type hints and documentation for all C++ functions.
"""

try:
    import autocm_engine
except ImportError:
    raise ImportError("Could not import autocm_engine. Make sure it's built and in the Python path.")

# Re-export all C++ classes and functions
from autocm_engine import *

# Function documentation
__doc__ = """
AutoCM Physics Engine Python Wrapper
====================================

This module provides Python bindings for the AutoCM C++ physics engine.

Classes:
--------
- Vec3: 3D vector (x, y, z) in km
- StateVector: Orbital state with epoch time, position, and velocity
- OrbitalObject: Satellite or debris object with state and properties
- CDMWarning: Conjunction detection message
- ConjunctionCandidate: Potential conjunction from KD-tree search
- ManeuverPlan: Planned maneuver with delta-v and timing
- Mat3x3: 3x3 matrix for coordinate transformations

Functions:
---------
- propagate(state, dt_total, dt_step=1.0): Propagate orbital state using RK4 with J2
- run_conjunction_assessment(satellites, debris, lookahead=86400, dt_step=30): 
  Find conjunctions using KD-tree search
- plan_evasion(satellite, warning): Plan evasion maneuver for conjunction
- plan_recovery(satellite, nominal_slot, time_offset): Plan station-keeping maneuver
- apply_burn(satellite, dv_eci_kms): Apply delta-v to satellite
- needs_graveyard(satellite): Check if satellite needs graveyard disposal
- plan_graveyard(satellite): Plan graveyard disposal maneuver
- fuel_consumed(dv_ms, mass_kg): Calculate fuel consumption using Tsiolkovsky
- eci_to_rtn_matrix(r, v): Get ECI to RTN rotation matrix
- rtn_to_eci(dv_rtn, r, v): Convert RTN delta-v to ECI

Units:
-----
- Position: km
- Velocity: km/s
- Delta-v: km/s (input to rtn_to_eci), m/s (input to fuel_consumed)
- Mass: kg
- Time: seconds since J2000
- Distance: km (except collision threshold: 0.100 km = 100 m)
"""

# Add docstrings to key functions for better IDE support
def propagate_with_docs(state: StateVector, dt_total: float, dt_step: float = 1.0) -> StateVector:
    """
    Propagate orbital state using RK4 integration with J2 perturbation.
    
    Args:
        state: Initial orbital state (position in km, velocity in km/s)
        dt_total: Total propagation time in seconds
        dt_step: Integration time step in seconds (default 1.0)
    
    Returns:
        Final propagated state vector
    """
    return autocm_engine.propagate(state, dt_total, dt_step)

def run_conjunction_assessment_with_docs(
    satellites: list, 
    debris: list, 
    lookahead_seconds: float = 86400.0,
    dt_step: float = 30.0
) -> list:
    """
    Run conjunction assessment using KD-tree spatial search.
    
    Args:
        satellites: List of OrbitalObject satellites
        debris: List of OrbitalObject debris
        lookahead_seconds: Time horizon for conjunction search (default 24h)
        dt_step: Propagation step for TCA calculation (default 30s)
    
    Returns:
        List of CDMWarning objects for conjunctions < 100m miss distance
    """
    return autocm_engine.run_conjunction_assessment(satellites, debris, lookahead_seconds, dt_step)

def fuel_consumed_with_docs(dv_ms: float, mass_current_kg: float) -> float:
    """
    Calculate fuel consumption using Tsiolkovsky rocket equation.
    
    Args:
        dv_ms: Delta-v in meters per second
        mass_current_kg: Current total mass in kg
    
    Returns:
        Fuel consumed in kg
    """
    return autocm_engine.fuel_consumed(dv_ms, mass_current_kg)

# Override functions with documented versions
propagate = propagate_with_docs
run_conjunction_assessment = run_conjunction_assessment_with_docs
fuel_consumed = fuel_consumed_with_docs
