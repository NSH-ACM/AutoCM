'use strict';

const constellation = require('../state/constellation');
const simClock      = require('../state/simClock');
const cdmStore      = require('../state/cdmStore');
const maneuverQueue = require('../state/maneuverQueue');
const { eciToGeodetic } = require('../utils/orbital');

/**
 * GET /api/visualization/snapshot
 *
 * Returns a compressed, frontend-optimized snapshot of the current fleet state.
 * Called at high frequency by the Orbital Insight dashboard.
 *
 * Satellites use a full object format (50+ objects, manageable size).
 * Debris uses a compact tuple format [id, lat, lon, altKm] to minimize JSON
 * payload size for 10,000+ objects.
 *
 * Response 200:
 * {
 *   "timestamp": "...",
 *   "satellites": [{ "id", "lat", "lon", "fuel_kg", "status" }],
 *   "debris_cloud": [["DEB-id", lat, lon, altKm], ...],
 *   "cdms": [...],
 *   "maneuvers": [...]
 * }
 */
function getSnapshot(req, res) {
  const currentTime = simClock.getCurrentTime();

  // ─── Satellites ───────────────────────────────────────────────────────────
  const satellites = constellation.getAllSatellites().map((sat) => {
    const { lat, lon } = eciToGeodetic(sat.r, currentTime);
    return {
      id:      sat.id,
      lat:     parseFloat(lat.toFixed(4)),
      lon:     parseFloat(lon.toFixed(4)),
      fuel_kg: parseFloat(sat.fuelKg.toFixed(2)),
      status:  sat.status,
    };
  });

  // ─── Debris cloud (flattened tuple format to minimise payload) ────────────
  const debris_cloud = constellation.getAllDebris().map((deb) => {
    const { lat, lon, altKm } = eciToGeodetic(deb.r, currentTime);
    return [
      deb.id,
      parseFloat(lat.toFixed(3)),
      parseFloat(lon.toFixed(3)),
      parseFloat(altKm.toFixed(2)),
    ];
  });

  // ─── CDMs and Maneuvers ──────────────────────────────────────────────────
  const cdms = cdmStore.getActiveCDMs();
  const maneuvers = maneuverQueue.getAll();

  return res.status(200).json({
    timestamp:    currentTime.toISOString(),
    satellites,
    debris_cloud,
    cdms,
    maneuvers,
  });
}

module.exports = { getSnapshot };
