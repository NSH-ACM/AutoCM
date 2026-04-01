/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — Main Application Entry Point
   Glassmorphism Edition: Particles, GSAP Choreography, Split.js Resize
   ═══════════════════════════════════════════════════════════════════════════ */

(function () {
  'use strict';

  const SNAPSHOT_INTERVAL = 2000;
  const STATS_INTERVAL    = 4000;
  const CLOCK_INTERVAL    = 1000;

  let simTimestamp = new Date().toISOString();
  let cdmCache = [];
  let maneuverCache = [];
  let prevStatValues = {};

  // ══════════════════════════════════════════════════════════════════════════
  // INIT
  // ══════════════════════════════════════════════════════════════════════════
  document.addEventListener('DOMContentLoaded', () => {
    // Init Lucide icons
    if (window.lucide) lucide.createIcons();

    // Setup resizable panels with Split.js
    initSplitPanels();

    // Init background effects
    initParticleField();

    // Init all modules (after split layout settles)
    setTimeout(() => {
      Globe.init();
      Bullseye.init();
      FuelPanel.init();
      Gantt.init();
      Telemetry.init();
      SpeedControl.init();
      Alerts.init();
      Drawer.init();

      // Wire up events
      setupEventListeners();

      // Start Telemetry (WebSocket preferred, falls back to polling)
      if (typeof WSTelemetry !== 'undefined') {
        WSTelemetry.onSnapshot((data) => {
          handleDataUpdate(data, 10); // Simulated ping for WS
        });
        WSTelemetry.connect();
        // Keep a slow poll just in case WS drops
        setInterval(pollSnapshot, SNAPSHOT_INTERVAL * 2);
      } else {
        pollSnapshot();
        setInterval(pollSnapshot, SNAPSHOT_INTERVAL);
      }

      // Real ΔV stats polling (uses /api/constellation/stats)
      pollConstellationStats();
      setInterval(pollConstellationStats, STATS_INTERVAL);

      // Sim clock
      setInterval(updateSimClock, CLOCK_INTERVAL);

      // GSAP Entrance Choreography
      playEntranceSequence();

      // Sim-step event fires when SpeedControl does a manual step
      document.addEventListener('sim-step', () => {
        pollSnapshot();
        pollConstellationStats();
      });
    }, 100);

    // Resize handler
    let resizeTimer;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(handleResize, 200);
    });

    // Close context menu
    document.addEventListener('click', () => Globe.hideContextMenu());
  });

  // ══════════════════════════════════════════════════════════════════════════
  // SPLIT.JS — Resizable Panels
  // ══════════════════════════════════════════════════════════════════════════
  function initSplitPanels() {
    // Vertical split: upper row / lower row
    Split(['#upper-row', '#lower-row'], {
      direction: 'vertical',
      sizes: [58, 42],
      minSize: [250, 200],
      gutterSize: 4,
      cursor: 'row-resize',
      onDragEnd: handleResize,
    });

    // Upper row horizontal split: globe / bullseye
    Split(['#globe-panel', '#bullseye-panel'], {
      sizes: [68, 32],
      minSize: [300, 250],  // Bullseye cannot go below 250px
      gutterSize: 4,
      cursor: 'col-resize',
      onDragEnd: handleResize,
    });

    // Lower row horizontal split: fuel / gantt / telemetry / alerts
    Split(['#fuel-panel', '#gantt-panel', '#telemetry-panel', '#alerts-panel'], {
      sizes: [14, 38, 28, 20],
      minSize: [120, 250, 200, 150],
      gutterSize: 4,
      cursor: 'col-resize',
      onDragEnd: handleResize,
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // ENTRANCE — Quick fade-in (no heavy choreography)
  // ══════════════════════════════════════════════════════════════════════════
  function playEntranceSequence() {
    // Simple fast fade — everything visible immediately
    if (!window.gsap) return;
    gsap.from('#app', { opacity: 0, duration: 0.5, ease: 'power2.out' });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // PARTICLE STAR FIELD — Background ambient particles
  // ══════════════════════════════════════════════════════════════════════════
  function initParticleField() {
    const canvas = document.getElementById('particle-canvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    let width = canvas.width = window.innerWidth;
    let height = canvas.height = window.innerHeight;

    const PARTICLE_COUNT = 60;
    const particles = [];

    class Particle {
      constructor() {
        this.reset();
      }
      reset() {
        this.x = Math.random() * width;
        this.y = Math.random() * height;
        this.size = Math.random() * 1.5 + 0.5;
        this.speedX = (Math.random() - 0.5) * 0.15;
        this.speedY = (Math.random() - 0.5) * 0.1;
        this.opacity = Math.random() * 0.4 + 0.1;
        this.pulseSpeed = Math.random() * 0.02 + 0.005;
        this.pulseOffset = Math.random() * Math.PI * 2;
      }
      update(time) {
        this.x += this.speedX;
        this.y += this.speedY;
        if (this.x < 0 || this.x > width) this.speedX *= -1;
        if (this.y < 0 || this.y > height) this.speedY *= -1;
        this.currentOpacity = this.opacity * (0.5 + 0.5 * Math.sin(time * this.pulseSpeed + this.pulseOffset));
      }
      draw(ctx) {
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(74, 158, 255, ${this.currentOpacity})`;
        ctx.fill();
        // Tiny glow
        ctx.beginPath();
        ctx.arc(this.x, this.y, this.size * 3, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(74, 158, 255, ${this.currentOpacity * 0.1})`;
        ctx.fill();
      }
    }

    for (let i = 0; i < PARTICLE_COUNT; i++) {
      particles.push(new Particle());
    }

    let time = 0;
    function animate() {
      ctx.clearRect(0, 0, width, height);
      time++;
      particles.forEach(p => {
        p.update(time);
        p.draw(ctx);
      });

      // Occasional connection lines between close particles
      for (let i = 0; i < particles.length; i++) {
        for (let j = i + 1; j < particles.length; j++) {
          const dx = particles[i].x - particles[j].x;
          const dy = particles[i].y - particles[j].y;
          const dist = Math.sqrt(dx * dx + dy * dy);
          if (dist < 120) {
            ctx.beginPath();
            ctx.moveTo(particles[i].x, particles[i].y);
            ctx.lineTo(particles[j].x, particles[j].y);
            ctx.strokeStyle = `rgba(74, 158, 255, ${0.04 * (1 - dist / 120)})`;
            ctx.lineWidth = 0.5;
            ctx.stroke();
          }
        }
      }

      requestAnimationFrame(animate);
    }
    animate();

    window.addEventListener('resize', () => {
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // CONSTELLATION STATS POLLING (Real ΔV data)
  // ══════════════════════════════════════════════════════════════════════════
  async function pollConstellationStats() {
    try {
      const stats = await API.fetchConstellationStats();
      if (!stats) {
        // Demo mode: generate synthetic ΔV that grows slowly
        if (API.isDemo()) {
          const elapsed = (API.getDemoTime() - new Date('2026-03-12T08:00:00Z')) / 3600000;
          const syntheticDv = elapsed * 0.12; // ~0.12 m/s per sim-hour
          AppState.addDvDataPoint(syntheticDv);
          Telemetry.updateDvChart(AppState.state.dvHistory);

          const totalEl = document.getElementById('dv-total');
          if (totalEl) totalEl.textContent = syntheticDv.toFixed(2) + ' m/s';
        }
        return;
      }

      // Real data from /api/constellation/stats
      const realDvMs = stats.maneuvers?.total_dv_ms || 0;
      AppState.addDvDataPoint(realDvMs);
      Telemetry.updateDvChart(AppState.state.dvHistory);

      const totalEl = document.getElementById('dv-total');
      if (totalEl) totalEl.textContent = realDvMs.toFixed(2) + ' m/s';

      // Also update alert count from stats
      const alertEl = document.getElementById('stat-alerts');
      if (alertEl && stats.conjunctions) {
        animateStat('stat-alerts', stats.conjunctions.total_raised);
      }

      if (stats.engine) {
        const engineEl = document.getElementById('health-physics');
        if (engineEl) {
           engineEl.textContent = stats.engine.engine_type === 'cpp' ? 'CPP_O3' : 'MOCK_PY';
           engineEl.className = stats.engine.engine_type === 'cpp' ? 'value text-green' : 'value text-amber';
        }

        const ingestionEl = document.getElementById('health-ingestion');
        if (ingestionEl) ingestionEl.textContent = (stats.engine.wrapper_avg_ms || 0).toFixed(1) + ' ms/cyc';
      }
    } catch (e) {
      console.warn('[Stats] Failed to poll constellation stats:', e.message);
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // POLLING — Snapshot (Fallback)
  // ══════════════════════════════════════════════════════════════════════════
  async function pollSnapshot() {
    if (typeof WSTelemetry !== 'undefined' && WSTelemetry.connected) return; // Skip if WS is active
    try {
      const start = performance.now();
      const data = await API.fetchSnapshot();
      const latency = Math.round(performance.now() - start);
      handleDataUpdate(data, latency);
    } catch (e) {
      console.error('[Poll] Snapshot error:', e);
    }
  }

  function handleDataUpdate(data, latency) {
    if (!data) return;

    AppState.setApiLatency(latency);
    simTimestamp = data.timestamp;
    cdmCache = data.cdms || [];
    maneuverCache = data.maneuvers || [];

    AppState.updateSnapshot(data);
    AppState.updateCDMs(cdmCache);
    AppState.updateManeuvers(maneuverCache);

    if (typeof Globe !== 'undefined') {
      Globe.updateSatellites(data.satellites);
      Globe.updateDebris(data.debris_cloud);
      Globe.updateConjunctions(cdmCache);
    }
    
    if (typeof FuelPanel !== 'undefined') FuelPanel.update(data.satellites);
    updateTopbarStats(data);
    
    if (typeof Bullseye !== 'undefined') Bullseye.update(cdmCache, simTimestamp);
    if (typeof Gantt !== 'undefined') Gantt.update(maneuverCache, simTimestamp);
    
    if (typeof Telemetry !== 'undefined') {
      Telemetry.updateHealth(latency, data.timestamp);
      Telemetry.updateCDMList(cdmCache, simTimestamp);
    }

    // Engine status is now updated during pollConstellationStats

    // Update critical CDM count organically
    const criticalCount = cdmCache.filter(c => c.missDistance < 0.1).length;
    const cdmEl = document.getElementById('stat-cdms');
    if (cdmEl) {
      cdmEl.textContent = criticalCount;
      cdmEl.parentElement.classList.toggle('pulse-critical', criticalCount > 0);
    }

    // Auto-select most threatened satellite
    if (!AppState.state.selectedSatelliteId && data.satellites.length > 0) {
      const evading = data.satellites.find(s => s.status === 'EVADING');
      AppState.selectSatellite((evading || data.satellites[0]).id);
    }

    // Live-update the drawer if open
    if (typeof Drawer !== 'undefined') {
      Drawer.update(data.satellites, cdmCache, maneuverCache);
    }

    // Data flash animation on panels
    flashPanel('globe-panel');
  }

  // ══════════════════════════════════════════════════════════════════════════
  // DATA FLASH — Visual feedback when panels update
  // ══════════════════════════════════════════════════════════════════════════
  function flashPanel(panelId) {
    const el = document.getElementById(panelId);
    if (!el) return;
    el.classList.remove('data-flash');
    void el.offsetWidth; // force reflow
    el.classList.add('data-flash');
    setTimeout(() => el.classList.remove('data-flash'), 1200);
  }

  // ══════════════════════════════════════════════════════════════════════════
  // TOPBAR STATS (with animated number transitions)
  // ══════════════════════════════════════════════════════════════════════════
  function updateTopbarStats(data) {
    const sats = data.satellites || [];

    const activeSats = sats.filter(s => s.status !== 'EOL').length;
    animateStat('stat-sats', activeSats);

    animateStat('stat-debris', (data.debris_cloud || []).length, true);

    const uptime = sats.length > 0 ? ((activeSats / sats.length) * 100) : 0;
    const uptimeEl = document.getElementById('stat-uptime');
    if (uptimeEl) {
      uptimeEl.textContent = uptime.toFixed(1) + '%';
      uptimeEl.style.color = uptime > 95 ? '#2ecc71' : (uptime > 80 ? '#f39c12' : '#e74c3c');
    }

    const avgFuel = sats.length > 0 ? sats.reduce((sum, s) => sum + s.fuel_kg, 0) / sats.length : 0;
    const avgPct = (avgFuel / 50) * 100;
    const fuelEl = document.getElementById('stat-fuel');
    if (fuelEl) {
      fuelEl.textContent = avgPct.toFixed(0) + '%';
      fuelEl.style.color = avgPct > 60 ? '#2ecc71' : (avgPct > 30 ? '#f39c12' : '#e74c3c');
    }
  }

  function animateStat(id, newValue, formatNum = false) {
    const el = document.getElementById(id);
    if (!el) return;
    const displayValue = formatNum ? newValue.toLocaleString() : String(newValue);
    const prevValue = prevStatValues[id];

    if (prevValue !== displayValue) {
      prevStatValues[id] = displayValue;
      el.textContent = displayValue;

      // GSAP number pop animation
      if (window.gsap) {
        gsap.fromTo(el,
          { scale: 1.3, color: '#fff' },
          { scale: 1, color: el.style.color || '#4a9eff', duration: 0.4, ease: 'back.out(2)' }
        );
      }
    }
  }

  // ══════════════════════════════════════════════════════════════════════════
  // SIM CLOCK WITH TYPING EFFECT
  // ══════════════════════════════════════════════════════════════════════════
  function updateSimClock() {
    const clockEl = document.getElementById('sim-clock');
    if (!clockEl || !simTimestamp) return;
    const t = new Date(simTimestamp);
    clockEl.textContent = `SIM ${t.toISOString().replace('T', ' ').slice(0, 19)}Z`;
  }

  // ══════════════════════════════════════════════════════════════════════════
  // EVENT LISTENERS
  // ══════════════════════════════════════════════════════════════════════════
  function setupEventListeners() {
    AppState.on('satellite-selected', (satId) => {
      const satIdEl = document.getElementById('bullseye-sat-id');
      if (satIdEl) {
        satIdEl.textContent = satId;
        if (window.gsap) {
          gsap.from(satIdEl, { x: 20, opacity: 0, duration: 0.3, ease: 'power2.out' });
        }
      }

      const satCDMs = AppState.getCDMsForSatellite(satId);
      Bullseye.update(satCDMs.length > 0 ? satCDMs : cdmCache, simTimestamp);
      FuelPanel.update(AppState.state.satellites);
    });

    document.querySelectorAll('.context-menu-item').forEach(item => {
      item.addEventListener('click', (e) => {
        const action = e.currentTarget.dataset.action;
        const menu = document.getElementById('context-menu');
        const sat = menu?._targetSat;
        if (!sat) return;

        switch (action) {
          case 'track-camera':   Globe.flyToSatelliteById(sat.id); break;
          case 'view-telemetry': AppState.selectSatellite(sat.id); break;
          case 'open-drawer': {
            const satCDMs = AppState.getCDMsForSatellite(sat.id);
            Drawer.open(sat, satCDMs, maneuverCache);
            break;
          }
          case 'schedule-maneuver': console.log('[Action] Schedule maneuver:', sat.id); break;
        }
        Globe.hideContextMenu();
      });
    });

    // Also open drawer on fuel-panel row click
    document.getElementById('fuel-list')?.addEventListener('click', (e) => {
      const row = e.target.closest('.fuel-row');
      if (!row) return;
      const satId = row.dataset.satId;
      const sat = AppState.state.satellites?.find(s => s.id === satId);
      if (sat) {
        AppState.selectSatellite(satId);
        const satCDMs = AppState.getCDMsForSatellite(satId);
        Drawer.open(sat, satCDMs, maneuverCache);
      }
    });
  }

  // ══════════════════════════════════════════════════════════════════════════
  // RESIZE HANDLER
  // ══════════════════════════════════════════════════════════════════════════
  function handleResize() {
    Bullseye.resize();
    Gantt.resize();
    if (cdmCache.length) {
      Bullseye.update(cdmCache, simTimestamp);
      Gantt.update(maneuverCache, simTimestamp);
    }
  }

})();
