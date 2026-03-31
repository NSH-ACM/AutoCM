'use strict';

const constellation  = require('../state/constellation');
const maneuverQueue  = require('../state/maneuverQueue');
const simClock       = require('../state/simClock');
const physics        = require('../physics/interface');
const groundStations = require('../data/groundStations');
const {
  deltaVMagnitudeMs,
  computeFuelConsumed,
  MAX_DELTA_V_MS,
  COOLDOWN_SECONDS,
  SIGNAL_LATENCY_S,
} = require('../utils/orbital');

/**
 * POST /api/maneuver/schedule
 *
 * Validates and schedules a sequence of burns for a satellite.
 * Every burn in the sequence is validated before any is queued —
 * the entire sequence is accepted or rejected atomically.
 *
 * Validation rules enforced (in order):
 *   1. Satellite exists in constellation state
 *   2. Satellite is not in EOL status
 *   3. Every burn has required fields
 *   4. burnTime >= currentSimTime + SIGNAL_LATENCY_S (10s uplink latency)
 *   5. |ΔV| ≤ MAX_DELTA_V_MS (15 m/s) per burn
 *   6. No conflict with already-queued burns on this satellite (600s cooldown)
 *   7. No conflict with last executed burn (600s cooldown)
 *   8. No cooldown violation between burns within this sequence
 *   9. Ground station LOS available at scheduling time
 *  10. Sufficient fuel for the entire sequence (simulated sequentially)
 *
 * Request body:
 * {
 *   "satelliteId": "SAT-Alpha-04",
 *   "maneuver_sequence": [
 *     { "burn_id": "EVASION_BURN_1", "burnTime": "...", "deltaV_vector": {x,y,z} },
 *     { "burn_id": "RECOVERY_BURN_1", "burnTime": "...", "deltaV_vector": {x,y,z} }
 *   ]
 * }
 *
 * Response 202 (accepted):
 * { "status": "SCHEDULED", "validation": { ground_station_los, sufficient_fuel, projected_mass_remaining_kg } }
 *
 * Response 422 (validation failed):
 * { "error": "...", "details": [...] }
 */
async function scheduleManeuver(req, res) {
  const { satelliteId, maneuver_sequence } = req.body;

  // ─── Top-level payload check ─────────────────────────────────────────────
  if (!satelliteId || !Array.isArray(maneuver_sequence) || maneuver_sequence.length === 0) {
    return res.status(400).json({
      error: 'Invalid payload. Required: satelliteId (string), maneuver_sequence (non-empty array).',
    });
  }

  // ─── Satellite existence check ───────────────────────────────────────────
  const satellite = constellation.getSatellite(satelliteId);
  if (!satellite) {
    return res.status(404).json({
      error: `Satellite "${satelliteId}" not found. Has its telemetry been ingested yet?`,
    });
  }

  // ─── EOL check ───────────────────────────────────────────────────────────
  if (satellite.status === 'EOL') {
    return res.status(409).json({
      error: `Satellite "${satelliteId}" has reached End-of-Life status. No maneuvers permitted.`,
    });
  }

  const currentTime   = simClock.getCurrentTime();
  const minBurnTime   = new Date(currentTime.getTime() + SIGNAL_LATENCY_S * 1000);
  const validationErrors = [];

  // ─── Per-burn validation ──────────────────────────────────────────────────
  for (let i = 0; i < maneuver_sequence.length; i++) {
    const burn   = maneuver_sequence[i];
    const prefix = `Burn[${burn.burn_id || i}]: `;

    // Required fields
    if (!burn.burn_id || !burn.burnTime || !burn.deltaV_vector) {
      validationErrors.push(`${prefix}Missing required fields (burn_id, burnTime, deltaV_vector).`);
      continue; // Skip further checks on this entry if it's incomplete
    }

    const burnDate = new Date(burn.burnTime);
    if (isNaN(burnDate.getTime())) {
      validationErrors.push(`${prefix}Invalid burnTime format: "${burn.burnTime}".`);
      continue;
    }

    // Rule 4 — Signal latency
    if (burnDate < minBurnTime) {
      validationErrors.push(
        `${prefix}burnTime must be ≥ current_sim_time + ${SIGNAL_LATENCY_S}s ` +
        `(earliest valid: ${minBurnTime.toISOString()}).`
      );
    }

    // Rule 5 — ΔV magnitude limit
    const dvMs = deltaVMagnitudeMs(burn.deltaV_vector);
    if (dvMs > MAX_DELTA_V_MS) {
      validationErrors.push(
        `${prefix}|ΔV| = ${dvMs.toFixed(4)} m/s exceeds the ${MAX_DELTA_V_MS} m/s per-burn limit.`
      );
    }

    // Rule 6 — Cooldown against EXISTING queued burns for this satellite
    for (const queued of maneuverQueue.getBurnsBySatellite(satelliteId)) {
      const diffSec = Math.abs(burnDate - queued.burnTime) / 1000;
      if (diffSec < COOLDOWN_SECONDS) {
        validationErrors.push(
          `${prefix}Cooldown conflict with already-scheduled burn "${queued.burnId}" ` +
          `(${diffSec.toFixed(0)}s apart; minimum is ${COOLDOWN_SECONDS}s).`
        );
      }
    }

    // Rule 7 — Cooldown against last executed burn
    if (satellite.lastBurnTime) {
      const diffSec = (burnDate - new Date(satellite.lastBurnTime)) / 1000;
      if (diffSec < COOLDOWN_SECONDS) {
        const remaining = (COOLDOWN_SECONDS - diffSec).toFixed(0);
        validationErrors.push(
          `${prefix}Thruster cooldown active from last burn. ${remaining}s remaining.`
        );
      }
    }

    // Rule 8 — Cooldown between burns within THIS sequence
    for (let j = 0; j < i; j++) {
      const other = maneuver_sequence[j];
      if (!other.burnTime) continue;
      const otherDate = new Date(other.burnTime);
      const diffSec   = Math.abs(burnDate - otherDate) / 1000;
      if (diffSec < COOLDOWN_SECONDS) {
        validationErrors.push(
          `${prefix}Cooldown violation with burn "${other.burn_id}" in this sequence ` +
          `(${diffSec.toFixed(0)}s apart; minimum is ${COOLDOWN_SECONDS}s).`
        );
      }
    }

    // Rule 9 — Ground station LOS at scheduling time (current sim time)
    const hasLOS = await physics.checkLOS(satellite, groundStations, currentTime);
    if (!hasLOS) {
      validationErrors.push(
        `${prefix}No ground station has line-of-sight to "${satelliteId}" at the current simulation time.`
      );
    }
  }

  if (validationErrors.length > 0) {
    return res.status(422).json({
      error:   'Maneuver sequence rejected: validation failed.',
      details: validationErrors,
    });
  }

  // ─── Rule 10 — Fuel sufficiency (simulate sequence forward) ───────────────
  // Mass decreases after each burn, making subsequent burns slightly cheaper.
  let simulatedMass = satellite.currentMass;
  let simulatedFuel = satellite.fuelKg;

  for (const burn of maneuver_sequence) {
    const dvMs        = deltaVMagnitudeMs(burn.deltaV_vector);
    const fuelNeeded  = computeFuelConsumed(simulatedMass, dvMs);

    if (fuelNeeded > simulatedFuel) {
      return res.status(422).json({
        status: 'REJECTED',
        validation: {
          ground_station_los:            true,
          sufficient_fuel:               false,
          projected_mass_remaining_kg:   parseFloat((simulatedMass - simulatedFuel).toFixed(3)),
          error: `Insufficient fuel at burn "${burn.burn_id}": need ${fuelNeeded.toFixed(4)} kg, have ${simulatedFuel.toFixed(4)} kg.`,
        },
      });
    }

    simulatedFuel -= fuelNeeded;
    simulatedMass -= fuelNeeded;
  }

  // ─── All checks passed — queue the entire sequence ────────────────────────
  for (const burn of maneuver_sequence) {
    maneuverQueue.add(satelliteId, burn);
  }

  return res.status(202).json({
    status: 'SCHEDULED',
    validation: {
      ground_station_los:          true,
      sufficient_fuel:             true,
      projected_mass_remaining_kg: parseFloat(simulatedMass.toFixed(3)),
    },
  });
}

module.exports = { scheduleManeuver };
