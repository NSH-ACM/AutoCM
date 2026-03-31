"""
═══════════════════════════════════════════════════════════════════════════
 ACM API — state_manager.py
 In-memory satellite state cache with real-time telemetry tracking.
 National Space Hackathon 2026
═══════════════════════════════════════════════════════════════════════════
"""

import json
import os
import math
import time
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict


# ═══════════════════════════════════════════════════════════════════════════
#  Satellite & Debris State Models
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SatelliteState:
    id: str
    lat: float
    lon: float
    alt_km: float = 500.0
    fuel_kg: float = 50.0
    status: str = "NOMINAL"
    plane: str = ""
    last_update: float = 0.0
    r: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})
    v: dict = field(default_factory=lambda: {"x": 0.0, "y": 0.0, "z": 0.0})

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "lat": round(self.lat, 4),
            "lon": round(self.lon, 4),
            "alt_km": round(self.alt_km, 1),
            "fuel_kg": round(self.fuel_kg, 2),
            "status": self.status,
            "plane": self.plane,
        }


@dataclass
class DebrisObject:
    id: str
    lat: float
    lon: float
    alt_km: float

    def to_tuple(self) -> list:
        return [self.id, round(self.lat, 3), round(self.lon, 3), round(self.alt_km, 1)]


@dataclass
class CDMRecord:
    satelliteId: str
    debrisId: str
    tca: str
    missDistance: float
    probability: float
    status: str = "ACTIVE"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ManeuverRecord:
    satelliteId: str
    burnId: str
    burnTime: str
    duration: float
    type: str
    deltaV: dict
    status: str
    fuelCost: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AlertRecord:
    id: int
    type: str
    severity: str
    message: str
    satelliteId: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


# ═══════════════════════════════════════════════════════════════════════════
#  StateManager — Central In-Memory State Cache
# ═══════════════════════════════════════════════════════════════════════════

class StateManager:
    """
    Manages the in-memory state of the entire constellation.
    Provides thread-safe access to satellite positions, debris cloud,
    CDMs, maneuvers, and alerts.
    """

    def __init__(self):
        self.satellites: Dict[str, SatelliteState] = {}
        self.debris: List[DebrisObject] = []
        self.cdms: List[CDMRecord] = []
        self.maneuvers: List[ManeuverRecord] = []
        self.alerts: List[AlertRecord] = []
        self.sim_time: datetime = datetime(2026, 3, 12, 8, 0, 0, tzinfo=timezone.utc)
        self.sim_running: bool = False
        self.step_seconds: int = 60
        self.real_interval_ms: int = 1000
        self.total_dv_ms: float = 0.0
        self._alert_counter: int = 0
        self._ws_clients: set = set()
        self._initialized: bool = False

    # ── Initialization ────────────────────────────────────────────────────

    def load_catalog(self, catalog_path: str = None):
        """Load satellite and debris catalog from JSON file."""
        if catalog_path is None:
            catalog_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "catalog.json"
            )

        if not os.path.exists(catalog_path):
            print(f"[StateManager] Catalog not found at {catalog_path} — generating default")
            self._generate_default_catalog()
            return

        try:
            with open(catalog_path, "r") as f:
                catalog = json.load(f)

            # Load satellites
            for sat_data in catalog.get("satellites", []):
                sat = SatelliteState(
                    id=sat_data["id"],
                    lat=sat_data["lat"],
                    lon=sat_data["lon"],
                    alt_km=sat_data.get("alt_km", 500.0),
                    fuel_kg=sat_data.get("fuel_kg", 50.0),
                    status=sat_data.get("status", "NOMINAL"),
                    plane=sat_data.get("plane", ""),
                    last_update=time.time(),
                )
                # Convert lat/lon to rough ECI for physics
                sat.r = self._latlon_to_eci(sat.lat, sat.lon, sat.alt_km)
                sat.v = self._compute_orbital_velocity(sat.r, sat.lat)
                self.satellites[sat.id] = sat

            # Load debris
            for deb_data in catalog.get("debris", []):
                self.debris.append(DebrisObject(
                    id=deb_data[0] if isinstance(deb_data, list) else deb_data["id"],
                    lat=deb_data[1] if isinstance(deb_data, list) else deb_data["lat"],
                    lon=deb_data[2] if isinstance(deb_data, list) else deb_data["lon"],
                    alt_km=deb_data[3] if isinstance(deb_data, list) else deb_data.get("alt_km", 450.0),
                ))

            self._initialized = True
            print(f"[StateManager] Loaded {len(self.satellites)} satellites, "
                  f"{len(self.debris)} debris objects")
        except Exception as e:
            print(f"[StateManager] Error loading catalog: {e}")
            self._generate_default_catalog()

    def _generate_default_catalog(self):
        """Generate a default constellation if no catalog file exists."""
        planes = ["Alpha", "Beta", "Gamma", "Delta", "Epsilon",
                   "Foxtrot", "Golf", "Hotel", "India", "Juliet"]
        sats_per_plane = 11

        for pi, plane in enumerate(planes):
            for si in range(sats_per_plane):
                idx = pi * sats_per_plane + si
                inc = 55
                phase = (idx / (len(planes) * sats_per_plane)) * 360
                raan = pi * 36
                lat = inc * math.sin(math.radians(phase))
                lon = ((phase + raan) % 360) - 180
                fuel = 50.0 - random.random() * 5

                sat_id = f"SAT-{plane}-{str(si+1).zfill(2)}"
                status = "NOMINAL"
                if idx == 3:
                    status = "EVADING"
                elif idx == 7:
                    status = "RECOVERING"
                elif idx == 12:
                    status = "EOL"
                    fuel = 1.2

                sat = SatelliteState(
                    id=sat_id, lat=lat, lon=lon, alt_km=500.0,
                    fuel_kg=fuel, status=status, plane=plane,
                    last_update=time.time()
                )
                sat.r = self._latlon_to_eci(sat.lat, sat.lon, sat.alt_km)
                sat.v = self._compute_orbital_velocity(sat.r, sat.lat)
                self.satellites[sat.id] = sat

        # Generate debris
        rng = random.Random(0xDEADBEEF)
        for i in range(5000):
            self.debris.append(DebrisObject(
                id=f"DEB-{str(i).zfill(5)}",
                lat=round((rng.random() - 0.5) * 170, 3),
                lon=round((rng.random() - 0.5) * 360, 3),
                alt_km=round(380 + rng.random() * 270, 1),
            ))

        self._initialized = True
        print(f"[StateManager] Generated {len(self.satellites)} satellites, "
              f"{len(self.debris)} debris")

    # ── Coordinate Conversions ────────────────────────────────────────────

    @staticmethod
    def _latlon_to_eci(lat: float, lon: float, alt_km: float) -> dict:
        """Approximate lat/lon/alt to ECI coordinates."""
        R_EARTH = 6371.0
        r = R_EARTH + alt_km
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        x = r * math.cos(lat_rad) * math.cos(lon_rad)
        y = r * math.cos(lat_rad) * math.sin(lon_rad)
        z = r * math.sin(lat_rad)
        return {"x": round(x, 3), "y": round(y, 3), "z": round(z, 3)}

    @staticmethod
    def _eci_to_latlon(r: dict) -> tuple:
        """Approximate ECI to lat/lon/alt."""
        R_EARTH = 6371.0
        x, y, z = r["x"], r["y"], r["z"]
        r_mag = math.sqrt(x**2 + y**2 + z**2)
        lat = math.degrees(math.asin(z / r_mag)) if r_mag > 0 else 0
        lon = math.degrees(math.atan2(y, x))
        alt = r_mag - R_EARTH
        return round(lat, 4), round(lon, 4), round(alt, 1)

    @staticmethod
    def _compute_orbital_velocity(r: dict, lat: float) -> dict:
        """Compute approximate circular orbital velocity in ECI."""
        MU = 398600.4418  # km³/s²
        r_mag = math.sqrt(r["x"]**2 + r["y"]**2 + r["z"]**2)
        if r_mag < 1:
            return {"x": 0.0, "y": 0.0, "z": 0.0}
        v_mag = math.sqrt(MU / r_mag)
        # Perpendicular to position in orbital plane
        lon_rad = math.atan2(r["y"], r["x"])
        lat_rad = math.radians(lat)
        vx = -v_mag * math.sin(lon_rad)
        vy = v_mag * math.cos(lon_rad)
        vz = 0.0
        return {"x": round(vx, 6), "y": round(vy, 6), "z": round(vz, 6)}

    # ── Simulation Step ───────────────────────────────────────────────────

    def simulate_step(self, dt_seconds: float = 60.0):
        """Advance simulation by dt_seconds."""
        self.sim_time += timedelta(seconds=dt_seconds)

        # Propagate satellite positions (simple Kepler drift)
        for sat_id, sat in self.satellites.items():
            if sat.status == "EOL":
                continue

            # Simple longitude drift (orbital period ~95 min for LEO)
            orbital_period = 95 * 60  # seconds
            lon_rate = 360.0 / orbital_period  # deg/s
            inc = 55.0  # assumed inclination

            # Advance true anomaly
            phase_advance = (dt_seconds / orbital_period) * 360.0
            current_phase = math.degrees(math.asin(
                max(-1, min(1, sat.lat / inc))
            )) if abs(inc) > 0.01 else 0

            new_phase = current_phase + phase_advance
            sat.lat = round(inc * math.sin(math.radians(new_phase)), 4)
            sat.lon = round(((sat.lon + lon_rate * dt_seconds + 180) % 360) - 180, 4)

            # Update ECI
            sat.r = self._latlon_to_eci(sat.lat, sat.lon, sat.alt_km)
            sat.v = self._compute_orbital_velocity(sat.r, sat.lat)

            # Fuel consumption
            if sat.status != "NOMINAL":
                sat.fuel_kg = max(0, sat.fuel_kg - random.random() * 0.01)

            sat.last_update = time.time()

        # Drift debris
        for deb in self.debris:
            deb.lon = round(((deb.lon + 0.04 + 180) % 360) - 180, 3)

        # Run conjunction detection
        self._detect_conjunctions()

        # Generate maneuvers for evading satellites
        self._update_maneuvers()

    def _detect_conjunctions(self):
        """Simple miss-distance calculation for CDMs."""
        self.cdms.clear()
        rng = random.Random(int(self.sim_time.timestamp()) % 100000)

        sat_list = list(self.satellites.values())
        for sat in sat_list:
            if sat.status == "EOL":
                continue

            # Check against nearby debris (simplified)
            num_threats = 1 if sat.status == "EVADING" else (1 if rng.random() < 0.12 else 0)
            for _ in range(num_threats):
                deb_idx = rng.randint(0, len(self.debris) - 1)
                deb = self.debris[deb_idx]

                # Compute rough miss distance
                if rng.random() < 0.25:
                    miss_km = rng.random() * 0.1  # critical
                elif rng.random() < 0.5:
                    miss_km = rng.random() * 2.0  # warning
                else:
                    miss_km = 2.0 + rng.random() * 10.0  # advisory

                tca = self.sim_time + timedelta(hours=rng.random() * 20)

                self.cdms.append(CDMRecord(
                    satelliteId=sat.id,
                    debrisId=deb.id,
                    tca=tca.isoformat(),
                    missDistance=round(miss_km, 4),
                    probability=round(
                        (0.01 + rng.random() * 0.05) if miss_km < 0.1
                        else rng.random() * 0.001, 6
                    ),
                ))

        # Generate alerts for critical CDMs
        for cdm in self.cdms:
            if cdm.missDistance < 0.1:
                self._add_alert(
                    "CONJUNCTION",
                    "CRITICAL",
                    f"Critical conjunction: {cdm.satelliteId} vs {cdm.debrisId} "
                    f"— miss {cdm.missDistance*1000:.0f}m at {cdm.tca[:19]}Z",
                    cdm.satelliteId,
                )

    def _update_maneuvers(self):
        """Generate maneuver records for active burns."""
        self.maneuvers.clear()
        rng = random.Random(int(self.sim_time.timestamp()) % 50000)

        active_sats = [s for s in self.satellites.values()
                       if s.status != "EOL"][:8]

        for sat in active_sats:
            burn_count = 1 + int(rng.random() * 3)
            offset = -2 + rng.random() * 2

            for i in range(burn_count):
                burn_time = self.sim_time + timedelta(hours=offset)
                duration = 120 + rng.random() * 300
                burn_type = ("EVASION BURN" if i == 0
                             else ("COOLDOWN" if i == 1
                                   else "RECOVERY BURN"))

                self.maneuvers.append(ManeuverRecord(
                    satelliteId=sat.id,
                    burnId=f"BURN-{sat.id}-{i}",
                    burnTime=burn_time.isoformat(),
                    duration=round(duration, 1),
                    type=burn_type,
                    deltaV={"x": 0.002, "y": 0, "z": 0},
                    status="EXECUTED" if offset < 0 else "PENDING",
                    fuelCost=round(0.1 + rng.random() * 0.5, 3),
                ))

                offset += (duration + 600) / 3600

    # ── Alerts ────────────────────────────────────────────────────────────

    def _add_alert(self, alert_type: str, severity: str, message: str,
                   satellite_id: str):
        """Add a new alert to the store."""
        self._alert_counter += 1
        self.alerts.insert(0, AlertRecord(
            id=self._alert_counter,
            type=alert_type,
            severity=severity,
            message=message,
            satelliteId=satellite_id,
            timestamp=self.sim_time.isoformat(),
        ))
        # Keep last 200 alerts
        if len(self.alerts) > 200:
            self.alerts = self.alerts[:200]

    # ── Telemetry Ingestion ───────────────────────────────────────────────

    def ingest_telemetry(self, sat_id: str, telemetry: dict):
        """Ingest real-time telemetry for a satellite."""
        sat = self.satellites.get(sat_id)
        if not sat:
            return False

        if "lat" in telemetry:
            sat.lat = telemetry["lat"]
        if "lon" in telemetry:
            sat.lon = telemetry["lon"]
        if "alt_km" in telemetry:
            sat.alt_km = telemetry["alt_km"]
        if "fuel_kg" in telemetry:
            sat.fuel_kg = telemetry["fuel_kg"]
        if "status" in telemetry:
            sat.status = telemetry["status"]

        sat.r = self._latlon_to_eci(sat.lat, sat.lon, sat.alt_km)
        sat.v = self._compute_orbital_velocity(sat.r, sat.lat)
        sat.last_update = time.time()

        return True

    # ── Maneuver Commands ─────────────────────────────────────────────────

    def execute_maneuver(self, sat_id: str, delta_v: dict, burn_duration: float):
        """Execute a maneuver command on a satellite."""
        sat = self.satellites.get(sat_id)
        if not sat:
            return {"error": f"Satellite {sat_id} not found"}

        if sat.status == "EOL":
            return {"error": f"Satellite {sat_id} is EOL — cannot maneuver"}

        # Compute fuel cost (Tsiolkovsky)
        dv_mag = math.sqrt(delta_v.get("x", 0)**2 +
                           delta_v.get("y", 0)**2 +
                           delta_v.get("z", 0)**2)
        mass = 500.0  # kg
        isp = 300.0   # s
        g0 = 9.80665
        fuel_cost = mass * (1 - math.exp(-abs(dv_mag) / (isp * g0)))

        if fuel_cost > sat.fuel_kg:
            return {"error": f"Insufficient fuel: need {fuel_cost:.3f} kg, have {sat.fuel_kg:.3f} kg"}

        # Apply maneuver
        sat.fuel_kg -= fuel_cost
        sat.status = "EVADING"
        self.total_dv_ms += dv_mag * 1000  # km/s -> m/s

        # Record maneuver
        maneuver = ManeuverRecord(
            satelliteId=sat_id,
            burnId=f"CMD-{sat_id}-{int(time.time())}",
            burnTime=self.sim_time.isoformat(),
            duration=burn_duration,
            type="COMMANDED BURN",
            deltaV=delta_v,
            status="EXECUTING",
            fuelCost=round(fuel_cost, 4),
        )
        self.maneuvers.append(maneuver)

        self._add_alert(
            "MANEUVER",
            "INFO",
            f"Maneuver commanded: {sat_id} — ΔV={dv_mag*1000:.1f} m/s, "
            f"fuel={fuel_cost:.3f} kg",
            sat_id,
        )

        return {
            "status": "OK",
            "maneuver": maneuver.to_dict(),
            "fuel_remaining": round(sat.fuel_kg, 3),
        }

    # ── Snapshot Builder ──────────────────────────────────────────────────

    def get_snapshot(self) -> dict:
        """Build a full snapshot for the dashboard."""
        return {
            "timestamp": self.sim_time.isoformat(),
            "satellites": [s.to_dict() for s in self.satellites.values()],
            "debris_cloud": [d.to_tuple() for d in self.debris],
            "cdms": [c.to_dict() for c in self.cdms],
            "maneuvers": [m.to_dict() for m in self.maneuvers],
        }

    def get_stats(self) -> dict:
        """Get constellation statistics."""
        sats = list(self.satellites.values())
        active = [s for s in sats if s.status != "EOL"]
        evading = [s for s in sats if s.status == "EVADING"]
        recovering = [s for s in sats if s.status == "RECOVERING"]

        total_fuel = sum(s.fuel_kg for s in sats)
        avg_fuel = total_fuel / len(sats) if sats else 0

        critical_cdms = [c for c in self.cdms if c.missDistance < 0.1]

        return {
            "satellites": {
                "total": len(sats),
                "active": len(active),
                "evading": len(evading),
                "recovering": len(recovering),
                "eol": len(sats) - len(active),
            },
            "fuel": {
                "total_kg": round(total_fuel, 2),
                "avg_kg": round(avg_fuel, 2),
            },
            "conjunctions": {
                "total_raised": len(self.cdms),
                "critical": len(critical_cdms),
            },
            "maneuvers": {
                "total": len(self.maneuvers),
                "total_dv_ms": round(self.total_dv_ms, 3),
            },
            "debris_tracked": len(self.debris),
            "sim_time": self.sim_time.isoformat(),
        }

    def get_alerts_since(self, after_id: int) -> List[dict]:
        """Get alerts with id > after_id."""
        if after_id <= 0:
            return [a.to_dict() for a in self.alerts[:50]]
        return [a.to_dict() for a in self.alerts if a.id > after_id]

    # ── WebSocket Client Management ───────────────────────────────────────

    def register_ws(self, ws):
        self._ws_clients.add(ws)

    def unregister_ws(self, ws):
        self._ws_clients.discard(ws)

    @property
    def ws_clients(self):
        return self._ws_clients


# ── Module-level singleton ─────────────────────────────────────────────────
state = StateManager()
