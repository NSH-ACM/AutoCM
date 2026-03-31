/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — Enhanced API Layer
   ═══════════════════════════════════════════════════════════════════════════ */

const API = (() => {
  const BASE = '';
  let useDemo = false;
  let demoTime = new Date('2026-03-12T08:00:00Z');

  // ── Demo Data Generator ────────────────────────────────────────────────────
  function _mulberry32(seed) {
    return function () {
      seed |= 0; seed = seed + 0x6D2B79F5 | 0;
      let t = Math.imul(seed ^ seed >>> 15, 1 | seed);
      t = t + Math.imul(t ^ t >>> 7, 61 | t) ^ t;
      return ((t ^ t >>> 14) >>> 0) / 4294967296;
    };
  }
  const _rng = _mulberry32(0xACE0FFEE);

  function generateDemoSatellites(count = 50) {
    const statuses = ['NOMINAL','NOMINAL','NOMINAL','NOMINAL','EVADING','RECOVERING','EOL'];
    const planes   = ['Alpha','Beta','Gamma','Delta','Epsilon'];
    const sats = [];
    for (let i = 0; i < count; i++) {
      const plane = planes[Math.floor(i / 10)];
      const num   = String((i % 10) + 1).padStart(2, '0');
      const inc   = 55;
      const phase = (i / count) * 360 + (demoTime.getTime() / 60000) * 0.06;
      const raan  = (Math.floor(i / 10) * 72);
      const lat   = inc * Math.sin(phase * Math.PI / 180);
      const lon   = ((phase + raan) % 360) - 180;
      const status = i === 3 ? 'EVADING' : i === 7 ? 'RECOVERING' : i === 12 ? 'EOL' :
                     (_rng() < 0.08 ? 'EVADING' : 'NOMINAL');
      sats.push({
        id:      `SAT-${plane}-${num}`,
        lat:     parseFloat(lat.toFixed(4)),
        lon:     parseFloat(lon.toFixed(4)),
        fuel_kg: status === 'EOL' ? 1.2 : parseFloat((5 + _rng() * 45).toFixed(2)),
        status,
      });
    }
    return sats;
  }

  // Pre-generate debris once (expensive — 10k entries)
  let _demoDebris = null;
  function generateDemoDebris(count = 10000) {
    if (_demoDebris) return _demoDebris;
    const debris = [];
    const dr = _mulberry32(0xDEADBEEF);
    for (let i = 0; i < count; i++) {
      debris.push([
        `DEB-${String(i).padStart(5,'0')}`,
        parseFloat(((dr() - 0.5) * 170).toFixed(3)),
        parseFloat(((dr() - 0.5) * 360).toFixed(3)),
        parseFloat((380 + dr() * 270).toFixed(1)),
      ]);
    }
    _demoDebris = debris;
    return debris;
  }

  function generateDemoCDMs(satellites) {
    const cdms = [];
    const threatened = satellites.filter(s => s.status === 'EVADING' || _rng() < 0.12);
    threatened.forEach(sat => {
      const missKm = _rng() < 0.25 ? _rng() * 0.1 : (_rng() < 0.5 ? _rng() * 2 : 2 + _rng() * 10);
      cdms.push({
        satelliteId: sat.id,
        debrisId: `DEB-${String(Math.floor(_rng() * 10000)).padStart(5,'0')}`,
        tca: new Date(demoTime.getTime() + _rng() * 20 * 3600000).toISOString(),
        missDistance: parseFloat(missKm.toFixed(4)),
        probability:  missKm < 0.1 ? 0.01 + _rng() * 0.05 : (_rng() * 0.001),
        status:       'ACTIVE',
      });
    });
    return cdms;
  }

  function generateDemoManeuvers(satellites) {
    const maneuvers = [];
    const active = satellites.filter(s => s.status !== 'EOL').slice(0, 8);
    active.forEach(sat => {
      const burnCount = 1 + Math.floor(_rng() * 3);
      let offset = -2 + _rng() * 2;
      for (let i = 0; i < burnCount; i++) {
        const burnTime = new Date(demoTime.getTime() + offset * 3600000);
        const duration = 120 + _rng() * 300;
        const type     = i === 0 ? 'EVASION BURN' : (i === 1 ? 'COOLDOWN' : 'RECOVERY BURN');
        maneuvers.push({
          satelliteId: sat.id,
          burnId:      `BURN-${sat.id}-${i}`,
          burnTime:    burnTime.toISOString(),
          duration,
          type,
          deltaV:  { x: 0.002, y: 0, z: 0 },
          status:  offset < 0 ? 'EXECUTED' : 'PENDING',
          fuelCost: parseFloat((0.1 + _rng() * 0.5).toFixed(3)),
        });
        offset += (duration + 600) / 3600;
      }
    });
    return maneuvers;
  }

  let _demoSats = null;
  let _demoCDMCache = null;

  function getDemoSnapshot() {
    demoTime = new Date(demoTime.getTime() + 2000);
    if (!_demoSats) _demoSats = generateDemoSatellites(50);

    // Drift satellites each call
    _demoSats.forEach(s => {
      s.lon = parseFloat(((s.lon + 0.04 + 180) % 360 - 180).toFixed(4));
      if (s.status !== 'EOL') s.fuel_kg = Math.max(0, s.fuel_kg - _rng() * 0.005);
    });

    const cdms = generateDemoCDMs(_demoSats);
    const maneuvers = generateDemoManeuvers(_demoSats);

    return {
      timestamp:    demoTime.toISOString(),
      satellites:   _demoSats,
      debris_cloud: generateDemoDebris(10000),
      cdms,
      maneuvers,
    };
  }

  // ── Resilient fetch helper with timeout ────────────────────────────────────
  async function _fetch(path, opts = {}, timeoutMs = 5000) {
    const controller = new AbortController();
    const tid = setTimeout(() => controller.abort(), timeoutMs);
    try {
      const res = await fetch(BASE + path, { signal: controller.signal, ...opts });
      clearTimeout(tid);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch (e) {
      clearTimeout(tid);
      throw e;
    }
  }

  // ── Public API ─────────────────────────────────────────────────────────────
  async function fetchSnapshot() {
    if (useDemo) return getDemoSnapshot();
    try {
      return await _fetch('/api/visualization/snapshot');
    } catch (e) {
      console.warn('[API] Switching to demo mode:', e.message);
      useDemo = true;
      return getDemoSnapshot();
    }
  }

  async function fetchAlerts(afterId = 0) {
    if (useDemo) return { alerts: [], latest_id: afterId };
    try {
      return await _fetch(`/api/alerts?after=${afterId}`);
    } catch (_) { return { alerts: [], latest_id: afterId }; }
  }

  async function fetchConstellationStats() {
    if (useDemo) return null;
    try {
      return await _fetch('/api/constellation/stats');
    } catch (_) { return null; }
  }

  async function simulateStep(stepSeconds = 60) {
    if (useDemo) { demoTime = new Date(demoTime.getTime() + stepSeconds * 1000); return null; }
    return _fetch('/api/simulate/step', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step_seconds: stepSeconds }),
    });
  }

  async function startAutoSim(stepSeconds = 60, intervalMs = 1000) {
    if (useDemo) return;
    return _fetch('/api/simulate/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ step_seconds: stepSeconds, real_interval_ms: intervalMs }),
    });
  }

  async function stopAutoSim() {
    if (useDemo) return;
    try {
      return await _fetch('/api/simulate/stop', { method: 'POST' });
    } catch (_) {}
  }

  async function getSimStatus() {
    if (useDemo) return { running: false };
    try { return await _fetch('/api/simulate/status'); } catch (_) { return { running: false }; }
  }

  async function fetchHealth() {
    if (useDemo) return { status: 'OK (DEMO)', sim_time: demoTime.toISOString() };
    try { return await _fetch('/health'); } catch (_) { return null; }
  }

  function getDemoCDMs() {
    if (!_demoSats) return [];
    _demoCDMCache = generateDemoCDMs(_demoSats);
    return _demoCDMCache;
  }

  function getDemoManeuvers() {
    if (!_demoSats) return [];
    return generateDemoManeuvers(_demoSats);
  }

  function isDemo()    { return useDemo; }
  function getDemoTime() { return demoTime; }

  return {
    fetchSnapshot, fetchAlerts, fetchConstellationStats,
    simulateStep, startAutoSim, stopAutoSim, getSimStatus,
    fetchHealth,
    getDemoCDMs, getDemoManeuvers,
    isDemo, getDemoTime,
  };
})();
