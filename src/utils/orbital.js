'use strict';

// ════════════════════════════════════════════════════════════
//  Orbital Utilities
//  All math used by the API layer that does NOT require
//  numerical integration (that stays in physics/interface.js)
// ════════════════════════════════════════════════════════════

// ─── Physical / Mission Constants ────────────────────────────────────────────
const ISP                  = 300.0;   // Specific impulse (s)
const G0                   = 9.80665; // Standard gravity (m/s²)
const RE                   = 6378.137;// Earth equatorial radius (km)
const MAX_DELTA_V_MS       = 15.0;    // Max ΔV per single burn (m/s)
const COOLDOWN_SECONDS     = 600;     // Mandatory thruster rest period (s)
const SIGNAL_LATENCY_S     = 10;      // Ground-to-satellite uplink latency (s)
const INITIAL_FUEL_KG      = 50.0;    // Starting propellant mass (kg)
const EOL_FUEL_THRESHOLD_KG = INITIAL_FUEL_KG * 0.05; // 2.5 kg — triggers EOL

// ─── Tsiolkovsky Rocket Equation ─────────────────────────────────────────────

/**
 * Computes the propellant mass consumed for a single impulsive burn.
 *
 * Formula: Δm = m_current × (1 − e^(−|Δv| / (Isp × g0)))
 *
 * @param {number} currentMassKg — satellite's current total mass (kg)
 * @param {number} deltaVMs      — magnitude of ΔV in m/s
 * @returns {number} propellant consumed in kg
 */
function computeFuelConsumed(currentMassKg, deltaVMs) {
  return currentMassKg * (1.0 - Math.exp(-deltaVMs / (ISP * G0)));
}

// ─── ΔV Helpers ──────────────────────────────────────────────────────────────

/**
 * Returns the Euclidean magnitude of a ΔV vector given in km/s, converted to m/s.
 * @param {{ x: number, y: number, z: number }} dv — km/s
 * @returns {number} magnitude in m/s
 */
function deltaVMagnitudeMs(dv) {
  return Math.sqrt(dv.x * dv.x + dv.y * dv.y + dv.z * dv.z) * 1000.0;
}

// ─── Time / Date Helpers ──────────────────────────────────────────────────────

/**
 * Converts a JavaScript Date to Julian Date.
 * @param {Date} date
 * @returns {number}
 */
function toJulianDate(date) {
  return date.getTime() / 86400000.0 + 2440587.5;
}

/**
 * Greenwich Mean Sidereal Time in radians from a Julian Date.
 * Uses the IAU 1982 formula.
 * @param {number} jd — Julian Date
 * @returns {number} GMST in radians
 */
function gmstFromJD(jd) {
  const T = (jd - 2451545.0) / 36525.0; // Julian centuries from J2000.0
  let gmstDeg =
    280.46061837 +
    360.98564736629 * (jd - 2451545.0) +
    0.000387933 * T * T -
    (T * T * T) / 38710000.0;
  // Normalise to [0°, 360°)
  gmstDeg = ((gmstDeg % 360.0) + 360.0) % 360.0;
  return gmstDeg * (Math.PI / 180.0);
}

// ─── Coordinate Conversion ────────────────────────────────────────────────────

/**
 * Converts an ECI position vector to geodetic coordinates.
 *
 * Steps:
 *   1. ECI → ECEF  (Z-axis rotation by GMST — accounts for Earth's rotation)
 *   2. ECEF → geodetic  (spherical Earth approximation; sufficient for visualization)
 *
 * @param {{ x: number, y: number, z: number }} r — ECI position in km
 * @param {Date} atTime — time at which the position is valid (needed for GMST)
 * @returns {{ lat: number, lon: number, altKm: number }}
 *          lat/lon in decimal degrees, altKm = altitude above spherical Earth
 */
function eciToGeodetic(r, atTime) {
  const jd   = toJulianDate(atTime);
  const gmst = gmstFromJD(jd);
  const cosG = Math.cos(gmst);
  const sinG = Math.sin(gmst);

  // ECI → ECEF rotation
  const xEcef =  r.x * cosG + r.y * sinG;
  const yEcef = -r.x * sinG + r.y * cosG;
  const zEcef =  r.z;

  // ECEF → geodetic (spherical)
  const lon   = Math.atan2(yEcef, xEcef) * (180.0 / Math.PI);
  const p     = Math.sqrt(xEcef * xEcef + yEcef * yEcef);
  const lat   = Math.atan2(zEcef, p) * (180.0 / Math.PI);
  const altKm = Math.sqrt(r.x * r.x + r.y * r.y + r.z * r.z) - RE;

  return { lat, lon, altKm };
}

// ─── Station-Keeping ─────────────────────────────────────────────────────────

/**
 * Compute semi-major axis from ECI state vector using vis-viva equation.
 * @param {{ x,y,z }} r — position in km
 * @param {{ x,y,z }} v — velocity in km/s
 * @returns {number} semi-major axis in km
 */
function computeSMA(r, v) {
  const MU = 398600.4418;
  const rMag = Math.sqrt(r.x * r.x + r.y * r.y + r.z * r.z);
  const v2 = v.x * v.x + v.y * v.y + v.z * v.z;
  // vis-viva: v² = μ(2/r - 1/a)  →  1/a = 2/r - v²/μ
  const oneOverA = (2 / rMag) - (v2 / MU);
  if (Math.abs(oneOverA) < 1e-15) return Infinity;
  return 1 / oneOverA;
}

/**
 * Station-keeping distance based on orbital element difference.
 * Compares semi-major axis difference (altitude offset) which is
 * invariant across the orbit, unlike raw ECI coordinates which rotate.
 *
 * If velocity data is unavailable on the nominal slot, falls back to
 * a simple altitude comparison using position magnitude.
 *
 * @param {{ x,y,z }} currentR — current ECI position (km)
 * @param {{ x,y,z }} nominalR — nominal slot ECI position (km)
 * @param {{ x,y,z }} [currentV] — current ECI velocity (km/s)
 * @param {{ x,y,z }} [nominalV] — nominal slot ECI velocity (km/s)
 * @returns {number} effective offset in km
 */
function stationKeepingDistance(currentR, nominalR, currentV, nominalV) {
  // If velocities are available, compare semi-major axes (robust)
  if (currentV && nominalV) {
    const currentSMA = computeSMA(currentR, currentV);
    const nominalSMA = computeSMA(nominalR, nominalV);
    return Math.abs(currentSMA - nominalSMA);
  }
  // Fallback: compare orbital radii (altitude proxy)
  const rCurrent = Math.sqrt(currentR.x * currentR.x + currentR.y * currentR.y + currentR.z * currentR.z);
  const rNominal = Math.sqrt(nominalR.x * nominalR.x + nominalR.y * nominalR.y + nominalR.z * nominalR.z);
  return Math.abs(rCurrent - rNominal);
}

module.exports = {
  // Constants
  ISP,
  G0,
  RE,
  MAX_DELTA_V_MS,
  COOLDOWN_SECONDS,
  SIGNAL_LATENCY_S,
  INITIAL_FUEL_KG,
  EOL_FUEL_THRESHOLD_KG,
  // Functions
  computeFuelConsumed,
  deltaVMagnitudeMs,
  toJulianDate,
  gmstFromJD,
  eciToGeodetic,
  stationKeepingDistance,
  computeSMA,
};
