"""
Autonomy Decision Logic for AutoCM fleet management.
"""

from typing import Dict, List, Any
import json
import math
from datetime import datetime, timezone

try:
    from .engine_wrapper import *
except ImportError:
    raise ImportError("Could not import engine_wrapper. Make sure the C++ engine is built.")

def eci_to_geodetic(r_eci: Vec3, gst_seconds: float) -> Dict[str, float]:
    """
    Convert ECI position to geodetic coordinates.
    Uses simplified ECI→ECEF→geodetic conversion.
    """
    # Greenwich Sidereal Time rotation
    theta_gst = gst_seconds
    
    # ECI to ECEF (rotate around Z axis)
    x_ecef = r_eci.x * math.cos(theta_gst) + r_eci.y * math.sin(theta_gst)
    y_ecef = -r_eci.x * math.sin(theta_gst) + r_eci.y * math.cos(theta_gst)
    z_ecef = r_eci.z
    
    # ECEF to geodetic (simplified)
    r = math.sqrt(x_ecef**2 + y_ecef**2 + z_ecef**2)
    lat = math.asin(z_ecef / r) if r > 0 else 0.0
    lon = math.atan2(y_ecef, x_ecef)
    alt = r - 6378.137  # km (Earth radius)
    
    return {
        "latitude": math.degrees(lat),
        "longitude": math.degrees(lon),
        "altitude_km": alt
    }

class AutonomyEngine:
    """
    Wraps the C++ engine and makes fleet-level decisions.
    """
    
    def __init__(self, catalog_path: str):
        """
        Load catalog.json, initialise all OrbitalObjects via engine_wrapper.
        """
        self.satellites: Dict[str, OrbitalObject] = {}
        self.debris: Dict[str, OrbitalObject] = {}
        self.scheduled_maneuvers: List[ManeuverPlan] = []
        self.cooldown_tracker: Dict[str, float] = {}
        self.sim_time: float = 0.0
        
        # Load catalog
        with open(catalog_path, 'r') as f:
            catalog = json.load(f)
        
        # Initialize satellites
        for sat_data in catalog.get('satellites', []):
            sat = OrbitalObject()
            sat.id = sat_data['id']
            sat.type = sat_data['type']
            sat.controllable = sat_data['controllable']
            sat.mass_dry = sat_data['mass_dry']
            sat.mass_fuel = sat_data['mass_fuel']
            sat.last_burn_time = -600.0  # Initialize to -600s to allow immediate burns
            
            # State vector
            state = sat_data['state']
            sat.state = StateVector()
            sat.state.t = state['t']
            sat.state.r = Vec3(state['r']['x'], state['r']['y'], state['r']['z'])
            sat.state.v = Vec3(state['v']['x'], state['v']['y'], state['v']['z'])
            
            # Store nominal slot for satellites
            if 'nominal_slot' in sat_data:
                sat.nominal_slot = StateVector()
                nominal = sat_data['nominal_slot']
                sat.nominal_slot.t = nominal['t']
                sat.nominal_slot.r = Vec3(nominal['r']['x'], nominal['r']['y'], nominal['r']['z'])
                sat.nominal_slot.v = Vec3(nominal['v']['x'], nominal['v']['y'], nominal['v']['z'])
            else:
                # If no nominal slot, use current state
                sat.nominal_slot = StateVector()
                sat.nominal_slot.t = sat.state.t
                sat.nominal_slot.r = Vec3(sat.state.r.x, sat.state.r.y, sat.state.r.z)
                sat.nominal_slot.v = Vec3(sat.state.v.x, sat.state.v.y, sat.state.v.z)
            
            self.satellites[sat.id] = sat
        
        # Initialize debris
        for deb_data in catalog.get('debris', []):
            deb = OrbitalObject()
            deb.id = deb_data['id']
            deb.type = deb_data['type']
            deb.controllable = deb_data['controllable']
            deb.mass_dry = deb_data['mass_dry']
            deb.mass_fuel = deb_data['mass_fuel']
            deb.last_burn_time = -600.0  # Not applicable for debris
            
            # State vector
            state = deb_data['state']
            deb.state = StateVector()
            deb.state.t = state['t']
            deb.state.r = Vec3(state['r']['x'], state['r']['y'], state['r']['z'])
            deb.state.v = Vec3(state['v']['x'], state['v']['y'], state['v']['z'])
            
            self.debris[deb.id] = deb
        
        print(f"Loaded {len(self.satellites)} satellites and {len(self.debris)} debris objects")
        
    def ingest_telemetry(self, payload: dict) -> dict:
        """
        Parse the /api/telemetry JSON body.
        Update internal states for each object in payload["objects"].
        Run run_conjunction_assessment() over updated states.
        For any NEW CDMWarning not already scheduled:
        - Call plan_evasion() 
        - Respect cooldown: if sat burned < 600 s ago, delay burn_time
        - Call plan_recovery() for 1 orbit after evasion
        - Append both plans to self.scheduled_maneuvers
        """
        processed_count = 0
        active_warnings = []
        
        # Update object states from telemetry
        for obj_data in payload.get('objects', []):
            obj_id = obj_data['id']
            
            # Update satellite or debris
            if obj_id in self.satellites:
                obj = self.satellites[obj_id]
            elif obj_id in self.debris:
                obj = self.debris[obj_id]
            else:
                continue  # Unknown object
            
            # Update state
            if 'state' in obj_data:
                state = obj_data['state']
                obj.state.t = state['t']
                obj.state.r = Vec3(state['r']['x'], state['r']['y'], state['r']['z'])
                obj.state.v = Vec3(state['v']['x'], state['v']['y'], state['v']['z'])
            
            # Update fuel if provided
            if 'mass_fuel' in obj_data:
                obj.mass_fuel = obj_data['mass_fuel']
            
            processed_count += 1
        
        # Run conjunction assessment
        satellites_list = list(self.satellites.values())
        debris_list = list(self.debris.values())
        
        warnings = run_conjunction_assessment(satellites_list, debris_list)
        
        # Process new warnings
        for warning in warnings:
            warning_key = f"{warning.satellite_id}_{warning.debris_id}_{warning.tca_seconds_from_now}"
            
            # Check if this warning is already being handled
            already_scheduled = any(
                m.satellite_id == warning.satellite_id and 
                abs(m.burn_time_offset_s - warning.tca_seconds_from_now + 300) < 60
                for m in self.scheduled_maneuvers
            )
            
            if not already_scheduled:
                active_warnings.append(warning)
                
                # Plan evasion maneuver
                if warning.satellite_id in self.satellites:
                    sat = self.satellites[warning.satellite_id]
                    
                    # Check cooldown
                    last_burn_time = sat.last_burn_time
                    cooldown_remaining = 600 - (self.sim_time - last_burn_time)
                    
                    evasion_plan = plan_evasion(sat, warning)
                    
                    if cooldown_remaining > 0:
                        evasion_plan.burn_time_offset_s += cooldown_remaining
                    
                    self.scheduled_maneuvers.append(evasion_plan)
                    
                    # Plan recovery burn for 1 orbit after evasion
                    if hasattr(sat, 'nominal_slot'):
                        recovery_plan = plan_recovery(sat, sat.nominal_slot, evasion_plan.burn_time_offset_s)
                        if recovery_plan.burn_id:  # Non-empty plan
                            self.scheduled_maneuvers.append(recovery_plan)
        
        return {
            "status": "ACK", 
            "processed_count": processed_count, 
            "active_cdm_warnings": len(active_warnings)
        }
    
    def schedule_maneuver(self, payload: dict) -> dict:
        """
        Accept external maneuver sequence from /api/maneuver/schedule.
        Validate: ground station LOS (stub returning True for now — 
        Person B will hook in real LOS check via API).
        Validate: sufficient fuel.
        Append to self.scheduled_maneuvers.
        """
        validation = {"valid": True, "errors": []}
        
        # Check ground station LOS (stub - always true for now)
        los_available = True
        if not los_available:
            validation["valid"] = False
            validation["errors"].append("No ground station LOS available")
        
        # Validate satellite exists and has sufficient fuel
        sat_id = payload.get('satellite_id')
        if sat_id not in self.satellites:
            validation["valid"] = False
            validation["errors"].append(f"Satellite {sat_id} not found")
        else:
            sat = self.satellites[sat_id]
            dv_eci = Vec3(
                payload['dv_eci_kms']['x'],
                payload['dv_eci_kms']['y'],
                payload['dv_eci_kms']['z']
            )
            
            # Check fuel sufficiency
            total_mass = sat.mass_dry + sat.mass_fuel
            dv_ms = math.sqrt(dv_eci.x**2 + dv_eci.y**2 + dv_eci.z**2) * 1000.0
            required_fuel = fuel_consumed(dv_ms, total_mass)
            
            if sat.mass_fuel < required_fuel:
                validation["valid"] = False
                validation["errors"].append(f"Insufficient fuel: need {required_fuel:.3f} kg, have {sat.mass_fuel:.3f} kg")
        
        if validation["valid"]:
            # Create maneuver plan
            plan = ManeuverPlan()
            plan.burn_id = payload.get('burn_id', f"EXTERNAL_{sat_id}_{int(self.sim_time)}")
            plan.satellite_id = sat_id
            plan.burn_time_offset_s = payload.get('burn_time_offset_s', 0.0)
            plan.dv_eci_kms = dv_eci
            plan.estimated_fuel_kg = required_fuel
            plan.is_recovery = payload.get('is_recovery', False)
            
            self.scheduled_maneuvers.append(plan)
        
        return {"status": "SCHEDULED", "validation": validation}
    
    def simulate_step(self, step_seconds: float) -> dict:
        """
        1. Execute any scheduled maneuvers whose burn_time_offset_s 
        falls within [sim_time, sim_time + step_seconds].
        - Call apply_burn() for each.
        - Update cooldown_tracker.
        - Count maneuvers_executed.
        2. Propagate ALL objects (satellites + debris) forward by 
        step_seconds using propagate() with dt_step = 30 s.
        3. Check for graveyard-eligible satellites; auto-schedule 
        graveyard burns if not already planned.
        4. Detect any collisions (miss distance < 0.100 km post-step).
        5. Advance sim_time by step_seconds.
        """
        maneuvers_executed = 0
        collisions_detected = 0
        
        # Execute scheduled maneuvers
        maneuvers_to_execute = []
        remaining_maneuvers = []
        
        for plan in self.scheduled_maneuvers:
            burn_time = self.sim_time + plan.burn_time_offset_s
            
            if burn_time <= self.sim_time + step_seconds:
                maneuvers_to_execute.append(plan)
            else:
                remaining_maneuvers.append(plan)
        
        self.scheduled_maneuvers = remaining_maneuvers
        
        # Execute maneuvers
        for plan in maneuvers_to_execute:
            if plan.satellite_id in self.satellites:
                sat = self.satellites[plan.satellite_id]
                burn_time = self.sim_time + plan.burn_time_offset_s
                
                if apply_burn(sat, plan.dv_eci_kms, burn_time):
                    maneuvers_executed += 1
                    self.cooldown_tracker[plan.satellite_id] = burn_time
        
        # Propagate all objects
        all_objects = list(self.satellites.values()) + list(self.debris.values())
        
        for obj in all_objects:
            obj.state = propagate(obj.state, step_seconds, 30.0)
        
        # Check for graveyard-eligible satellites
        for sat_id, sat in self.satellites.items():
            if needs_graveyard(sat):
                # Check if graveyard burn already scheduled
                already_scheduled = any(
                    m.satellite_id == sat_id and m.burn_id == "GRAVEYARD_BURN"
                    for m in self.scheduled_maneuvers
                )
                
                if not already_scheduled:
                    graveyard_plan = plan_graveyard(sat)
                    self.scheduled_maneuvers.append(graveyard_plan)
        
        # Detect collisions
        for sat in self.satellites.values():
            for deb in self.debris.values():
                distance = math.sqrt(
                    (sat.state.r.x - deb.state.r.x)**2 +
                    (sat.state.r.y - deb.state.r.y)**2 +
                    (sat.state.r.z - deb.state.r.z)**2
                )
                
                if distance < 0.100:  # 100 meters
                    collisions_detected += 1
        
        # Advance simulation time
        self.sim_time += step_seconds
        
        # Generate ISO timestamp
        timestamp = datetime.fromtimestamp(self.sim_time, tz=timezone.utc).isoformat()
        
        return {
            "status": "STEP_COMPLETE",
            "new_timestamp": timestamp,
            "collisions_detected": collisions_detected,
            "maneuvers_executed": maneuvers_executed
        }
    
    def get_snapshot(self) -> dict:
        """
        Return the /api/visualization/snapshot payload.
        - Convert each satellite ECI r/v → geodetic lat/lon/alt.
        Use the standard ECI→ECEF→geodetic conversion 
        (assume Greenwich sidereal time from sim_time).
        - Return satellites list and flattened debris_cloud tuples.
        """
        satellites = []
        debris_cloud = []
        
        # Greenwich sidereal time (simplified)
        gst_seconds = self.sim_time * (1.00273790935 + 0.0)  # Earth rotation rate
        
        # Process satellites
        for sat in self.satellites.values():
            geodetic = eci_to_geodetic(sat.state.r, gst_seconds)
            
            satellites.append({
                "id": sat.id,
                "latitude": geodetic["latitude"],
                "longitude": geodetic["longitude"],
                "altitude_km": geodetic["altitude_km"],
                "mass_fuel": sat.mass_fuel,
                "controllable": sat.controllable
            })
        
        # Process debris (flattened tuples)
        for deb in self.debris.values():
            geodetic = eci_to_geodetic(deb.state.r, gst_seconds)
            
            debris_cloud.append([
                geodetic["latitude"],
                geodetic["longitude"],
                geodetic["altitude_km"]
            ])
        
        return {
            "satellites": satellites,
            "debris_cloud": debris_cloud
        }
