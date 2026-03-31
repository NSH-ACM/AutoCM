'use strict';
const express = require('express');
const router  = express.Router();
const { getConstellationStats } = require('../controllers/constellationController');

router.get('/stats', getConstellationStats);

module.exports = router;
