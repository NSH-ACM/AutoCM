'use strict';

const simClock = require('./simClock');

/**
 * Alert Store — mission event log with rolling history.
 * Shared singleton — all controllers push alerts here.
 * Frontend polls via GET /api/alerts.
 * Timestamps use simulation clock for chronological consistency.
 */

const MAX_ALERTS = 200;

const _alerts = [];
let _seq = 0;

/**
 * Add an alert.
 * @param {'CRITICAL'|'WARNING'|'INFO'} severity
 * @param {string} message
 */
function add(severity, message) {
  _seq++;
  _alerts.unshift({
    id:        _seq,
    severity,
    message,
    timestamp: simClock.getCurrentTime().toISOString(),
  });
  if (_alerts.length > MAX_ALERTS) _alerts.length = MAX_ALERTS;
  console.log(`[Alert:${severity}] ${message}`);
}

/** Return all alerts (newest first). */
function getAll() {
  return _alerts;
}

/** Return alerts since a given sequence number. */
function getSince(afterId) {
  return _alerts.filter(a => a.id > afterId);
}

/** Clear all alerts (called on sim reset). */
function clear() {
  _alerts.length = 0;
  _seq = 0;
}

module.exports = { add, getAll, getSince, clear };
