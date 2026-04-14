"""
═══════════════════════════════════════════════════════════════════════════
 ACM API — state_manager.py
 Central Facade for v2 Services
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

import os
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any

from .models import Satellite, Debris, Vector3, Maneuver, CDM
from .services.fleet_service import FleetService
from .services.conjunction_service import ConjunctionService
from .services.maneuver_service import ManeuverService
from .services.comms_service import CommsService
from .services.simulation_service import SimulationService
from .services.decision_service import DecisionService

class StateManager:
    """
    Lightweight facade for AutoCM v2.
    Coordinates specialized services while maintaining backward compatibility
    with existing FastAPI routers.
    """

    def __init__(self):
        # 1. Initialize Services
        self.fleet = FleetService()
        self.conj = ConjunctionService()
        self.maneuver = ManeuverService()
        
        data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
        self.comms = CommsService(os.path.join(data_dir, "ground_stations.csv"))
        self.decision = DecisionService(self.fleet, self.maneuver)
        
        self.sim = SimulationService(self.fleet, self.conj, self.maneuver, self.comms, self.decision)
        
        # 2. Local State for UI and WebSockets
        self._ws_clients = set()
        self.alerts = []
        self._alert_counter = 0
        self.real_interval_ms = 1000  # ms between sim ticks

    # ── Backward Compatible Properties ─────────────────────────────────────
    
    @property
    def satellites(self): return self.fleet.satellites
    
    @property
    def debris(self): return self.fleet.debris
    
    @property
    def sim_time(self): return self.sim.sim_time
    
    @property
    def cdms(self): return self.conj.active_cdms
    
    @property
    def maneuvers(self): 
        # Combine executed and pending for UI
        pending = []
        for sat_burns in self.maneuver.scheduled_burns.values():
            pending.extend(sat_burns)
        return pending

    @property
    def ws_clients(self): return self._ws_clients

    @property
    def sim_running(self): return self.sim.running
    @sim_running.setter
    def sim_running(self, val): self.sim.running = val

    @property
    def step_seconds(self): return self.sim.step_seconds
    @step_seconds.setter
    def step_seconds(self, val): self.sim.step_seconds = val

    # ── Data Loading ──────────────────────────────────────────────────────

    def load_catalog(self, catalog_path: str):
        """Loads satellites and debris from catalog.json."""
        if not os.path.exists(catalog_path):
            print(f"[StateManager] Catalog not found: {catalog_path}")
            return

        with open(catalog_path, "r") as f:
            data = json.load(f)

        for s in data.get("satellites", []):
            # Convert dict to Satellite model
            sat = Satellite(
                id=s['id'],
                r=Vector3(**s['state']['r']),
                v=Vector3(**s['state']['v']),
                fuel_kg=s.get('mass_fuel', 50.0),
                status=s.get('status', 'NOMINAL')
            )
            # Pre-calculate lat/lon/alt
            from .core.physics import eci_to_latlon
            sat.lat, sat.lon, sat.alt_km = eci_to_latlon(sat.r.to_np())
            self.fleet.add_satellite(sat)

        for d in data.get("debris", []):
            deb = Debris(
                id=d['id'],
                r=Vector3(**d['state']['r']),
                v=Vector3(**d['state']['v']),
                lat=0, lon=0, alt_km=0 # Placeholder till calculated
            )
            from .core.physics import eci_to_latlon
            new_r = deb.r.to_np()
            deb.lat, deb.lon, deb.alt_km = eci_to_latlon(new_r)
            self.fleet.add_debris(deb)

    # ── Simulation Facade ─────────────────────────────────────────────────

    def simulate_step(self, dt: float):
        return self.sim.step(dt)

    # ── Validation & Execution ────────────────────────────────────────────

    def validate_maneuver(self, sat_id: str, burn_time: datetime, delta_v: dict, **kwargs) -> dict:
        """
        Validates maneuver against Section 4.2 & 5 constraints.
        """
        sat = self.fleet.satellites.get(sat_id)
        if not sat:
            return {"valid": False, "errors": ["Satellite not found"]}

        errors = []
        
        # 1. Comms LOS Check (Section 5.4)
        has_los = self.comms.has_los(sat.r.to_np())
        if not has_los:
            errors.append("No ground station line-of-sight for command upload")

        # 2. Fuel Check
        from .core.navigation import Navigator
        nav = Navigator()
        dv_mag = np.linalg.norm(np.array([delta_v['x'], delta_v['y'], delta_v['z']])) * 1000.0
        fuel_cost = nav.compute_fuel_cost(sat.mass_kg, dv_mag)
        
        sufficient_fuel = sat.fuel_kg >= fuel_cost
        if not sufficient_fuel:
            errors.append(f"Insufficient propellant (need {fuel_cost:.2f}kg)")

        # 3. Cooldown Check
        last_burn = self.maneuver.cooldown_tracker.get(sat_id)
        cooldown_ok = True
        if last_burn and (burn_time - last_burn).total_seconds() < 600:
            cooldown_ok = False
            errors.append("Thruster cooldown violation (600s)")

        return {
            "valid": len(errors) == 0,
            "ground_station_los": has_los,
            "sufficient_fuel": sufficient_fuel,
            "thruster_cooldown_ok": cooldown_ok,
            "fuel_cost_kg": round(fuel_cost, 4),
            "projected_mass_remaining_kg": round(sat.mass_kg - fuel_cost, 2),
            "errors": errors
        }

    def get_stats(self) -> dict:
        """Get constellation statistics."""
        sats = list(self.fleet.satellites.values())
        active = [s for s in sats if s.status != "EOL"]
        critical_cdms = [c for c in self.conj.active_cdms if c.missDistance < 0.1]

        return {
            "satellites": {
                "total": len(sats),
                "active": len(active),
                "eol": len(sats) - len(active),
            },
            "fuel": {
                "total_kg": round(sum(s.fuel_kg for s in sats), 2),
                "avg_kg": round(sum(s.fuel_kg for s in sats) / len(sats) if sats else 0, 2),
            },
            "conjunctions": {
                "total_active": len(self.conj.active_cdms),
                "critical": len(critical_cdms),
            },
            "sim_time": self.sim.sim_time.isoformat(),
        }

    def get_alerts_since(self, after_id: int) -> List[dict]:
        """Get alerts with id > after_id."""
        return [a for a in self.alerts if a["id"] > after_id]

    def _add_alert(self, type: str, level: str, msg: str, sat_id: Optional[str] = None):
        self._alert_counter += 1
        self.alerts.append({
            "id": self._alert_counter,
            "type": type,
            "level": level,
            "message": msg,
            "satellite_id": sat_id,
            "timestamp": self.sim.sim_time.isoformat()
        })
        # Keep buffer small
        if len(self.alerts) > 100:
            self.alerts.pop(0)

    def execute_maneuver(self, sat_id: str, delta_v: dict, burn_time_iso: Optional[str] = None):
        """Direct execution (manual override)."""
        sat = self.fleet.satellites.get(sat_id)
        if not sat: return {"status": "ERROR", "message": "Not found"}
        
        # In v2, we prefer scheduling. Manual override just schedules for T+10s.
        burn_dt = self.sim.sim_time + timedelta(seconds=11)
        from .models import Maneuver, Vector3
        m = Maneuver(
            burn_id=f"MANUAL_{self._alert_counter}",
            satelliteId=sat_id,
            burnTime=burn_dt,
            deltaV_vector=Vector3(**delta_v)
        )
        res = self.maneuver.schedule_burns(sat_id, [m], sat.fuel_kg)
        return res

    # ── Snapshot for Dashboard ────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        return {
            "timestamp": self.sim.sim_time.isoformat(),
            "satellites": [s.model_dump() for s in self.fleet.satellites.values()],
            "debris_cloud": self.fleet.get_debris_snapshot(),
            "cdms": [c.model_dump() for c in self.conj.active_cdms],
            "maneuvers": self.maneuvers # Combined pending
        }

    def register_ws(self, ws): self._ws_clients.add(ws)
    def unregister_ws(self, ws): self._ws_clients.discard(ws)

state = StateManager()
