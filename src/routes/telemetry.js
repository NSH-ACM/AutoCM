'use strict';

const { Router } = require('express');
const { ingestTelemetry } = require('../controllers/telemetryController');

const router = Router();
router.post('/', ingestTelemetry);

module.exports = router;
