/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — Fuel Status Gauges
   ═══════════════════════════════════════════════════════════════════════════ */

const FuelPanel = (() => {
  let container = null;
  let isInitialized = false;
  const INITIAL_FUEL = 50.0; // kg

  function init() {
    if (isInitialized) return;
    isInitialized = true;
    container = document.getElementById('fuel-list');
  }

  function update(satellites) {
    if (!container) return;

    // Sort by fuel (lowest first)
    const sorted = [...satellites].sort((a, b) => a.fuel_kg - b.fuel_kg);

    // D3 data join for smooth reordering
    const rows = d3.select(container)
      .selectAll('.fuel-row')
      .data(sorted, d => d.id);

    // Enter
    const enter = rows.enter()
      .append('div')
      .attr('class', 'fuel-row fade-in-up')
      .attr('data-sat-id', d => d.id)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        AppState.selectSatellite(d.id);
        Globe.flyToSatelliteById(d.id);
      });

    enter.append('span')
      .attr('class', 'sat-id');

    const barContainer = enter.append('div')
      .attr('class', 'fuel-bar-track');
    barContainer.append('div')
      .attr('class', 'fuel-bar-fill');

    enter.append('span')
      .attr('class', 'fuel-pct');

    // Update (enter + update)
    const merged = enter.merge(rows);

    merged.select('.sat-id')
      .text(d => d.id.replace('SAT-',''))
      .style('color', d => d.id === AppState.state.selectedSatelliteId ? '#4a9eff' : '#5a7a9a');

    merged.classed('selected', d => d.id === AppState.state.selectedSatelliteId);

    merged.select('.fuel-bar-fill')
      .style('width', d => {
        const pct = (d.fuel_kg / INITIAL_FUEL) * 100;
        return Math.min(100, Math.max(0, pct)) + '%';
      })
      .style('background-color', d => {
        const pct = (d.fuel_kg / INITIAL_FUEL) * 100;
        if (d.status === 'EOL') return '#e74c3c';
        if (pct < 30) return '#e74c3c';
        if (pct < 60) return '#f39c12';
        return '#2ecc71';
      })
      .classed('pulse-fuel-low', d => {
        const pct = (d.fuel_kg / INITIAL_FUEL) * 100;
        return pct < 30 && d.status !== 'EOL';
      });

    merged.select('.fuel-pct')
      .text(d => {
        if (d.status === 'EOL') return 'EOL';
        const pct = (d.fuel_kg / INITIAL_FUEL) * 100;
        return pct.toFixed(0) + '%';
      })
      .style('color', d => {
        if (d.status === 'EOL') return '#e74c3c';
        const pct = (d.fuel_kg / INITIAL_FUEL) * 100;
        if (pct < 30) return '#e74c3c';
        if (pct < 60) return '#f39c12';
        return '#2ecc71';
      })
      .classed('pulse-fuel-low', d => {
        const pct = (d.fuel_kg / INITIAL_FUEL) * 100;
        return pct < 30 && d.status !== 'EOL';
      });

    // Smooth ordering transition using GSAP
    merged.each(function(d, i) {
      gsap.to(this, {
        y: 0,
        duration: 0.3,
        ease: 'power2.out',
      });
    });

    // Exit
    rows.exit()
      .transition()
      .duration(300)
      .style('opacity', 0)
      .remove();

    // Re-order DOM elements to match sort
    merged.sort((a, b) => a.fuel_kg - b.fuel_kg);
  }

  return { init, update };
})();
