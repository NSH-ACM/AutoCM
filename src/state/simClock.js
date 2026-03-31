'use strict';

/**
 * Simulation Clock
 * Single source of truth for the current simulation time.
 * Initialized to server startup time; updated by /api/telemetry (first ingest)
 * and advanced by /api/simulate/step.
 */

let currentTime = new Date();

function getCurrentTime() {
  return new Date(currentTime);
}

function setCurrentTime(date) {
  currentTime = new Date(date);
}

function advanceBy(seconds) {
  currentTime = new Date(currentTime.getTime() + seconds * 1000);
}

module.exports = { getCurrentTime, setCurrentTime, advanceBy };
