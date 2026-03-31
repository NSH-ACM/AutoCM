'use strict';

const constellation     = require('../state/constellation');
const maneuverQueue     = require('../state/maneuverQueue');
const cdmStore          = require('../state/cdmStore');
const simClock          = require('../state/simClock');
const physics           = require('../physics/interface');
const alertStore        = require('../state/alertStore');
const {
  computeFuelConsumed,
  deltaVMagnitudeMs,
  EOL_FUEL_THRESHOLD_KG,
} = require('../utils/orbital');
const autonomousManager = require('../autonomy/manager');
const constellationCtrl = require('./constellationController');

// ── Auto-simulation state ─────────────────────────────────────────────────────
let _autoSimInterval = null;
let _autoSimSpeed    = 1;      // seconds of sim time per real tick
let _autoSimTicking  = false;  // prevents overlapping ticks

// ─────────────────────────────────────────────────────────────────────────────
/**
 * POST /api/simulate/step
 */
async function simulateStep(req, res) {
  const { step_seconds } = req.body;

  if (typeof step_seconds !== 'number' || step_seconds <= 0) {
    return res.status(400).json({ error: 'step_seconds must be a positive number.' });
  }

  const result = await _doStep(step_seconds);
  return res.status(200).json(result);
}

// ── Core step function (shared by manual and auto-sim) ────────────────────────
async function _doStep(step_seconds) {
  const startTime = simClock.getCurrentTime();
  const endTime   = new Date(startTime.getTime() + step_seconds * 1000);

  const allObjects  = constellation.getAllObjects();
  const pendingBurns = maneuverQueue
    .getBurnsInWindow(startTime, endTime)
    .sort((a, b) => a.burnTime - b.burnTime);

  let cursor             = new Date(startTime);
  let maneuversExecuted  = 0;
  let collisionsDetected = 0;

  // ── Execute burns ─────────────────────────────────────────────────────────
  for (const burn of pendingBurns) {
    const dtToBurn = (burn.burnTime - cursor) / 1000;
    if (dtToBurn > 0) await _tryPropagate(allObjects, dtToBurn);

    const satellite = constellation.getSatellite(burn.satelliteId);
    if (!satellite) {
      maneuverQueue.markFailed(burn.burnId, 'Satellite not found during execution');
      continue;
    }

    // Apply impulsive ΔV
    satellite.v.x += burn.deltaV.x;
    satellite.v.y += burn.deltaV.y;
    satellite.v.z += burn.deltaV.z;

    const dvMs         = deltaVMagnitudeMs(burn.deltaV);
    const fuelConsumed = computeFuelConsumed(satellite.currentMass, dvMs);

    satellite.fuelKg      = Math.max(0, satellite.fuelKg - fuelConsumed);
    satellite.currentMass = satellite.dryMass + satellite.fuelKg;
    satellite.lastBurnTime = new Date(burn.burnTime);

    // EOL check
    if (satellite.fuelKg <= EOL_FUEL_THRESHOLD_KG && satellite.status !== 'EOL') {
      satellite.status = 'EOL';
      alertStore.add('CRITICAL', `🪦 ${satellite.id} fuel depleted (${satellite.fuelKg.toFixed(2)} kg). Deorbiting.`);
      console.warn(`[EOL] ${satellite.id} → EOL`);
    }

    // Track ΔV for analytics
    constellationCtrl.recordBurnExecuted(dvMs, burn.burnId);

    maneuverQueue.markExecuted(burn.burnId);
    maneuversExecuted++;
    cursor = new Date(burn.burnTime);

    const burnLabel = burn.burnId.includes('AUTO_EVA_') ? '⬛ EVASION' :
                      burn.burnId.includes('AUTO_REC_') ? '🔵 RECOVERY' :
                      burn.burnId.includes('AUTO_EOL_') ? '⚫ DEORBIT' : '🟡 MANUAL';
    console.log(`[SimStep] ${burnLabel} burn on ${satellite.id} | ΔV=${dvMs.toFixed(4)} m/s | fuel=${satellite.fuelKg.toFixed(3)} kg`);
  }

  // ── Propagate remaining ────────────────────────────────────────────────────
  const remainingDt = (endTime - cursor) / 1000;
  if (remainingDt > 0) await _tryPropagate(allObjects, remainingDt);

  // ── Conjunction detection ─────────────────────────────────────────────────
  const satellites = constellation.getAllSatellites();
  const debrisArr  = constellation.getAllDebris();

  try {
    const cdms = await physics.detectConjunctions(satellites, debrisArr, 86400, endTime);
    cdmStore.updateCDMs(cdms);
    collisionsDetected = cdms.filter(c => c.missDistance < 0.1).length;

    // Track raise count and emit alerts for critical CDMs
    constellationCtrl.recordCdmsRaised(cdms.length);
    cdms.forEach(c => {
      if (c.missDistance < 0.1) {
        alertStore.add('CRITICAL',
          `🔴 CDM: ${c.satelliteId} — miss ${(c.missDistance * 1000).toFixed(0)} m at TCA`);
      } else if (c.missDistance < 1.0) {
        alertStore.add('WARNING',
          `🟠 CDM: ${c.satelliteId} — ${c.missDistance.toFixed(2)} km approach`);
      }
    });

    await autonomousManager.respondToCDMs(cdms, endTime);
  } catch (err) {
    console.warn(`[SimStep] detectConjunctions: ${err.message}`);
  }

  simClock.setCurrentTime(endTime);

  // Prune old executed/failed burns to prevent memory leak
  maneuverQueue.pruneOldEntries();

  return {
    status:              'STEP_COMPLETE',
    new_timestamp:       endTime.toISOString(),
    collisions_detected: collisionsDetected,
    maneuvers_executed:  maneuversExecuted,
    step_seconds,
  };
}

// ── Auto-simulation ───────────────────────────────────────────────────────────
/**
 * POST /api/simulate/run
 * Body: { step_seconds: number, real_interval_ms: number }
 * Starts an automatic stepping loop.
 */
function startAutoSim(req, res) {
  const { step_seconds = 60, real_interval_ms = 1000 } = req.body || {};

  // Validate parameters
  if (typeof step_seconds !== 'number' || step_seconds <= 0 || step_seconds > 86400) {
    return res.status(400).json({ error: 'step_seconds must be a number between 1 and 86400.' });
  }
  if (typeof real_interval_ms !== 'number' || real_interval_ms < 100 || real_interval_ms > 60000) {
    return res.status(400).json({ error: 'real_interval_ms must be a number between 100 and 60000.' });
  }

  if (_autoSimInterval) {
    return res.status(409).json({ error: 'Auto-sim already running. POST /api/simulate/stop first.' });
  }

  _autoSimSpeed = step_seconds;

  _autoSimInterval = setInterval(async () => {
    if (_autoSimTicking) return;  // Skip if previous tick hasn't finished
    _autoSimTicking = true;
    try {
      await _doStep(_autoSimSpeed);
    } catch (err) {
      console.error('[AutoSim] Tick error:', err.message);
    } finally {
      _autoSimTicking = false;
    }
  }, real_interval_ms);

  console.log(`[AutoSim] Started: ${step_seconds}s sim / ${real_interval_ms}ms real`);
  alertStore.add('INFO', `▶ Auto-sim started — ${step_seconds}s/tick`);

  return res.status(200).json({
    status:          'AUTO_SIM_STARTED',
    step_seconds,
    real_interval_ms,
  });
}

function stopAutoSim(_req, res) {
  if (!_autoSimInterval) {
    return res.status(400).json({ error: 'Auto-sim is not running.' });
  }
  clearInterval(_autoSimInterval);
  _autoSimInterval = null;
  _autoSimTicking  = false;
  alertStore.add('INFO', '⏸ Auto-sim paused');
  console.log('[AutoSim] Stopped');
  return res.status(200).json({ status: 'AUTO_SIM_STOPPED' });
}

function getAutoSimStatus(_req, res) {
  return res.status(200).json({
    running:      !!_autoSimInterval,
    step_seconds: _autoSimSpeed,
    sim_time:     simClock.getCurrentTime().toISOString(),
  });
}

// ── Internal helpers ──────────────────────────────────────────────────────────
async function _tryPropagate(objects, dt) {
  try {
    await physics.propagate(objects, dt);
  } catch (err) {
    if (!_tryPropagate._warned) {
      console.warn(`[SimStep] physics.propagate() unavailable: ${err.message}`);
      _tryPropagate._warned = true;
    }
  }
}
_tryPropagate._warned = false;

module.exports = { simulateStep, startAutoSim, stopAutoSim, getAutoSimStatus };
