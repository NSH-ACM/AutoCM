/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — 2D Mercator Ground Track Map (D3.js)
   Implements Section 6.2 requirement for Mercator projection visualization
   ═══════════════════════════════════════════════════════════════════════════ */

const GroundTrack = (() => {
  let svg = null;
  let g = null;
  let width = 0;
  let height = 0;
  let isInitialized = false;
  
  // Mercator projection parameters
  const projection = d3.geoMercator()
    .scale(width / 2 / Math.PI)
    .translate([width / 2, height / 2]);

  // ── Initialize ───────────────────────────────────────────────────────────
  function init() {
    if (isInitialized) return;
    isInitialized = true;

    const container = document.getElementById('groundtrack-svg-container');
    if (!container) return;

    const rect = container.getBoundingClientRect();
    width = rect.width;
    height = rect.height;

    projection
      .scale(width / 2 / Math.PI)
      .translate([width / 2, height / 2]);

    svg = d3.select('#groundtrack-svg')
      .attr('width', width)
      .attr('height', height);

    g = svg.append('g');

    drawStaticElements();
  }

  function resize() {
    if (!svg || !projection) return;
    const container = document.getElementById('groundtrack-svg-container');
    if (!container) return;

    const parent = container.parentElement;
    if (!parent) return;

    const rect = parent.getBoundingClientRect();
    width = rect.width;
    height = rect.height;

    projection
      .scale(width / 2 / Math.PI)
      .translate([width / 2, height / 2]);

    svg
      .attr('width', width)
      .attr('height', height);

    g.selectAll('*').remove();
    drawStaticElements();
  }

  // ── Static Elements ──────────────────────────────────────────────────────
  function drawStaticElements() {
    // Background
    g.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', '#030508');

    // Graticule (latitude/longitude grid)
    const graticule = d3.geoGraticule().step([15, 15]);
    g.append('path')
      .datum(graticule())
      .attr('d', d3.geoPath().projection(projection))
      .attr('fill', 'none')
      .attr('stroke', '#1a2a3e')
      .attr('stroke-width', 0.5)
      .attr('opacity', 0.4);

    // Simplified world outline (major continents)
    const worldOutline = [
      // North America
      [[-160, 70], [-100, 70], [-60, 50], [-80, 30], [-120, 20], [-125, 50], [-130, 60], [-160, 70]],
      // South America
      [[-80, 10], [-35, -5], [-40, -30], [-70, -55], [-80, -10], [-80, 10]],
      // Europe
      [[-10, 60], [30, 60], [40, 40], [10, 35], [-5, 40], [-10, 60]],
      // Africa
      [[-20, 35], [40, 35], [50, 10], [40, -35], [20, -35], [10, 0], [-20, 35]],
      // Asia
      [[40, 70], [140, 70], [150, 30], [100, 10], [60, 20], [40, 35], [40, 70]],
      // Australia
      [[110, -20], [155, -20], [150, -40], [115, -35], [110, -20]]
    ];

    worldOutline.forEach(continent => {
      g.append('path')
        .datum({type: 'Polygon', coordinates: [continent]})
        .attr('d', d3.geoPath().projection(projection))
        .attr('fill', 'rgba(74, 158, 255, 0.05)')
        .attr('stroke', '#4a9eff')
        .attr('stroke-width', 1)
        .attr('opacity', 0.5);
    });

    // Equator
    g.append('path')
      .datum({type: 'LineString', coordinates: [[-180, 0], [180, 0]]})
      .attr('d', d3.geoPath().projection(projection))
      .attr('fill', 'none')
      .attr('stroke', '#4a9eff')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.6);

    // Prime Meridian
    g.append('path')
      .datum({type: 'LineString', coordinates: [[0, -90], [0, 90]]})
      .attr('d', d3.geoPath().projection(projection))
      .attr('fill', 'none')
      .attr('stroke', '#4a9eff')
      .attr('stroke-width', 1.5)
      .attr('opacity', 0.6);

    // Terminator line placeholder (will be updated dynamically)
    g.append('path')
      .attr('id', 'terminator-line')
      .attr('fill', 'rgba(255, 200, 100, 0.08)')
      .attr('stroke', 'rgba(255, 200, 100, 0.3)')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '8,4');
  }

  // ── Update Satellites ─────────────────────────────────────────────────────
  function update(satellites) {
    if (!g) return;

    // Remove old elements
    g.selectAll('.sat-marker').remove();
    g.selectAll('.sat-trail').remove();
    g.selectAll('.sat-predicted').remove();

    const selectedId = AppState.state.selectedSatelliteId;

    satellites.forEach(sat => {
      const isSelected = sat.id === selectedId;
      
      // Current position marker
      g.append('circle')
        .attr('class', 'sat-marker')
        .attr('cx', projection([sat.lon, sat.lat])[0])
        .attr('cy', projection([sat.lon, sat.lat])[1])
        .attr('r', isSelected ? 6 : 4)
        .attr('fill', isSelected ? '#4a9eff' : '#2ecc71')
        .attr('stroke', isSelected ? '#ffffff' : 'none')
        .attr('stroke-width', 2)
        .style('cursor', 'pointer')
        .on('click', (event) => {
          AppState.selectSatellite(sat.id);
          Globe.flyToSatelliteById(sat.id);
        });

      // Historical trail (90 minutes)
      const historicalFeature = generateOrbitTrail(sat.lon, sat.lat, -90);
      g.append('path')
        .attr('class', 'sat-trail')
        .datum(historicalFeature)
        .attr('d', d3.geoPath().projection(projection))
        .attr('fill', 'none')
        .attr('stroke', '#4a9eff')
        .attr('stroke-width', 1.5)
        .attr('opacity', 0.6);

      // Predicted trajectory (90 minutes) - dashed
      const predictedFeature = generateOrbitTrail(sat.lon, sat.lat, 90);
      g.append('path')
        .attr('class', 'sat-predicted')
        .datum(predictedFeature)
        .attr('d', d3.geoPath().projection(projection))
        .attr('fill', 'none')
        .attr('stroke', '#f39c12')
        .attr('stroke-width', 1.5)
        .attr('stroke-dasharray', '5,3')
        .attr('opacity', 0.7);
    });

    // Update terminator line (simplified - based on time)
    updateTerminator();
  }

  // ── Generate Orbit Trail Points ───────────────────────────────────────────
  function generateOrbitTrail(baseLon, baseLat, minutes) {
    const points = [];
    const inc = 55.0; // Assume 55deg inclination
    const orbitalPeriod = 95.0; // LEO period ~95min
    const numPoints = Math.abs(minutes);
    const direction = minutes < 0 ? -1 : 1;

    // Use inverse sine to approximate current orbital phase
    const currentPhase = Math.asin(Math.max(-1, Math.min(1, baseLat / inc))) * 180/Math.PI;

    for (let i = 0; i <= numPoints; i++) {
      const dt = i * direction;
      const phaseOffset = (dt / orbitalPeriod) * 360.0;
      const targetPhase = currentPhase + phaseOffset;
      
      const adjustedLat = inc * Math.sin(targetPhase * Math.PI/180);
      const earthRotationDrift = (-360.0 / (24 * 60)) * dt;
      const orbitAdvance = (dt / orbitalPeriod) * 360.0;
      
      let nextLon = baseLon + (direction > 0 ? orbitAdvance : -orbitAdvance) + earthRotationDrift;
      nextLon = ((nextLon + 180) % 360 + 360) % 360 - 180;
      
      points.push([nextLon, adjustedLat]);
    }

    // Split at antimeridian to avoid horizontal wrap glitches in D3
    const segments = [];
    let currentSegment = [points[0]];
    for (let i = 1; i < points.length; i++) {
      if (Math.abs(points[i][0] - points[i-1][0]) > 180) {
        segments.push(currentSegment);
        currentSegment = [points[i]];
      } else {
        currentSegment.push(points[i]);
      }
    }
    segments.push(currentSegment);

    return { type: 'MultiLineString', coordinates: segments };
  }

  // ── Update Terminator Line ────────────────────────────────────────────────
  function updateTerminator() {
    if (!g) return;

    // Animate sun slowly over time for the demo
    const timeRef = Date.now() / 10000;
    const sunLon = (timeRef % 360) - 180;
    const sunLat = 23.44 * Math.sin((timeRef / 365) * Math.PI * 2);

    const nightSide = [];
    for (let lon = -180; lon <= 180; lon += 5) {
      // Terminator calculation
      const phase = (lon - sunLon) * Math.PI / 180;
      let termLat = -Math.atan(Math.cos(phase) * Math.tan(sunLat * Math.PI/180)) * 180/Math.PI;
      // Clamp for numerical safety
      termLat = Math.max(-89.9, Math.min(89.9, termLat));
      nightSide.push([lon, termLat]);
    }

    // Connect polygon into the dark pole
    if (sunLat >= 0) {
        nightSide.push([180, -90], [-180, -90]); // South pole is dark
    } else {
        nightSide.push([180, 90], [-180, 90]);   // North pole is dark
    }

    g.select('#terminator-line')
      .datum({type: 'Polygon', coordinates: [nightSide]})
      .attr('d', d3.geoPath().projection(projection))
      .attr('fill', 'rgba(0, 0, 0, 0.45)')
      .attr('stroke', 'rgba(255, 100, 50, 0.25)'); // subtle eclipse glow
  }

  return { init, resize, update };
})();
