/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — Conjunction Bullseye Chart (D3.js)
   ═══════════════════════════════════════════════════════════════════════════ */

const Bullseye = (() => {
  let svg = null;
  let g = null;
  let width = 0;
  let height = 0;
  let radius = 0;
  let isInitialized = false;

  // Ring boundaries in hours
  const RINGS = [
    { label: '0h', hoursMax: 0 },
    { label: '8h', hoursMax: 8 },
    { label: '16h', hoursMax: 16 },
    { label: '24h', hoursMax: 24 },
  ];

  const MAX_HOURS = 24;

  // ── Initialize ───────────────────────────────────────────────────────────
  function init() {
    if (isInitialized) return;
    isInitialized = true;

    const container = document.getElementById('bullseye-svg-container');
    if (!container) return;

    _measure(container);

    svg = d3.select('#bullseye-svg')
      .attr('viewBox', `0 0 ${width} ${height}`)
      .attr('preserveAspectRatio', 'xMidYMid meet')
      .style('width', '100%')
      .style('height', '100%');

    g = svg.append('g')
      .attr('transform', `translate(${width/2},${height/2})`);

    drawStaticElements();
  }

  function _measure(container) {
    if (!container) container = document.getElementById('bullseye-svg-container');
    if (!container) return;
    const rect = container.getBoundingClientRect();
    width = Math.max(rect.width, 200);
    height = Math.max(rect.height, 200);
    radius = Math.min(width, height) / 2 - 25;
  }

  function resize() {
    if (!svg) return;
    const container = document.getElementById('bullseye-svg-container');
    if (!container) return;
    _measure(container);
    svg.attr('viewBox', `0 0 ${width} ${height}`);
  }

  // ── Static Elements ──────────────────────────────────────────────────────
  function drawStaticElements() {
    // Background fill
    g.append('circle')
      .attr('r', radius)
      .attr('fill', 'rgba(3,5,8,0.6)')
      .attr('stroke', 'var(--border-dim)')
      .attr('stroke-width', 1);

    // Concentric rings
    const ringRadii = [radius, radius * (16/24), radius * (8/24)];
    const ringLabels = ['24h', '16h', '8h'];

    ringRadii.forEach((r, i) => {
      g.append('circle')
        .attr('r', r)
        .attr('fill', 'none')
        .attr('stroke', '#1a2a3e')
        .attr('stroke-width', 0.5)
        .attr('stroke-dasharray', i === 0 ? 'none' : '4,4');

      // Label at 3 o'clock
      g.append('text')
        .attr('x', r + 4)
        .attr('y', 3)
        .attr('fill', '#5a7a9a')
        .attr('font-size', '8px')
        .attr('font-family', 'JetBrains Mono')
        .text(ringLabels[i]);
    });

    // Critical zone — inner red circle
    const critRadius = radius * (2/24);
    g.append('circle')
      .attr('r', critRadius)
      .attr('fill', 'rgba(231,76,60,0.08)')
      .attr('stroke', '#e74c3c')
      .attr('stroke-width', 1)
      .attr('stroke-dasharray', '6,4')
      .attr('class', 'rotating-dash');

    // Center satellite dot
    g.append('circle')
      .attr('r', 4)
      .attr('fill', '#4a9eff')
      .attr('filter', 'url(#glow-blue)');

    // Radial lines (8 directions)
    for (let i = 0; i < 8; i++) {
      const angle = (i * 45 - 90) * Math.PI / 180;
      g.append('line')
        .attr('x1', 0).attr('y1', 0)
        .attr('x2', Math.cos(angle) * radius)
        .attr('y2', Math.sin(angle) * radius)
        .attr('stroke', '#1a2a3e')
        .attr('stroke-width', 0.5)
        .attr('opacity', 0.5);
    }

    // North indicator
    g.append('text')
      .attr('x', 0)
      .attr('y', -radius - 8)
      .attr('text-anchor', 'middle')
      .attr('fill', '#5a7a9a')
      .attr('font-size', '9px')
      .attr('font-family', 'JetBrains Mono')
      .text('N');

    // Radar sweep line (decorative)
    const sweepLine = g.append('line')
      .attr('x1', 0).attr('y1', 0)
      .attr('x2', 0).attr('y2', -radius)
      .attr('stroke', 'rgba(74,158,255,0.15)')
      .attr('stroke-width', 1);

    // Animate sweep
    function animateSweep() {
      sweepLine.transition()
        .duration(6000)
        .ease(d3.easeLinear)
        .attrTween('transform', () => d3.interpolateString('rotate(0)', 'rotate(360)'))
        .on('end', animateSweep);
    }
    animateSweep();

    // SVG Defs for glow filter
    const defs = svg.append('defs');

    const glowBlue = defs.append('filter').attr('id', 'glow-blue').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%');
    glowBlue.append('feGaussianBlur').attr('stdDeviation', '3').attr('result', 'blur');
    glowBlue.append('feMerge').selectAll('feMergeNode').data(['blur','SourceGraphic']).join('feMergeNode').attr('in', d => d);

    const glowRed = defs.append('filter').attr('id', 'glow-red').attr('x', '-50%').attr('y', '-50%').attr('width', '200%').attr('height', '200%');
    glowRed.append('feGaussianBlur').attr('stdDeviation', '4').attr('result', 'blur');
    glowRed.append('feMerge').selectAll('feMergeNode').data(['blur','SourceGraphic']).join('feMergeNode').attr('in', d => d);
  }

  // ── Update with CDM Data ─────────────────────────────────────────────────
  function update(cdms, simTimestamp) {
    if (!g) return;

    const now = new Date(simTimestamp);
    const satIdEl = document.getElementById('bullseye-sat-id');

    // Determine satellite context
    const selectedId = AppState.state.selectedSatelliteId;
    const relevantCDMs = selectedId
      ? cdms.filter(c => c.satelliteId === selectedId)
      : cdms.slice(0, 15);

    if (satIdEl) {
      satIdEl.textContent = selectedId || 'ALL SATELLITES';
    }

    // Map CDMs to polar coordinates
    const dots = relevantCDMs.map((cdm, i) => {
      const tcaDate = new Date(cdm.tca);
      const hoursToTCA = Math.max(0, (tcaDate - now) / 3600000);
      const r = Math.min(hoursToTCA / MAX_HOURS, 1) * radius;
      const angle = ((i * 137.508) % 360) * Math.PI / 180; // golden angle distribution

      let color = '#2ecc71'; // green > 5km
      if (cdm.missDistance < 0.1) color = '#e74c3c';
      else if (cdm.missDistance < 1) color = '#e74c3c';
      else if (cdm.missDistance < 5) color = '#f39c12';

      const size = Math.max(3, Math.min(10, cdm.probability * 500));

      return {
        x: Math.cos(angle - Math.PI/2) * r,
        y: Math.sin(angle - Math.PI/2) * r,
        color,
        size,
        cdm,
        hoursToTCA,
      };
    });

    // D3 data join with animation
    const circles = g.selectAll('.debris-dot')
      .data(dots, (d, i) => d.cdm.debrisId + '-' + i);

    // Enter
    const enter = circles.enter()
      .append('circle')
      .attr('class', 'debris-dot')
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)
      .attr('r', 0)
      .attr('fill', d => d.color)
      .attr('opacity', 0.8)
      .attr('filter', d => d.cdm.missDistance < 1 ? 'url(#glow-red)' : 'none')
      .style('cursor', 'pointer');

    enter.transition()
      .duration(600)
      .attr('r', d => d.size);

    // Tooltips
    enter.append('title')
      .text(d => `${d.cdm.debrisId}\nMiss: ${d.cdm.missDistance.toFixed(3)} km\nTCA: T-${d.hoursToTCA.toFixed(1)}h\nP(collision): ${(d.cdm.probability * 100).toFixed(3)}%`);

    // Update
    circles.transition()
      .duration(500)
      .attr('cx', d => d.x)
      .attr('cy', d => d.y)
      .attr('r', d => d.size)
      .attr('fill', d => d.color);

    circles.select('title')
      .text(d => `${d.cdm.debrisId}\nMiss: ${d.cdm.missDistance.toFixed(3)} km\nTCA: T-${d.hoursToTCA.toFixed(1)}h\nP(collision): ${(d.cdm.probability * 100).toFixed(3)}%`);

    // Exit
    circles.exit()
      .transition()
      .duration(300)
      .attr('r', 0)
      .remove();
  }

  // ── Resize ───────────────────────────────────────────────────────────────
  function resize() {
    isInitialized = false;
    if (svg) svg.selectAll('*').remove();
    init();
  }

  return { init, update, resize };
})();
