'use strict';

/**
 * ════════════════════════════════════════════════════════════════════════
 *  EVASION PLANNER  —  src/autonomy/evasionPlanner.js
 *
 *  Calculates minimum-ΔV evasion burns in RTN frame, converts to ECI.
 *  Preference order: Prograde → Retrograde → Radial → Normal (cheapest first).
 * ════════════════════════════════════════════════════════════════════════
 */

const {
  computeFuelConsumed,
  SIGNAL_LATENCY_S,
  COOLDOWN_SECONDS,
  MAX_DELTA_V_MS,
} = require('../utils/orbital');

// ── Constants ──────────────────────────────────────────────────────────────────
const COLLISION_THRESHOLD_KM = 0.1;   // 100 m
const SAFETY_MARGIN_KM       = 0.2;   // Target 200 m miss (2× safety)
const TCA_MARGIN_S           = 60;    // Don't burn within 60s of TCA
const MIN_DV_KMS             = 0.010; // 10 m/s — initial test
const DV_STEP_KMS            = 0.002; // 2 m/s — step up size
const MAX_DV_KMS             = MAX_DELTA_V_MS / 1000; // 0.015 km/s cap
const HALF_ORBIT_S           = 45 * 60; // ~45 min (half of ~90 min LEO period)

// ── Vector Math (inlined for zero-allocation performance) ──────────────────────

function cross(a, b) {
  return {
    x: a.y * b.z - a.z * b.y,
    y: a.z * b.x - a.x * b.z,
    z: a.x * b.y - a.y * b.x,
  };
}

function dot(a, b) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function magnitude(v) {
  return Math.sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
}

function scale(v, s) {
  return { x: v.x * s, y: v.y * s, z: v.z * s };
}

function add(a, b) {
  return { x: a.x + b.x, y: a.y + b.y, z: a.z + b.z };
}

function subtract(a, b) {
  return { x: a.x - b.x, y: a.y - b.y, z: a.z - b.z };
}

function normalize(v) {
  const m = magnitude(v);
  if (m < 1e-15) return { x: 0, y: 0, z: 0 };
  return { x: v.x / m, y: v.y / m, z: v.z / m };
}

// ── RTN Frame ──────────────────────────────────────────────────────────────────

/**
 * Compute RTN (Radial-Transverse-Normal) unit vectors from ECI state.
 * R = radial outward, T = along-track (prograde), N = orbit normal.
 */
function getRTNFrame(r_eci, v_eci) {
  const R_hat = normalize(r_eci);
  const N_raw = cross(r_eci, v_eci);
  const N_hat = normalize(N_raw);
  const T_hat = cross(N_hat, R_hat);
  return { R_hat, T_hat, N_hat };
}

/**
 * Convert RTN ΔV components to ECI vector.
 */
function rtnToECI(dv_R, dv_T, dv_N, R_hat, T_hat, N_hat) {
  return {
    x: dv_R * R_hat.x + dv_T * T_hat.x + dv_N * N_hat.x,
    y: dv_R * R_hat.y + dv_T * T_hat.y + dv_N * N_hat.y,
    z: dv_R * R_hat.z + dv_T * T_hat.z + dv_N * N_hat.z,
  };
}

// ── Miss Distance Estimation ──────────────────────────────────────────────────

/**
 * Linear TCA miss distance estimate.
 * Given current relative state, estimates miss distance at closest approach.
 * This is O(1) and avoids calling the full RK4 propagator.
 */
function estimateMissDistance(satR, satV, debR, debV) {
  const relPos = subtract(satR, debR);
  const relVel = subtract(satV, debV);
  const relSpeed2 = dot(relVel, relVel);

  if (relSpeed2 < 1e-18) {
    // Parallel trajectories — distance is constant
    return magnitude(relPos);
  }

  const tcaSec = -dot(relPos, relVel) / relSpeed2;
  const missVec = add(relPos, scale(relVel, Math.max(0, tcaSec)));
  return magnitude(missVec);
}

/**
 * Estimate miss distance after applying a ΔV perturbation to the satellite.
 */
function estimateMissWithDV(satR, satV, debR, debV, dvECI) {
  const newV = add(satV, dvECI);
  return estimateMissDistance(satR, newV, debR, debV);
}

// ── Burn Timing ───────────────────────────────────────────────────────────────

/**
 * Determine the optimal burn time given constraints.
 */
function computeBurnTime(satellite, tcaDate, currentSimTime) {
  const nowMs  = currentSimTime.getTime();
  const tcaMs  = tcaDate.getTime();

  // Earliest possible burn: now + signal latency
  let earliestMs = nowMs + SIGNAL_LATENCY_S * 1000;

  // Cooldown constraint: lastBurnTime + 600s
  if (satellite.lastBurnTime) {
    const cooldownEnd = satellite.lastBurnTime.getTime() + COOLDOWN_SECONDS * 1000;
    earliestMs = Math.max(earliestMs, cooldownEnd);
  }

  // Latest possible burn: 60s before TCA
  const latestMs = tcaMs - TCA_MARGIN_S * 1000;

  if (earliestMs >= latestMs) {
    return null; // No valid burn window
  }

  // Optimal: half-orbit before TCA for transverse burns (most efficient)
  const optimalMs = tcaMs - HALF_ORBIT_S * 1000;

  // Clamp to valid window
  const burnMs = Math.max(earliestMs, Math.min(optimalMs, latestMs));

  return new Date(burnMs);
}

// ── Main Planner ──────────────────────────────────────────────────────────────

/**
 * planEvasion(satellite, debris, tcaDate, currentSimTime)
 *
 * Calculates the minimum-ΔV burn that pushes miss distance beyond 200m (2× safety).
 * Tries prograde first, then retrograde, radial, and finally out-of-plane.
 *
 * @param {object} satellite — satellite state from constellation
 * @param {object} debris    — debris state from constellation
 * @param {Date}   tcaDate   — predicted time of closest approach
 * @param {Date}   currentSimTime
 * @returns {object|null} { burnTime, deltaV_ECI, dvMagnitudeMs, fuelCostKg, strategy }
 */
function planEvasion(satellite, debris, tcaDate, currentSimTime) {
  // ── Step 1: Compute burn time ───────────────────────────────────────────
  const burnTime = computeBurnTime(satellite, tcaDate, currentSimTime);
  if (!burnTime) {
    console.log(`[ACM] No valid burn window for ${satellite.id} — skipping`);
    return null;
  }

  // ── Step 2: Get RTN frame ───────────────────────────────────────────────
  const { R_hat, T_hat, N_hat } = getRTNFrame(satellite.r, satellite.v);

  // ── Step 3: Try burn strategies in order of efficiency ──────────────────
  const strategies = [
    { name: 'PROGRADE',   dir: T_hat,          sign: +1 },
    { name: 'RETROGRADE', dir: T_hat,          sign: -1 },
    { name: 'RADIAL_OUT', dir: R_hat,          sign: +1 },
    { name: 'RADIAL_IN',  dir: R_hat,          sign: -1 },
    { name: 'NORMAL_POS', dir: N_hat,          sign: +1 },
    { name: 'NORMAL_NEG', dir: N_hat,          sign: -1 },
  ];

  for (const strat of strategies) {
    const result = tryStrategy(
      satellite, debris, strat.dir, strat.sign, strat.name, burnTime
    );
    if (result) return result;
  }

  // All strategies failed
  console.log(`[ACM] WARNING: No valid evasion strategy found for ${satellite.id}`);
  return null;
}

/**
 * Try a specific burn direction/sign, scaling ΔV from minimum up to max.
 * Returns the burn parameters if successful, null otherwise.
 */
function tryStrategy(satellite, debris, dir, sign, strategyName, burnTime) {
  const isNormal = strategyName.startsWith('NORMAL');

  // Start small, scale up
  let dvMag = MIN_DV_KMS;

  while (dvMag <= MAX_DV_KMS) {
    // Build ΔV vector in ECI
    const dvECI = {
      x: sign * dvMag * dir.x,
      y: sign * dvMag * dir.y,
      z: sign * dvMag * dir.z,
    };

    // Estimate post-burn miss distance
    const newMiss = estimateMissWithDV(
      satellite.r, satellite.v, debris.r, debris.v, dvECI
    );

    if (newMiss >= SAFETY_MARGIN_KM) {
      // Check fuel sufficiency
      const dvMs = dvMag * 1000; // km/s → m/s
      const fuelCostKg = computeFuelConsumed(satellite.currentMass, dvMs);

      if (fuelCostKg > satellite.fuelKg) {
        // Not enough fuel for this strategy at this ΔV
        return null;
      }

      if (isNormal) {
        console.log(`[ACM] WARNING: Plane change burn required for ${satellite.id} — high fuel cost`);
      }

      return {
        burnTime,
        deltaV_ECI: dvECI,
        dvMagnitudeMs: dvMs,
        fuelCostKg,
        strategy: strategyName,
      };
    }

    dvMag += DV_STEP_KMS;
  }

  return null; // This strategy can't create enough separation
}

module.exports = { planEvasion, getRTNFrame, rtnToECI, estimateMissDistance };
