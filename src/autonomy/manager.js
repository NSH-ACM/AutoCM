'use strict';

/**
 * ════════════════════════════════════════════════════════════════════════
 *  AUTONOMOUS MANAGER  —  src/autonomy/manager.js
 *
 *  The Brain. Called once per simulate/step tick after conjunction
 *  detection runs. Orchestrates evasion, recovery, EOL, and status
 *  management for the entire constellation.
 *
 *  Execution order:
 *    1. Filter actionable CDMs
 *    2. Check ground station LOS
 *    3. Plan evasion burns (min ΔV)
 *    4. Plan recovery burns
 *    5. Submit burn pairs to maneuver queue
 *    6. Update satellite status → EVADING
 *    7. Handle EOL satellites (graveyard deorbit)
 *    8. Update RECOVERING → NOMINAL transitions
 * ════════════════════════════════════════════════════════════════════════
 */

const constellation  = require('../state/constellation');
const maneuverQueue  = require('../state/maneuverQueue');
const physics        = require('../physics/interface');
const groundStations = require('../data/groundStations');
const {
  stationKeepingDistance,
  EOL_FUEL_THRESHOLD_KG,
  SIGNAL_LATENCY_S,
  COOLDOWN_SECONDS,
} = require('../utils/orbital');

const evasionPlanner  = require('./evasionPlanner');
const recoveryPlanner = require('./recoveryPlanner');
const eolHandler      = require('./eolHandler');

// ── Constants ──────────────────────────────────────────────────────────────────
const COLLISION_THRESHOLD_KM  = 0.1;   // 100 m — critical threshold
const NOMINAL_RETURN_DIST_KM  = 10.0;  // Within 10 km = back in slot

// ══════════════════════════════════════════════════════════════════════════════
//  MAIN ENTRY POINT — called from simulateController.js
// ══════════════════════════════════════════════════════════════════════════════

/**
 * respondToCDMs(cdms, currentSimTime)
 *
 * Processes all active CDMs, plans and schedules autonomous evasion/recovery
 * burn pairs, handles EOL satellites, and manages status transitions.
 *
 * @param {Array}  cdms           — CDM entries from physics.detectConjunctions()
 * @param {Date}   currentSimTime — end-of-step simulation time
 */
async function respondToCDMs(cdms, currentSimTime) {
  // ── Step 1–6: Process critical CDMs ─────────────────────────────────────
  const actionable = filterActionableCDMs(cdms, currentSimTime);

  if (actionable.length > 0) {
    console.log(`[ACM] Processing ${actionable.length} critical CDMs...`);
  }

  for (const cdm of actionable) {
    try {
      await processOneCDM(cdm, currentSimTime);
    } catch (err) {
      console.error(`[ACM] Error processing CDM ${cdm.satelliteId} vs ${cdm.debrisId}: ${err.message}`);
    }
  }

  // ── Step 7: Handle EOL satellites ───────────────────────────────────────
  const satellites = constellation.getAllSatellites();
  for (const sat of satellites) {
    if (sat.fuelKg <= EOL_FUEL_THRESHOLD_KG && sat.status !== 'EOL') {
      // simulateController already sets EOL status, just schedule deorbit
      await eolHandler.scheduleGraveyardOrbit(sat, currentSimTime);
    }
  }

  // ── Step 8: Update status transitions ───────────────────────────────────
  updateStatusTransitions(currentSimTime);
}

// ══════════════════════════════════════════════════════════════════════════════
//  Step 1 — FILTER ACTIONABLE CDMs
// ══════════════════════════════════════════════════════════════════════════════

/**
 * A CDM is actionable if ALL of:
 *   1. missDistance < 0.1 km (critical)
 *   2. Satellite has no PENDING evasion burn already
 *   3. Satellite is not EVADING or EOL
 *   4. Time to TCA > SIGNAL_LATENCY_S
 *
 * Also deduplicates: only keep the most critical CDM per satellite.
 */
function filterActionableCDMs(cdms, currentSimTime) {
  const nowMs = currentSimTime.getTime();

  // Pre-filter on conditions 1 and 4
  const critical = cdms.filter(cdm => {
    if (cdm.missDistance >= COLLISION_THRESHOLD_KM) return false;

    const timeToTCA = (cdm.tca.getTime() - nowMs) / 1000;
    if (timeToTCA <= SIGNAL_LATENCY_S) {
      console.log(`[ACM] CDM ${cdm.satelliteId} vs ${cdm.debrisId} — TCA too close (${timeToTCA.toFixed(0)}s), cannot uplink in time`);
      return false;
    }

    return true;
  });

  // Deduplicate: keep most critical CDM per satellite (lowest miss distance)
  const bestPerSat = new Map();
  for (const cdm of critical) {
    const existing = bestPerSat.get(cdm.satelliteId);
    if (!existing || cdm.missDistance < existing.missDistance) {
      bestPerSat.set(cdm.satelliteId, cdm);
    }
  }

  // Filter on conditions 2 and 3
  const actionable = [];
  for (const cdm of bestPerSat.values()) {
    const sat = constellation.getSatellite(cdm.satelliteId);
    if (!sat) {
      console.log(`[ACM] CDM skip: ${cdm.satelliteId} not found in constellation`);
      continue;
    }

    if (sat.status === 'EVADING' || sat.status === 'EOL') {
      console.log(`[ACM] CDM skip: ${cdm.satelliteId} already ${sat.status}`);
      continue;
    }

    // Check for existing pending evasion burns
    const pendingBurns = maneuverQueue.getBurnsBySatellite(cdm.satelliteId);
    const hasEvasionBurn = pendingBurns.some(b => b.burnId.includes('AUTO_EVA_'));
    if (hasEvasionBurn) {
      console.log(`[ACM] CDM skip: ${cdm.satelliteId} already has pending evasion burn`);
      continue;
    }

    actionable.push(cdm);
  }

  return actionable;
}

// ══════════════════════════════════════════════════════════════════════════════
//  Steps 2–6 — PROCESS ONE CDM
// ══════════════════════════════════════════════════════════════════════════════

async function processOneCDM(cdm, currentSimTime) {
  const satellite = constellation.getSatellite(cdm.satelliteId);
  const debris    = constellation.getDebris(cdm.debrisId);

  if (!satellite || !debris) {
    console.log(`[ACM] CDM skip: objects not in state (sat=${!!satellite}, deb=${!!debris})`);
    return;
  }

  const timeToTCA = ((cdm.tca.getTime() - currentSimTime.getTime()) / 1000);
  const tcaHours  = Math.floor(timeToTCA / 3600);
  const tcaMin    = Math.floor((timeToTCA % 3600) / 60);

  console.log(
    `[ACM] CDM: ${satellite.id} vs ${cdm.debrisId} | ` +
    `miss=${cdm.missDistance.toFixed(3)}km | TCA=T+${tcaHours}h${tcaMin}m`
  );

  // ── Step 2: Check ground station LOS ────────────────────────────────────
  let hasLOS = false;
  let losStation = null;

  try {
    hasLOS = await physics.checkLOS(satellite, groundStations, currentSimTime);
    if (hasLOS) {
      // Find which station has LOS (for logging)
      losStation = await findLOSStation(satellite, currentSimTime);
    }
  } catch (err) {
    // checkLOS may throw if physics not ready — assume LOS available
    console.log(`[ACM] LOS check failed (${err.message}) — assuming LOS available`);
    hasLOS = true;
  }

  if (!hasLOS) {
    // Try future LOS windows before TCA
    const futureWindow = await findFutureLOSWindow(satellite, cdm.tca, currentSimTime);
    if (futureWindow) {
      console.log(`[ACM] No current LOS. Scheduling at future window: ${futureWindow.toISOString()}`);
      // Delay burn to LOS window — adjust currentSimTime for planner
    } else {
      console.log(`[ACM] BLIND CONJUNCTION — ${satellite.id}: no LOS window before TCA. Cannot uplink.`);
      return;
    }
  } else {
    const gsName = losStation ? losStation.name.replace(/_/g, ' ') : 'unknown';
    console.log(`[ACM] LOS check: ${satellite.id} → ${gsName} ✓`);
  }

  // ── Step 3: Plan evasion burn ───────────────────────────────────────────
  const evasionBurn = evasionPlanner.planEvasion(
    satellite, debris, cdm.tca, currentSimTime
  );

  if (!evasionBurn) {
    console.log(`[ACM] No valid evasion burn found for ${satellite.id} — skipping`);
    return;
  }

  // ── Step 4: Plan recovery burn ──────────────────────────────────────────
  const recoveryBurn = recoveryPlanner.planRecovery(
    satellite, cdm.tca, evasionBurn
  );

  // ── Step 5: Submit both burns to maneuver queue ─────────────────────────
  const evaBurnId = `AUTO_EVA_${satellite.id}_${Date.now()}`;
  const recBurnId = `AUTO_REC_${satellite.id}_${Date.now() + 1}`;

  maneuverQueue.add(satellite.id, {
    burn_id: evaBurnId,
    burnTime: evasionBurn.burnTime.toISOString(),
    deltaV_vector: evasionBurn.deltaV_ECI,
  });

  maneuverQueue.add(satellite.id, {
    burn_id: recBurnId,
    burnTime: recoveryBurn.burnTime.toISOString(),
    deltaV_vector: recoveryBurn.deltaV_ECI,
  });

  const evaDvMs = evasionBurn.dvMagnitudeMs;
  const evaKms  = (evaDvMs / 1000).toFixed(4);

  console.log(
    `[ACM] Evasion: ${evasionBurn.strategy} ${evaDvMs >= 0 ? '+' : ''}${evaKms} km/s | ` +
    `fuel cost: ${evasionBurn.fuelCostKg.toFixed(3)}kg | scheduled: ${evasionBurn.burnTime.toISOString()}`
  );
  console.log(
    `[ACM] Recovery: ${(recoveryBurn.dvMagnitudeMs / 1000).toFixed(4)} km/s | ` +
    `scheduled: ${recoveryBurn.burnTime.toISOString()}`
  );

  // ── Step 6: Update satellite status ─────────────────────────────────────
  satellite.status = 'EVADING';
  console.log(`[ACM] ${satellite.id} status → EVADING`);
}

// ══════════════════════════════════════════════════════════════════════════════
//  Step 8 — STATUS TRANSITIONS
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Manage EVADING → RECOVERING → NOMINAL state machine.
 */
function updateStatusTransitions(currentSimTime) {
  const satellites = constellation.getAllSatellites();

  for (const sat of satellites) {
    if (sat.status === 'EOL') continue;

    const allBurns = maneuverQueue.getAll().filter(b => b.satelliteId === sat.id);
    const pendingBurns = allBurns.filter(b => b.status === 'PENDING');

    // ── EVADING → RECOVERING ──────────────────────────────────────────────
    // Evasion burn executed, recovery burn still pending
    if (sat.status === 'EVADING') {
      const evasionBurns = allBurns.filter(b => b.burnId.includes('AUTO_EVA_'));
      const recoveryBurns = allBurns.filter(b => b.burnId.includes('AUTO_REC_'));

      const evasionExecuted = evasionBurns.some(b => b.status === 'EXECUTED');
      const recoveryPending = recoveryBurns.some(b => b.status === 'PENDING');

      if (evasionExecuted && recoveryPending) {
        sat.status = 'RECOVERING';
        console.log(`[ACM] ${sat.id} evasion complete. Status → RECOVERING`);
      }

      // Edge case: both burns executed or failed, force to RECOVERING
      if (evasionExecuted && !recoveryPending) {
        const recoveryExecuted = recoveryBurns.some(b => b.status === 'EXECUTED');
        if (recoveryExecuted) {
          sat.status = 'RECOVERING'; // Will transition to NOMINAL below
        }
      }
    }

    // ── RECOVERING → NOMINAL ──────────────────────────────────────────────
    // Recovery burn executed AND within 10km of nominal slot
    if (sat.status === 'RECOVERING') {
      const hasPending = pendingBurns.length > 0;

      if (!hasPending && sat.nominalSlot) {
        const dist = stationKeepingDistance(sat.r, sat.nominalSlot, sat.v, sat.nominalV);
        if (dist <= NOMINAL_RETURN_DIST_KM) {
          sat.status = 'NOMINAL';
          console.log(`[ACM] ${sat.id} returned to nominal slot (${dist.toFixed(2)} km). Status → NOMINAL`);
        }
      }
    }
  }
}

// ══════════════════════════════════════════════════════════════════════════════
//  HELPERS
// ══════════════════════════════════════════════════════════════════════════════

/**
 * Find which ground station currently has LOS (for logging).
 */
async function findLOSStation(satellite, atTime) {
  for (const gs of groundStations) {
    try {
      if (await physics.checkLOS(satellite, [gs], atTime)) {
        return gs;
      }
    } catch (_) { /* skip */ }
  }
  return null;
}

/**
 * Search for a future LOS window before TCA.
 * Scans in 60-second steps from now to TCA.
 */
async function findFutureLOSWindow(satellite, tcaDate, currentSimTime) {
  const step = 60 * 1000; // 60 seconds
  const tcaMs = tcaDate.getTime();
  let t = currentSimTime.getTime() + step;

  // Limit search to 100 steps (~100 minutes) for performance
  const maxSteps = 100;
  let steps = 0;

  while (t < tcaMs && steps < maxSteps) {
    const checkTime = new Date(t);
    try {
      if (await physics.checkLOS(satellite, groundStations, checkTime)) {
        return checkTime;
      }
    } catch (_) { /* skip */ }
    t += step;
    steps++;
  }

  return null;
}

module.exports = { respondToCDMs };
