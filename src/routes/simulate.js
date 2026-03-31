'use strict';

const { Router } = require('express');
const { simulateStep, startAutoSim, stopAutoSim, getAutoSimStatus } = require('../controllers/simulateController');

const router = Router();
router.post('/step',   simulateStep);
router.post('/run',    startAutoSim);
router.post('/stop',   stopAutoSim);
router.get('/status',  getAutoSimStatus);

module.exports = router;
