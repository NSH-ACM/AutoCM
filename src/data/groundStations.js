'use strict';

/**
 * Ground Station Network
 * Source: Problem Statement Section 5.5.1
 *
 * Used by physics/interface.js checkLOS() to determine
 * whether a satellite is reachable for command uplink.
 */
const GROUND_STATIONS = [
  {
    id:               'GS-001',
    name:             'ISTRAC_Bengaluru',
    lat:              13.0333,
    lon:              77.5167,
    elevM:            820,
    minElevAngleDeg:  5.0,
  },
  {
    id:               'GS-002',
    name:             'Svalbard_Sat_Station',
    lat:              78.2297,
    lon:              15.4077,
    elevM:            400,
    minElevAngleDeg:  5.0,
  },
  {
    id:               'GS-003',
    name:             'Goldstone_Tracking',
    lat:              35.4266,
    lon:             -116.8900,
    elevM:            1000,
    minElevAngleDeg:  10.0,
  },
  {
    id:               'GS-004',
    name:             'Punta_Arenas',
    lat:             -53.1500,
    lon:             -70.9167,
    elevM:            30,
    minElevAngleDeg:  5.0,
  },
  {
    id:               'GS-005',
    name:             'IIT_Delhi_Ground_Node',
    lat:              28.5450,
    lon:              77.1926,
    elevM:            225,
    minElevAngleDeg:  15.0,
  },
  {
    id:               'GS-006',
    name:             'McMurdo_Station',
    lat:             -77.8463,
    lon:              166.6682,
    elevM:            10,
    minElevAngleDeg:  5.0,
  },
];

module.exports = GROUND_STATIONS;
