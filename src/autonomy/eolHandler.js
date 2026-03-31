'use strict';

/**
 * ════════════════════════════════════════════════════════════════════════
 *  EOL HANDLER  —  src/autonomy/eolHandler.js
 *
 *  Handles end-of-life satellites by scheduling graveyard/deorbit burns.
 *  For LEO, a small retrograde burn lowers perigee into the atmosphere.
 * ════════════════════════════════════════════════════════════════════════
 */

const maneuverQueue  = require('../state/maneuverQueue');
const {
  computeFuelConsumed,
  SIGNAL_LATENCY_S,
} = require('../utils/orbital');
const { getRTNFrame } = require('./evasionPlanner');

// ── Constants ──────────────────────────────────────────────────────────────────
const DEORBIT_DV_KMS   = 0.010;  // 10 m/s retrograde — lowers perigee to drag regime
const SCHEDULE_DELAY_S = SIGNAL_LATENCY_S + 30; // Signal latency + 30s buffer

/**
 * scheduleGraveyardOrbit(satellite, currentSimTime)
 *
 * Schedules a retrograde deorbit burn to lower perigee.
 * Uses remaining fuel (partial burn if insufficient for full 10 m/s).
 *
 * @param {object} satellite     — satellite state object
 * @param {Date}   currentSimTime — current simulation time
 */
async function scheduleGraveyardOrbit(satellite, currentSimTime) {
  // ── Check: already has a pending burn? ──────────────────────────────────
  const pendingBurns = maneuverQueue.getBurnsBySatellite(satellite.id);
  if (pendingBurns.length > 0) {
    return; // Don't double-schedule
  }

  // ── Compute RTN frame ──────────────────────────────────────────────────
  const { T_hat } = getRTNFrame(satellite.r, satellite.v);

  // ── Determine available ΔV ─────────────────────────────────────────────
  let dvKms = DEORBIT_DV_KMS;
  let dvMs  = dvKms * 1000;
  let fuelNeeded = computeFuelConsumed(satellite.currentMass, dvMs);

  // If not enough fuel for full deorbit, use what's left
  if (fuelNeeded > satellite.fuelKg) {
    // Binary search for maximum achievable ΔV with remaining fuel
    let lo = 0, hi = dvMs;
    for (let i = 0; i < 20; i++) {
      const mid = (lo + hi) / 2;
      if (computeFuelConsumed(satellite.currentMass, mid) <= satellite.fuelKg) {
        lo = mid;
      } else {
        hi = mid;
      }
    }
    dvMs = lo;
    dvKms = dvMs / 1000;
    fuelNeeded = computeFuelConsumed(satellite.currentMass, dvMs);

    if (dvMs < 0.5) {
      // Less than 0.5 m/s achievable — not worth burning
      console.log(`[EOL] ${satellite.id} has insufficient fuel for any deorbit burn (${satellite.fuelKg.toFixed(3)} kg remaining)`);
      return;
    }

    console.log(`[EOL] ${satellite.id} partial deorbit burn: ${dvMs.toFixed(2)} m/s (fuel limited)`);
  }

  // ── Build retrograde ΔV (negative T direction = retrograde) ────────────
  const deltaV_ECI = {
    x: -dvKms * T_hat.x,
    y: -dvKms * T_hat.y,
    z: -dvKms * T_hat.z,
  };

  // ── Schedule burn ──────────────────────────────────────────────────────
  const burnTime = new Date(currentSimTime.getTime() + SCHEDULE_DELAY_S * 1000);
  const burnId = `AUTO_EOL_${satellite.id}_${Date.now()}`;

  maneuverQueue.add(satellite.id, {
    burn_id: burnId,
    burnTime: burnTime.toISOString(),
    deltaV_vector: deltaV_ECI,
  });

  console.log(
    `[EOL] ${satellite.id} fuel critical (${satellite.fuelKg.toFixed(3)} kg remaining). Scheduling deorbit burn.`
  );
  console.log(
    `[EOL] Deorbit burn: burnTime=${burnTime.toISOString()} | dv=${dvMs.toFixed(2)} m/s retrograde | burn_id=${burnId}`
  );
}

module.exports = { scheduleGraveyardOrbit };
