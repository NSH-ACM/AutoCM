'use strict';

/**
 * ════════════════════════════════════════════════════════════════════════
 *  RECOVERY PLANNER  —  src/autonomy/recoveryPlanner.js
 *
 *  After evasion, plans the return burn to the satellite's nominal slot.
 *  Uses ~0.95× inverse of the evasion ΔV, timed at TCA + 90 minutes.
 * ════════════════════════════════════════════════════════════════════════
 */

const {
  COOLDOWN_SECONDS,
  SIGNAL_LATENCY_S,
  computeFuelConsumed,
} = require('../utils/orbital');

// ── Constants ──────────────────────────────────────────────────────────────────
const RECOVERY_DELAY_S      = 90 * 60;    // TCA + 90 min (one full orbit)
const RECOVERY_SCALE_FACTOR = 0.95;       // Slightly less than full reversal
const MIN_RECOVERY_DELAY_S  = 10 * 60;    // At least 10 min after TCA

/**
 * planRecovery(satellite, tcaDate, evasionBurn)
 *
 * Calculates the return burn to re-enter nominal slot.
 * Recovery ΔV ≈ -0.95 × evasion ΔV (accounts for orbital drift).
 *
 * @param {object}  satellite    — satellite state
 * @param {Date}    tcaDate      — TCA of the conjunction
 * @param {object}  evasionBurn  — the evasion burn { burnTime, deltaV_ECI, ... }
 * @returns {object} { burnTime, deltaV_ECI, dvMagnitudeMs, fuelCostKg }
 */
function planRecovery(satellite, tcaDate, evasionBurn) {
  // ── Timing ────────────────────────────────────────────────────────────────
  // Recovery burn at TCA + 90 minutes (one full LEO orbit)
  let recoveryMs = tcaDate.getTime() + RECOVERY_DELAY_S * 1000;

  // Ensure cooldown from evasion burn is respected
  const evasionBurnMs = evasionBurn.burnTime.getTime();
  const cooldownEndMs = evasionBurnMs + COOLDOWN_SECONDS * 1000;

  if (recoveryMs < cooldownEndMs) {
    recoveryMs = cooldownEndMs + SIGNAL_LATENCY_S * 1000;
  }

  // Minimum delay from TCA
  const minRecoveryMs = tcaDate.getTime() + MIN_RECOVERY_DELAY_S * 1000;
  recoveryMs = Math.max(recoveryMs, minRecoveryMs);

  const burnTime = new Date(recoveryMs);

  // ── ΔV Calculation ────────────────────────────────────────────────────────
  // Approximate reversal: -0.95× the evasion ΔV
  // The 0.95 scaling accounts for orbital drift during the evasion period.
  // A perfect reversal would overshoot due to the changed orbital elements.
  const evDV = evasionBurn.deltaV_ECI;
  const recoveryDV = {
    x: -evDV.x * RECOVERY_SCALE_FACTOR,
    y: -evDV.y * RECOVERY_SCALE_FACTOR,
    z: -evDV.z * RECOVERY_SCALE_FACTOR,
  };

  // ── Fuel cost ─────────────────────────────────────────────────────────────
  const dvMs = Math.sqrt(
    recoveryDV.x * recoveryDV.x +
    recoveryDV.y * recoveryDV.y +
    recoveryDV.z * recoveryDV.z
  ) * 1000;

  const fuelCostKg = computeFuelConsumed(satellite.currentMass, dvMs);

  return {
    burnTime,
    deltaV_ECI: recoveryDV,
    dvMagnitudeMs: dvMs,
    fuelCostKg,
  };
}

module.exports = { planRecovery };
