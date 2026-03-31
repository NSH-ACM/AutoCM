'use strict';

const { Router } = require('express');
const { getSnapshot } = require('../controllers/visualizationController');

const router = Router();
router.get('/snapshot', getSnapshot);

module.exports = router;
