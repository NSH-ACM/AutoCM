'use strict';

/**
 * CDM (Conjunction Data Message) Store
 *
 * Holds the latest set of active conjunction warnings produced by the
 * physics engine's detectConjunctions() call during each simulate/step.
 *
 * CDM entry shape (set by Part 1's physics engine):
 * {
 *   satelliteId:  string  — the threatened satellite
 *   debrisId:     string  — the threatening debris object
 *   tca:          Date    — Time of Closest Approach
 *   missDistance: number  — predicted miss distance in km
 *   probability:  number  — collision probability [0, 1]
 *   status:       'ACTIVE'
 * }
 */

let activeCDMs = [];

/**
 * Replaces the active CDM list with fresh detections from the physics engine.
 * Called once per simulate/step cycle.
 * @param {Array} cdms
 */
function updateCDMs(cdms) {
  activeCDMs = cdms.map((c) => ({ ...c, status: 'ACTIVE' }));
}

function getActiveCDMs() {
  return activeCDMs;
}

function getActiveCDMCount() {
  return activeCDMs.length;
}

/**
 * Returns CDMs where missDistance < 0.100 km (100 m — the critical collision threshold).
 */
function getCriticalCDMs() {
  return activeCDMs.filter((c) => c.missDistance < 0.1);
}

module.exports = { updateCDMs, getActiveCDMs, getActiveCDMCount, getCriticalCDMs };
