'use strict';

/**
 * Constellation State Store
 *
 * All objects (satellites + debris) are stored in-memory using Maps for O(1) lookup.
 * The physics engine (Part 1) modifies r and v fields IN PLACE during propagation.
 *
 * Satellite state shape:
 * {
 *   id:           string        — unique identifier (e.g. "SAT-Alpha-04")
 *   type:         'SATELLITE'
 *   r:            {x, y, z}     — ECI position (km)
 *   v:            {x, y, z}     — ECI velocity (km/s)
 *   timestamp:    Date          — time of last update
 *   dryMass:      number        — 500.0 kg (constant)
 *   fuelKg:       number        — current propellant mass (kg)
 *   currentMass:  number        — dryMass + fuelKg (updated after every burn)
 *   status:       string        — NOMINAL | EVADING | RECOVERING | EOL
 *   nominalSlot:  {x, y, z}     — ECI position of ideal orbital slot (set at first telemetry)
 *   lastBurnTime: Date | null   — timestamp of last executed burn (for cooldown checks)
 * }
 *
 * Debris state shape:
 * {
 *   id:        string
 *   type:      'DEBRIS'
 *   r:         {x, y, z}
 *   v:         {x, y, z}
 *   timestamp: Date
 * }
 */

// Physical constants for new satellite initialization
const DRY_MASS_KG     = 500.0;
const INITIAL_FUEL_KG = 50.0;

const satellites   = new Map();  // id -> satellite object
const debrisObjects = new Map(); // id -> debris object

/**
 * Upserts an object into state. New satellites are initialized with full fuel load.
 * Existing objects have only r, v, and timestamp updated (preserves fuel/status).
 *
 * @param {{ id, type, r, v, timestamp }} obj
 */
function upsert(obj) {
  const { id, type, r, v, timestamp } = obj;

  if (type === 'SATELLITE') {
    if (satellites.has(id)) {
      const existing = satellites.get(id);
      existing.r         = { ...r };
      existing.v         = { ...v };
      existing.timestamp = timestamp;
    } else {
      // Accept fuelKg from seed data; fall back to INITIAL_FUEL_KG if not provided
      const fuel = (typeof obj.fuelKg === 'number' && obj.fuelKg > 0) ? obj.fuelKg : INITIAL_FUEL_KG;
      // Accept nominalR from seed data if provided
      const nominal = obj.nominalR ? { ...obj.nominalR } : { x: r.x, y: r.y, z: r.z };
      satellites.set(id, {
        id,
        type: 'SATELLITE',
        r:            { ...r },
        v:            { ...v },
        timestamp,
        dryMass:      DRY_MASS_KG,
        fuelKg:       fuel,
        currentMass:  DRY_MASS_KG + fuel,
        status:       'NOMINAL',
        nominalSlot:  nominal,
        nominalV:     { ...v }, // store velocity at nominal slot for SMA comparison
        lastBurnTime: null,
      });
    }
  } else if (type === 'DEBRIS') {
    if (debrisObjects.has(id)) {
      const existing = debrisObjects.get(id);
      existing.r         = { ...r };
      existing.v         = { ...v };
      existing.timestamp = timestamp;
    } else {
      debrisObjects.set(id, {
        id,
        type: 'DEBRIS',
        r:    { ...r },
        v:    { ...v },
        timestamp,
      });
    }
  }
}

function getSatellite(id) {
  return satellites.get(id) || null;
}

function getDebris(id) {
  return debrisObjects.get(id) || null;
}

function getAllSatellites() {
  return Array.from(satellites.values());
}

function getAllDebris() {
  return Array.from(debrisObjects.values());
}

/** Returns all objects (satellites + debris) as a single array. */
function getAllObjects() {
  return [...getAllSatellites(), ...getAllDebris()];
}

function getSatelliteCount() {
  return satellites.size;
}

function getDebrisCount() {
  return debrisObjects.size;
}

module.exports = {
  upsert,
  getSatellite,
  getDebris,
  getAllSatellites,
  getAllDebris,
  getAllObjects,
  getSatelliteCount,
  getDebrisCount,
  DRY_MASS_KG,
  INITIAL_FUEL_KG,
};
