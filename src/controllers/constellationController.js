'use strict';

/**
 * GET /api/constellation/stats
 *
 * Fleet-wide analytics: status breakdown, fuel, ΔV, CDM counts, uptime.
 */

const constellation  = require('../state/constellation');
const maneuverQueue  = require('../state/maneuverQueue');
const cdmStore       = require('../state/cdmStore');
const simClock       = require('../state/simClock');
const { INITIAL_FUEL_KG } = require('../utils/orbital');

// ── Global counters (accumulated across steps) ────────────────────────────────
let _totalDvMs        = 0;   // m/s accumulated across all burns
let _totalCdmsRaised  = 0;   // total CDMs ever raised
let _totalEvasions    = 0;   // total AUTO_EVA burns executed
let _simStartTime     = null;  // lazy — set on first stats call

/**
 * Called from maneuverController / simulateController to update counters.
 * Export separately so other modules can call it.
 */
function recordBurnExecuted(dvMs, burnId) {
  _totalDvMs += dvMs;
  if (burnId && burnId.includes('AUTO_EVA_')) _totalEvasions++;
}

function recordCdmsRaised(count) {
  _totalCdmsRaised += count;
}

function resetStats() {
  _totalDvMs       = 0;
  _totalCdmsRaised = 0;
  _totalEvasions   = 0;
  _simStartTime    = new Date(simClock.getCurrentTime());
}

function getConstellationStats(_req, res) {
  const sats = constellation.getAllSatellites();
  const now  = simClock.getCurrentTime();

  // Lazy-init: set start time on first call (module loads before sim clock is seeded)
  if (!_simStartTime) _simStartTime = new Date(now);

  // Status breakdown
  const statusBreakdown = { NOMINAL: 0, EVADING: 0, RECOVERING: 0, EOL: 0 };
  let totalFuel = 0;
  let minFuel   = Infinity;
  let maxFuel   = 0;

  for (const s of sats) {
    statusBreakdown[s.status] = (statusBreakdown[s.status] || 0) + 1;
    totalFuel += s.fuelKg;
    if (s.fuelKg < minFuel) minFuel = s.fuelKg;
    if (s.fuelKg > maxFuel) maxFuel = s.fuelKg;
  }

  const activeSats    = sats.length - statusBreakdown.EOL;
  const avgFuelKg     = sats.length > 0 ? totalFuel / sats.length : 0;
  const avgFuelPct    = (avgFuelKg / INITIAL_FUEL_KG) * 100;
  const uptimePct     = sats.length > 0 ? (activeSats / sats.length) * 100 : 100;

  const activeCdms    = cdmStore.getActiveCDMs();
  const criticalCdms  = activeCdms.filter(c => c.missDistance < 0.1).length;
  const pendingBurns  = maneuverQueue.getAll().filter(b => b.status === 'PENDING').length;

  const simElapsedMs  = now - _simStartTime;
  const simElapsedH   = (simElapsedMs / 3600000).toFixed(2);

  return res.status(200).json({
    timestamp:         now.toISOString(),
    constellation: {
      total_satellites: sats.length,
      active_satellites: activeSats,
      status_breakdown: statusBreakdown,
      uptime_pct:       parseFloat(uptimePct.toFixed(2)),
    },
    fuel: {
      avg_kg:           parseFloat(avgFuelKg.toFixed(3)),
      avg_pct:          parseFloat(avgFuelPct.toFixed(1)),
      min_kg:           parseFloat(minFuel === Infinity ? 0 : minFuel.toFixed(3)),
      max_kg:           parseFloat(maxFuel.toFixed(3)),
    },
    debris: {
      tracked:          constellation.getDebrisCount(),
    },
    conjunctions: {
      active_cdms:      activeCdms.length,
      critical_cdms:    criticalCdms,
      total_raised:     _totalCdmsRaised,
    },
    maneuvers: {
      pending_burns:    pendingBurns,
      total_evasions:   _totalEvasions,
      total_dv_ms:      parseFloat(_totalDvMs.toFixed(4)),
    },
    simulation: {
      elapsed_hours:    simElapsedH,
    },
  });
}

module.exports = { getConstellationStats, recordBurnExecuted, recordCdmsRaised, resetStats };
