'use strict';

/**
 * Maneuver Queue
 *
 * Stores all scheduled (pending) and historical (executed/failed) burn commands.
 *
 * Queue entry shape:
 * {
 *   satelliteId: string
 *   burnId:      string          — unique ID from the request (burn_id)
 *   burnTime:    Date            — when to execute this burn
 *   deltaV:      {x, y, z}      — ΔV vector in km/s (ECI frame)
 *   status:      'PENDING' | 'EXECUTED' | 'FAILED'
 *   failReason:  string | null   — populated on FAILED status
 * }
 */

const queue = new Map(); // burnId -> entry

/**
 * Adds a burn to the queue. The burn object comes from the API request body.
 * @param {string} satelliteId
 * @param {{ burn_id, burnTime, deltaV_vector: {x,y,z} }} burn
 * @returns {object} The queued entry
 */
function add(satelliteId, burn) {
  const entry = {
    satelliteId,
    burnId:    burn.burn_id,
    burnTime:  new Date(burn.burnTime),
    deltaV:    { ...burn.deltaV_vector }, // km/s, ECI frame
    status:    'PENDING',
    failReason: null,
  };
  queue.set(burn.burn_id, entry);
  return entry;
}

/**
 * Returns all PENDING burns for a given satellite.
 */
function getBurnsBySatellite(satelliteId) {
  return Array.from(queue.values()).filter(
    (b) => b.satelliteId === satelliteId && b.status === 'PENDING'
  );
}

/**
 * Returns all PENDING burns whose burnTime falls within [startTime, endTime].
 * Used by simulate/step to determine which burns to execute.
 */
function getBurnsInWindow(startTime, endTime) {
  return Array.from(queue.values()).filter(
    (b) =>
      b.status === 'PENDING' &&
      b.burnTime >= startTime &&
      b.burnTime <= endTime
  );
}

function markExecuted(burnId) {
  const entry = queue.get(burnId);
  if (entry) entry.status = 'EXECUTED';
}

function markFailed(burnId, reason) {
  const entry = queue.get(burnId);
  if (entry) {
    entry.status = 'FAILED';
    entry.failReason = reason || 'Unknown';
  }
}

function getAll() {
  return Array.from(queue.values());
}

function getPending() {
  return Array.from(queue.values()).filter((b) => b.status === 'PENDING');
}

/**
 * Prune completed/failed burns older than maxAgeMs (default 2 hours).
 * Called periodically to prevent unbounded memory growth.
 */
function pruneOldEntries(maxAgeMs = 2 * 3600 * 1000) {
  const cutoff = Date.now() - maxAgeMs;
  for (const [burnId, entry] of queue.entries()) {
    if (entry.status !== 'PENDING' && entry.burnTime.getTime() < cutoff) {
      queue.delete(burnId);
    }
  }
}

module.exports = {
  add,
  getBurnsBySatellite,
  getBurnsInWindow,
  markExecuted,
  markFailed,
  getAll,
  getPending,
  pruneOldEntries,
};
