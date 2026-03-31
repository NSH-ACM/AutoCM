'use strict';

const constellation = require('../state/constellation');
const cdmStore      = require('../state/cdmStore');
const simClock      = require('../state/simClock');

/**
 * POST /api/telemetry
 *
 * Ingests a batch of ECI state vectors (satellites + debris) and updates
 * the internal physics state. The simulation clock is set to the incoming
 * timestamp on the first call (subsequent advances come from simulate/step).
 *
 * Malformed individual entries are skipped; the rest of the batch is processed.
 *
 * Request body:
 * {
 *   "timestamp": "2026-03-12T08:00:00.000Z",
 *   "objects": [
 *     { "id": "DEB-99421", "type": "DEBRIS", "r": {x,y,z}, "v": {x,y,z} },
 *     { "id": "SAT-Alpha-04", "type": "SATELLITE", "r": {x,y,z}, "v": {x,y,z} }
 *   ]
 * }
 *
 * Response 200:
 * { "status": "ACK", "processed_count": N, "active_cdm_warnings": M }
 */
async function ingestTelemetry(req, res) {
  const { timestamp, objects } = req.body;

  if (!timestamp || !Array.isArray(objects)) {
    return res.status(400).json({
      error: 'Invalid payload. Required fields: timestamp (ISO string), objects (array).',
    });
  }

  const incomingTime = new Date(timestamp);
  if (isNaN(incomingTime.getTime())) {
    return res.status(400).json({ error: `Invalid timestamp format: "${timestamp}"` });
  }

  // Advance the sim clock if incoming timestamp is ahead.
  // This lets the first telemetry batch seed the initial simulation time.
  if (incomingTime > simClock.getCurrentTime()) {
    simClock.setCurrentTime(incomingTime);
  }

  let processedCount = 0;

  for (const obj of objects) {
    // Skip entries missing required fields
    if (
      !obj.id ||
      !obj.type ||
      !obj.r || typeof obj.r.x !== 'number' || typeof obj.r.y !== 'number' || typeof obj.r.z !== 'number' ||
      !obj.v || typeof obj.v.x !== 'number' || typeof obj.v.y !== 'number' || typeof obj.v.z !== 'number'
    ) {
      continue;
    }

    if (!['SATELLITE', 'DEBRIS'].includes(obj.type)) {
      continue;
    }

    constellation.upsert({
      id:        obj.id,
      type:      obj.type,
      r:         obj.r,
      v:         obj.v,
      timestamp: incomingTime,
    });
    processedCount++;
  }

  return res.status(200).json({
    status:              'ACK',
    processed_count:     processedCount,
    active_cdm_warnings: cdmStore.getActiveCDMCount(),
  });
}

module.exports = { ingestTelemetry };
