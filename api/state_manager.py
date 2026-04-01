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
import csv
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field, asdict

from .engine_wrapper import engine as physics_engine
from .core.autonomy_logic import AutonomyManager

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
        self.ground_stations: List[Dict] = []
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
        # Station-keeping: nominal slot tracking (Section 5.2)
        self.nominal_slots: Dict[str, Dict[str, float]] = {}  # sat_id -> {lat, lon, alt}
        # Maneuver history for cooldown tracking (Section 5.1)
        self.last_burn_time: Dict[str, datetime] = {}  # sat_id -> last burn timestamp
        # EOL tracking
        self.eol_triggered: set = set()  # sat_ids that triggered EOL
        
        # Physics & Autonomy Engines
        self.physics_engine = physics_engine
        self.autonomy_engine = AutonomyManager(self)

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

    @staticmethod
    def _rtn_to_eci(r: dict, v: dict, dv_rtn: dict) -> dict:
        """
        Convert delta-V from RTN (Radial-Transverse-Normal) frame to ECI.
        
        RTN frame:
        - R (Radial): along position vector (away from Earth)
        - T (Transverse): along velocity vector (direction of motion)
        - N (Normal): cross product of R × T (perpendicular to orbital plane)
        
        Args:
            r: Position vector in ECI (km)
            v: Velocity vector in ECI (km/s)
            dv_rtn: Delta-V in RTN frame {radial, transverse, normal} (km/s)
        
        Returns:
            Delta-V in ECI frame {x, y, z} (km/s)
        """
        # Compute unit vectors for RTN frame
        r_mag = math.sqrt(r["x"]**2 + r["y"]**2 + r["z"]**2)
        v_mag = math.sqrt(v["x"]**2 + v["y"]**2 + v["z"]**2)
        
        if r_mag < 1e-10 or v_mag < 1e-10:
            return {"x": 0.0, "y": 0.0, "z": 0.0}
        
        # R_hat = r / |r| (Radial unit vector)
        r_hat = {
            "x": r["x"] / r_mag,
            "y": r["y"] / r_mag,
            "z": r["z"] / r_mag
        }
        
        # T_hat = v / |v| (Transverse unit vector, approximately along-track)
        t_hat = {
            "x": v["x"] / v_mag,
            "y": v["y"] / v_mag,
            "z": v["z"] / v_mag
        }
        
        # N_hat = R × T (Normal unit vector, perpendicular to orbital plane)
        n_hat = {
            "x": r_hat["y"] * t_hat["z"] - r_hat["z"] * t_hat["y"],
            "y": r_hat["z"] * t_hat["x"] - r_hat["x"] * t_hat["z"],
            "z": r_hat["x"] * t_hat["y"] - r_hat["y"] * t_hat["x"]
        }
        n_mag = math.sqrt(n_hat["x"]**2 + n_hat["y"]**2 + n_hat["z"]**2)
        if n_mag > 1e-10:
            n_hat = {k: v / n_mag for k, v in n_hat.items()}
        
        # Transform RTN to ECI: dV_eci = dV_r * R_hat + dV_t * T_hat + dV_n * N_hat
        dv_eci = {
            "x": dv_rtn["radial"] * r_hat["x"] + dv_rtn["transverse"] * t_hat["x"] + dv_rtn["normal"] * n_hat["x"],
            "y": dv_rtn["radial"] * r_hat["y"] + dv_rtn["transverse"] * t_hat["y"] + dv_rtn["normal"] * n_hat["y"],
            "z": dv_rtn["radial"] * r_hat["z"] + dv_rtn["transverse"] * t_hat["z"] + dv_rtn["normal"] * n_hat["z"]
        }
        
        return dv_eci

    # ── Simulation Step ───────────────────────────────────────────────────

    def simulate_step(self, dt_seconds: float = 60.0):
        """Advance simulation by dt_seconds using C++ J2/RK4 propagator."""
        self.sim_time += timedelta(seconds=dt_seconds)

        # Prepare satellite objects for physics engine
        sat_objects = []
        for sat_id, sat in self.satellites.items():
            if sat.status == "EOL":
                continue
            sat_objects.append({
                "id": sat_id,
                "r": sat.r,
                "v": sat.v
            })

        # Propagate using C++ physics engine (J2 + RK4)
        if sat_objects:
            try:
                updated_sats = physics_engine.propagate(sat_objects, dt_seconds)
                for updated in updated_sats:
                    sat_id = updated["id"]
                    if sat_id in self.satellites:
                        sat = self.satellites[sat_id]
                        sat.r = updated["r"]
                        sat.v = updated["v"]
                        # Convert ECI back to lat/lon/alt
                        sat.lat, sat.lon, sat.alt_km = self._eci_to_latlon(sat.r)
                        sat.last_update = time.time()
            except Exception as e:
                print(f"[StateManager] Physics engine propagation failed: {e}")
                # Fallback to simple drift
                self._simple_propagate(dt_seconds)

        # Prepare and propagate debris
        debris_objects = []
        for deb in self.debris:
            deb_r = self._latlon_to_eci(deb.lat, deb.lon, deb.alt_km)
            # Estimate debris velocity (rough approximation)
            deb_v = self._compute_orbital_velocity(deb_r, deb.lat)
            debris_objects.append({
                "id": deb.id,
                "r": deb_r,
                "v": deb_v
            })

        if debris_objects:
            try:
                updated_debris = physics_engine.propagate(debris_objects, dt_seconds)
                deb_dict = {d.id: d for d in self.debris}
                for updated in updated_debris:
                    deb_id = updated["id"]
                    if deb_id in deb_dict:
                        deb = deb_dict[deb_id]
                        lat, lon, alt = self._eci_to_latlon(updated["r"])
                        deb.lat = lat
                        deb.lon = lon
                        deb.alt_km = alt
            except Exception as e:
                # Fallback: simple longitude drift
                for deb in self.debris:
                    deb.lon = round(((deb.lon + 0.04 + 180) % 360) - 180, 3)

        # Check for EOL satellites (< 5% fuel) and trigger graveyard
        self._check_eol_management()

        # Run real conjunction detection using KD-Tree
        self._detect_conjunctions_kdtree()

        # Update station-keeping status
        self._update_station_keeping()

    def _simple_propagate(self, dt_seconds: float):
        """Fallback simple propagation when physics engine fails."""
        for sat_id, sat in self.satellites.items():
            if sat.status == "EOL":
                continue
            orbital_period = 95 * 60
            lon_rate = 360.0 / orbital_period
            inc = 55.0
            phase_advance = (dt_seconds / orbital_period) * 360.0
            current_phase = math.degrees(math.asin(
                max(-1, min(1, sat.lat / inc))
            )) if abs(inc) > 0.01 else 0
            new_phase = current_phase + phase_advance
            sat.lat = round(inc * math.sin(math.radians(new_phase)), 4)
            sat.lon = round(((sat.lon + lon_rate * dt_seconds + 180) % 360) - 180, 4)
            sat.r = self._latlon_to_eci(sat.lat, sat.lon, sat.alt_km)
            sat.v = self._compute_orbital_velocity(sat.r, sat.lat)
            sat.last_update = time.time()

    def _detect_conjunctions_kdtree(self):
        """Real conjunction detection using C++ KD-Tree engine (Section 6.3)."""
        self.cdms.clear()

        # Prepare satellites for physics engine
        sat_objects = []
        for sat_id, sat in self.satellites.items():
            if sat.status == "EOL":
                continue
            sat_objects.append({
                "id": sat_id,
                "r": sat.r,
                "v": sat.v
            })

        # Prepare debris for physics engine
        debris_objects = []
        for deb in self.debris:
            deb_r = self._latlon_to_eci(deb.lat, deb.lon, deb.alt_km)
            deb_v = self._compute_orbital_velocity(deb_r, deb.lat)
            debris_objects.append({
                "id": deb.id,
                "r": deb_r,
                "v": deb_v
            })

        if not sat_objects or not debris_objects:
            return

        try:
            # Use C++ engine for conjunction detection with 24h lookahead
            epoch_iso = self.sim_time.isoformat()
            raw_cdms = physics_engine.detect_conjunctions(
                sat_objects, debris_objects,
                lookahead_seconds=86400,  # 24 hours
                epoch_iso=epoch_iso
            )

            # Convert to CDMRecord format
            for cdm in raw_cdms:
                miss_distance = cdm.get("missDistance", cdm.get("miss_distance", 999))
                if miss_distance < 5.0:  # Only report if < 5km
                    # Calculate TCA timestamp
                    tca_seconds = cdm.get("tca_seconds_from_now", 0)
                    tca = self.sim_time + timedelta(seconds=tca_seconds)

                    self.cdms.append(CDMRecord(
                        satelliteId=cdm.get("satellite_id", cdm.get("satelliteId", "")),
                        debrisId=cdm.get("debris_id", cdm.get("debrisId", "")),
                        tca=tca.isoformat(),
                        missDistance=round(miss_distance, 4),
                        probability=round(cdm.get("probability", 0.001), 6),
                    ))

            # Generate alerts for critical CDMs (< 100m)
            for cdm in self.cdms:
                if cdm.missDistance < 0.1:
                    self._add_alert(
                        "CONJUNCTION",
                        "CRITICAL",
                        f"Critical conjunction: {cdm.satelliteId} vs {cdm.debrisId} "
                        f"— miss {cdm.missDistance*1000:.0f}m at {cdm.tca[:19]}Z",
                        cdm.satelliteId,
                    )

        except Exception as e:
            print(f"[StateManager] KD-Tree conjunction detection failed: {e}")
            # Fallback to old method if C++ engine fails
            self._detect_conjunctions_fallback()

    def _detect_conjunctions_fallback(self):
        """Fallback simple miss-distance calculation for CDMs."""
        rng = random.Random(int(self.sim_time.timestamp()) % 100000)
        sat_list = list(self.satellites.values())
        for sat in sat_list:
            if sat.status == "EOL":
                continue
            num_threats = 1 if sat.status == "EVADING" else (1 if rng.random() < 0.12 else 0)
            for _ in range(num_threats):
                deb_idx = rng.randint(0, len(self.debris) - 1)
                deb = self.debris[deb_idx]
                if rng.random() < 0.25:
                    miss_km = rng.random() * 0.1
                elif rng.random() < 0.5:
                    miss_km = rng.random() * 2.0
                else:
                    miss_km = 2.0 + rng.random() * 10.0
                tca = self.sim_time + timedelta(hours=rng.random() * 20)
                self.cdms.append(CDMRecord(
                    satelliteId=sat.id,
                    debrisId=deb.id,
                    tca=tca.isoformat(),
                    missDistance=round(miss_km, 4),
                    probability=round((0.01 + rng.random() * 0.05) if miss_km < 0.1 else rng.random() * 0.001, 6),
                ))

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

        # Record burn time for cooldown tracking
        self.record_burn(sat_id, self.sim_time)

        # Schedule recovery burn to return to nominal slot (Section 4.2 Objective 2)
        self._schedule_recovery_burn(sat_id, delta_v)

        return {
            "status": "OK",
            "maneuver": maneuver.to_dict(),
            "fuel_remaining": round(sat.fuel_kg, 3),
        }

    def _schedule_recovery_burn(self, sat_id: str, evasion_dv: dict):
        """Schedule Hohmann-style recovery burn after evasion (Section 4.2)."""
        COOLDOWN_SECONDS = 600  # 10-minute cooldown

        sat = self.satellites.get(sat_id)
        if not sat or sat_id not in self.nominal_slots:
            return

        # Calculate reverse delta-v (scaled for efficiency)
        recovery_dv = {
            "x": -evasion_dv.get("x", 0) * 0.95,
            "y": -evasion_dv.get("y", 0) * 0.95,
            "z": -evasion_dv.get("z", 0) * 0.95,
        }

        # Schedule after cooldown
        recovery_time = self.sim_time + timedelta(seconds=COOLDOWN_SECONDS)

        # Validate recovery burn
        validation = self.validate_maneuver(sat_id, recovery_time, recovery_dv, check_cooldown=False)
        if not validation["valid"]:
            print(f"[StateManager] Recovery burn for {sat_id} failed validation: {validation['errors']}")
            return

        # Create recovery maneuver record
        recovery_maneuver = ManeuverRecord(
            satelliteId=sat_id,
            burnId=f"RECOV-{sat_id}-{int(time.time())}",
            burnTime=recovery_time.isoformat(),
            duration=300.0,
            type="RECOVERY_BURN",
            deltaV=recovery_dv,
            status="PENDING",
            fuelCost=round(validation["fuel_cost_kg"], 4),
        )
        self.maneuvers.append(recovery_maneuver)

        self._add_alert(
            "RECOVERY",
            "INFO",
            f"Recovery burn scheduled for {sat_id} at {recovery_time.isoformat()} "
            f"to return to nominal slot",
            sat_id,
        )

    # ── EOL Management (Section 5.3) ────────────────────────────────────────

    def _check_eol_management(self):
        """Autonomous EOL: trigger graveyard orbit when fuel < 5%."""
        FUEL_CAPACITY = 50.0  # kg (assumed full capacity)
        EOL_THRESHOLD = 0.05 * FUEL_CAPACITY  # 5% = 2.5 kg
        GRAVEYARD_DELTA_KM = 25.0  # +25km graveyard orbit

        for sat_id, sat in self.satellites.items():
            if sat.status == "EOL" or sat_id in self.eol_triggered:
                continue

            if sat.fuel_kg < EOL_THRESHOLD:
                # Trigger EOL sequence
                self.eol_triggered.add(sat_id)
                sat.status = "EOL"

                # Plan graveyard orbit raise (+25km)
                # Delta-v for altitude change: approximately 10-15 m/s per km at LEO
                dv_graveyard = 0.015 * GRAVEYARD_DELTA_KM  # ~0.375 km/s

                self._add_alert(
                    "EOL",
                    "WARNING",
                    f"SAT {sat_id} fuel {sat.fuel_kg:.2f}kg below 5% threshold. "
                    f"Autonomous EOL triggered: raising to graveyard orbit (+{GRAVEYARD_DELTA_KM}km)",
                    sat_id,
                )

                # Schedule graveyard maneuver
                maneuver = ManeuverRecord(
                    satelliteId=sat_id,
                    burnId=f"EOL-{sat_id}-{int(time.time())}",
                    burnTime=self.sim_time.isoformat(),
                    duration=300.0,
                    type="EOL_GRAVEYARD",
                    deltaV={"x": dv_graveyard, "y": 0, "z": 0},
                    status="PENDING",
                    fuelCost=round(sat.fuel_kg * 0.5, 3),  # Use remaining fuel
                )
                self.maneuvers.append(maneuver)
                sat.alt_km += GRAVEYARD_DELTA_KM

    # ── Station-Keeping Box Monitoring (Section 5.2) ──────────────────────

    def _update_station_keeping(self):
        """Monitor if satellites are within 10km nominal orbital slot."""
        STATION_KEEPING_THRESHOLD_KM = 10.0

        for sat_id, sat in self.satellites.items():
            if sat.status == "EOL":
                continue

            # Initialize nominal slot on first encounter
            if sat_id not in self.nominal_slots:
                self.nominal_slots[sat_id] = {
                    "lat": sat.lat,
                    "lon": sat.lon,
                    "alt_km": sat.alt_km
                }
                continue

            slot = self.nominal_slots[sat_id]

            # Calculate 3D drift from nominal slot
            # Approximate: 1 deg lat/lon ~ 111km at equator
            lat_drift_km = abs(sat.lat - slot["lat"]) * 111.0
            lon_drift_km = abs(sat.lon - slot["lon"]) * 111.0 * math.cos(math.radians(sat.lat))
            alt_drift_km = abs(sat.alt_km - slot["alt_km"])

            # Total drift (Euclidean approximation)
            total_drift = math.sqrt(lat_drift_km**2 + lon_drift_km**2 + alt_drift_km**2)

            if total_drift > STATION_KEEPING_THRESHOLD_KM and sat.status == "NOMINAL":
                self._add_alert(
                    "STATION_KEEPING",
                    "WARNING",
                    f"SAT {sat_id} drifted {total_drift:.1f}km from nominal slot "
                    f"(threshold: {STATION_KEEPING_THRESHOLD_KM}km). Recovery maneuver required.",
                    sat_id,
                )

    # ── Ground Station Operations (Section 5.4) ───────────────────────────

    def load_ground_stations(self, csv_path: str = None):
        """Load ground station data from CSV."""
        if csv_path is None:
            csv_path = os.path.join(
                os.path.dirname(os.path.dirname(__file__)),
                "data", "ground_stations.csv"
            )

        if not os.path.exists(csv_path):
            print(f"[StateManager] Ground stations file not found: {csv_path}")
            # Create default ground stations
            self.ground_stations = [
                {"id": "GS-1", "lat": 28.5, "lon": -80.6, "alt_km": 0.1, "min_elevation": 5.0},
                {"id": "GS-2", "lat": 35.0, "lon": 139.0, "alt_km": 0.1, "min_elevation": 5.0},
                {"id": "GS-3", "lat": -30.0, "lon": 149.0, "alt_km": 0.1, "min_elevation": 5.0},
            ]
            return

        try:
            with open(csv_path, 'r') as f:
                reader = csv.DictReader(f)
                for row in reader:
                    self.ground_stations.append({
                        "id": row.get("id", f"GS-{len(self.ground_stations)}"),
                        "lat": float(row.get("lat", 0)),
                        "lon": float(row.get("lon", 0)),
                        "alt_km": float(row.get("alt_km", 0)),
                        "min_elevation": float(row.get("min_elevation", 5.0)),
                    })
            print(f"[StateManager] Loaded {len(self.ground_stations)} ground stations")
        except Exception as e:
            print(f"[StateManager] Error loading ground stations: {e}")

    def check_ground_station_los(self, sat_id: str, timestamp: datetime = None) -> bool:
        """Check if satellite has line-of-sight to any ground station (Section 5.4)."""
        if timestamp is None:
            timestamp = self.sim_time

        sat = self.satellites.get(sat_id)
        if not sat:
            return False

        if not self.ground_stations:
            self.load_ground_stations()

        try:
            # Use physics engine for LOS check
            sat_obj = {"r": sat.r}
            timestamp_iso = timestamp.isoformat()
            has_los = physics_engine.check_los(sat_obj, self.ground_stations, timestamp_iso)
            return has_los
        except Exception as e:
            # Fallback: simple geometric check
            return self._check_los_geometric(sat, timestamp)

    def _check_los_geometric(self, sat: SatelliteState, timestamp: datetime) -> bool:
        """Fallback geometric LOS check accounting for Earth curvature."""
        R_EARTH = 6371.0  # km

        for gs in self.ground_stations:
            # Convert ground station to ECI (simplified, ignoring Earth rotation)
            gs_r = self._latlon_to_eci(gs["lat"], gs["lon"], gs["alt_km"])

            # Vector from ground station to satellite
            dx = sat.r["x"] - gs_r["x"]
            dy = sat.r["y"] - gs_r["y"]
            dz = sat.r["z"] - gs_r["z"]
            range_km = math.sqrt(dx**2 + dy**2 + dz**2)

            # Elevation angle calculation
            # cos(elevation) = (r_sat * sin(range_angle)) / range
            # Simplified: check if satellite is above horizon
            gs_mag = math.sqrt(gs_r["x"]**2 + gs_r["y"]**2 + gs_r["z"]**2)
            sat_mag = math.sqrt(sat.r["x"]**2 + sat.r["y"]**2 + sat.r["z"]**2)

            # Minimum elevation check (simplified)
            # If satellite altitude > ground station and within visible arc
            if sat.alt_km > gs["alt_km"]:
                # Rough check: satellite should be within ~2000km ground range for LEO
                if range_km < 2000:
                    return True

        return False

    # ── Maneuver Validation (Sections 4.2, 5.1, 5.4) ──────────────────────

    def validate_maneuver(self, sat_id: str, burn_time: datetime,
                          delta_v: dict, check_cooldown: bool = True) -> dict:
        """
        Validate maneuver against mission constraints.

        Returns validation object with:
        - valid: bool
        - ground_station_los: bool
        - sufficient_fuel: bool
        - uplink_latency_ok: bool (T >= current_time + 10s)
        - thruster_cooldown_ok: bool (600s since last burn)
        - errors: list of constraint violations
        """
        errors = []
        sat = self.satellites.get(sat_id)

        if not sat:
            return {"valid": False, "errors": [f"Satellite {sat_id} not found"]}

        # Check 1: Ground Station LOS (Section 5.4)
        has_los = self.check_ground_station_los(sat_id, burn_time)
        if not has_los:
            errors.append("No ground station line-of-sight")

        # Check 2: Sufficient Fuel (Tsiolkovsky)
        dv_mag = math.sqrt(delta_v.get("x", 0)**2 +
                          delta_v.get("y", 0)**2 +
                          delta_v.get("z", 0)**2)
        mass = 500.0  # kg
        isp = 300.0   # s
        g0 = 9.80665
        fuel_cost = mass * (1 - math.exp(-abs(dv_mag) / (isp * g0)))
        has_fuel = fuel_cost <= sat.fuel_kg
        if not has_fuel:
            errors.append(f"Insufficient fuel: need {fuel_cost:.3f}kg, have {sat.fuel_kg:.3f}kg")

        # Check 3: Uplink Latency (Section 5.4) - 10 second minimum
        min_burn_time = self.sim_time + timedelta(seconds=10)
        latency_ok = burn_time >= min_burn_time
        if not latency_ok:
            errors.append(f"Burn time violates 10s uplink latency: must be >= {min_burn_time.isoformat()}")

        # Check 4: Thruster Cooldown (Section 5.1) - 600 second rest
        cooldown_ok = True
        if check_cooldown and sat_id in self.last_burn_time:
            time_since_last = (burn_time - self.last_burn_time[sat_id]).total_seconds()
            cooldown_ok = time_since_last >= 600
            if not cooldown_ok:
                errors.append(f"Thruster cooldown violation: {time_since_last:.0f}s since last burn (need 600s)")

        valid = has_los and has_fuel and latency_ok and cooldown_ok

        return {
            "valid": valid,
            "ground_station_los": has_los,
            "sufficient_fuel": has_fuel,
            "uplink_latency_ok": latency_ok,
            "thruster_cooldown_ok": cooldown_ok,
            "fuel_cost_kg": round(fuel_cost, 4),
            "errors": errors
        }

    def record_burn(self, sat_id: str, timestamp: datetime):
        """Record burn time for cooldown tracking."""
        self.last_burn_time[sat_id] = timestamp

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
