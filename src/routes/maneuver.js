'use strict';

const { Router } = require('express');
const { scheduleManeuver } = require('../controllers/maneuverController');

const router = Router();
router.post('/schedule', scheduleManeuver);

module.exports = router;
