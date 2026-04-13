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

    const rect = container.getBoundingClientRect();
    width = rect.width;
    height = rect.height;

    projection
      .scale(width / 2 / Math.PI)
      .translate([width / 2, height / 2]);

    svg.attr('width', width).attr('height', height);
    g.selectAll('*').remove();
    drawStaticElements();
  }

  // ── Static Elements ──────────────────────────────────────────────────────
  function drawStaticElements() {
    // World map background (simple outline)
    g.append('rect')
      .attr('width', width)
      .attr('height', height)
      .attr('fill', 'rgba(3, 5, 8, 0.8)')
      .attr('stroke', '#1a2a3e')
      .attr('stroke-width', 1);

    // Grid lines
    for (let lon = -180; lon <= 180; lon += 30) {
      const line = d3.geoGraticule().step([30, 30])();
      g.append('path')
        .datum(d3.geoCircle().center([0, 0]).radius(90)())
        .attr('d', d3.geoPath().projection(projection))
        .attr('fill', 'none')
        .attr('stroke', '#1a2a3e')
        .attr('stroke-width', 0.5)
        .attr('opacity', 0.3);
    }

    // Equator
    g.append('path')
      .datum({type: 'LineString', coordinates: [[-180, 0], [180, 0]]})
      .attr('d', d3.geoPath().projection(projection))
      .attr('fill', 'none')
      .attr('stroke', '#4a9eff')
      .attr('stroke-width', 1)
      .attr('opacity', 0.5);

    // Prime Meridian
    g.append('path')
      .datum({type: 'LineString', coordinates: [[0, -90], [0, 90]]})
      .attr('d', d3.geoPath().projection(projection))
      .attr('fill', 'none')
      .attr('stroke', '#4a9eff')
      .attr('stroke-width', 1)
      .attr('opacity', 0.5);

    // Terminator line placeholder (will be updated dynamically)
    g.append('path')
      .attr('id', 'terminator-line')
      .attr('fill', 'rgba(255, 200, 100, 0.1)')
      .attr('stroke', 'rgba(255, 200, 100, 0.4)')
      .attr('stroke-width', 2)
      .attr('stroke-dasharray', '5,5');
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
      const trailPoints = generateOrbitTrail(sat.lon, sat.lat, -90);
      g.append('path')
        .attr('class', 'sat-trail')
        .datum({type: 'LineString', coordinates: trailPoints})
        .attr('d', d3.geoPath().projection(projection))
        .attr('fill', 'none')
        .attr('stroke', '#4a9eff')
        .attr('stroke-width', 1.5)
        .attr('opacity', 0.6);

      // Predicted trajectory (90 minutes) - dashed
      const predictedPoints = generateOrbitTrail(sat.lon, sat.lat, 90);
      g.append('path')
        .attr('class', 'sat-predicted')
        .datum({type: 'LineString', coordinates: predictedPoints})
        .attr('d', d3.geoPath().projection(projection))
        .attr('fill', 'none')
        .attr('stroke', '#f39c12')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', '5,3')
        .attr('opacity', 0.7);
    });

    // Update terminator line (simplified - based on time)
    updateTerminator();
  }

  // ── Generate Orbit Trail Points ───────────────────────────────────────────
  function generateOrbitTrail(baseLon, baseLat, minutes) {
    const points = [];
    const inclination = 30 + (baseLon % 60); // Simplified inclination
    const orbitalPeriod = 90; // minutes for LEO
    const numPoints = Math.abs(minutes);
    const direction = minutes < 0 ? -1 : 1;

    for (let i = 0; i <= numPoints; i++) {
      const angle = (i / numPoints) * 360 * direction;
      const lonOffset = angle;
      const latOffset = inclination * Math.sin(angle * Math.PI / 180) * 0.7;
      const adjustedLon = ((baseLon + lonOffset + 180) % 360) - 180;
      const adjustedLat = Math.max(-85, Math.min(85, baseLat + latOffset));
      points.push([adjustedLon, adjustedLat]);
    }

    return points;
  }

  // ── Update Terminator Line ────────────────────────────────────────────────
  function updateTerminator() {
    if (!g) return;

    // Simplified terminator: vertical line at solar noon
    // In a real implementation, this would be calculated based on sun position
    const sunLon = 0; // Simplified - sun at 0° longitude
    
    const terminatorCoords = [];
    for (let lat = -90; lat <= 90; lat += 5) {
      terminatorCoords.push([sunLon, lat]);
    }
    
    // Add night side polygon
    const nightSide = [];
    nightSide.push(...terminatorCoords);
    nightSide.push([sunLon + 180, 90]);
    nightSide.push([sunLon + 180, -90]);
    
    g.select('#terminator-line')
      .datum({type: 'Polygon', coordinates: [nightSide]})
      .attr('d', d3.geoPath().projection(projection));
  }

  return { init, resize, update };
})();
