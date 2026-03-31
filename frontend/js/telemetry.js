/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — Telemetry Stats Panel
   ═══════════════════════════════════════════════════════════════════════════ */

const Telemetry = (() => {
  let dvSvg = null;
  let dvLine = null;
  let dvArea = null;
  let dvXScale = null;
  let dvYScale = null;
  let isInitialized = false;

  function init() {
    if (isInitialized) return;
    isInitialized = true;
    initDvChart();
  }

  // ── CDM List ─────────────────────────────────────────────────────────────
  function updateCDMList(cdms, simTimestamp) {
    const container = document.getElementById('cdm-list');
    if (!container) return;

    const now = new Date(simTimestamp);

    // Sort by TCA (soonest first)
    const sorted = [...cdms].sort((a, b) => new Date(a.tca) - new Date(b.tca)).slice(0, 15);

    const rows = d3.select(container)
      .selectAll('.cdm-row')
      .data(sorted, (d, i) => d.satelliteId + d.debrisId + i);

    const enter = rows.enter()
      .append('div')
      .attr('class', d => `cdm-row ${d.missDistance < 0.1 ? 'critical pulse-critical' : ''}`)
      .style('cursor', 'pointer')
      .on('click', (event, d) => {
        AppState.selectSatellite(d.satelliteId);
        Globe.flyToSatelliteById(d.satelliteId);
      });

    // IDs
    const ids = enter.append('div').attr('class', 'cdm-ids');
    ids.append('span').attr('class', 'cdm-sat-id');
    ids.append('span').attr('class', 'cdm-vs').text('vs');
    ids.append('span').attr('class', 'cdm-debris-id');

    // Badge
    enter.append('span').attr('class', 'cdm-badge');

    // TCA countdown
    enter.append('span').attr('class', 'cdm-tca');

    // Merge
    const merged = enter.merge(rows);

    merged.select('.cdm-sat-id').text(d => d.satelliteId.replace('SAT-',''));
    merged.select('.cdm-debris-id').text(d => d.debrisId);

    merged.select('.cdm-badge')
      .text(d => {
        if (d.missDistance < 0.1) return `${(d.missDistance * 1000).toFixed(0)}m`;
        return `${d.missDistance.toFixed(2)}km`;
      })
      .attr('class', d => `cdm-badge ${d.missDistance < 0.1 ? 'red' : (d.missDistance < 5 ? 'amber' : 'green')}`);

    merged.select('.cdm-tca')
      .text(d => {
        const tcaDate = new Date(d.tca);
        const diffMs = tcaDate - now;
        if (diffMs <= 0) return 'T+0';
        const h = Math.floor(diffMs / 3600000);
        const m = Math.floor((diffMs % 3600000) / 60000);
        return `T-${h}h${String(m).padStart(2,'0')}m`;
      })
      .style('color', d => {
        const tcaDate = new Date(d.tca);
        const hoursToTCA = (tcaDate - now) / 3600000;
        if (hoursToTCA < 2) return '#e74c3c';
        if (hoursToTCA < 8) return '#f39c12';
        return '#5a7a9a';
      });

    merged.attr('class', d => `cdm-row ${d.missDistance < 0.1 ? 'critical pulse-critical' : ''}`);

    rows.exit().remove();
  }

  // ── ΔV Cost Chart ────────────────────────────────────────────────────────
  function initDvChart() {
    const container = document.getElementById('dv-chart');
    if (!container) return;

    const rect = container.getBoundingClientRect();
    const w = rect.width || 200;
    const h = rect.height || 60;

    dvSvg = d3.select('#dv-chart')
      .attr('width', w)
      .attr('height', h);

    dvXScale = d3.scaleLinear().domain([0, 19]).range([0, w]);
    dvYScale = d3.scaleLinear().domain([0, 10]).range([h, 0]);

    // Area
    dvArea = d3.area()
      .x((d, i) => dvXScale(i))
      .y0(h)
      .y1(d => dvYScale(d))
      .curve(d3.curveMonotoneX);

    // Line
    dvLine = d3.line()
      .x((d, i) => dvXScale(i))
      .y(d => dvYScale(d))
      .curve(d3.curveMonotoneX);

    dvSvg.append('path')
      .attr('class', 'dv-area-path')
      .attr('fill', 'rgba(74,158,255,0.1)')
      .attr('stroke', 'none');

    dvSvg.append('path')
      .attr('class', 'dv-line-path')
      .attr('fill', 'none')
      .attr('stroke', '#4a9eff')
      .attr('stroke-width', 1.5);
  }

  function updateDvChart(dvHistory) {
    if (!dvSvg || !dvHistory.length) return;

    // Pad to 20 points
    const data = dvHistory.length < 20
      ? Array(20 - dvHistory.length).fill(0).concat(dvHistory)
      : dvHistory.slice(-20);

    const maxVal = Math.max(1, d3.max(data));
    dvYScale.domain([0, maxVal * 1.1]);

    dvSvg.select('.dv-area-path')
      .transition().duration(300)
      .attr('d', dvArea(data));

    dvSvg.select('.dv-line-path')
      .transition().duration(300)
      .attr('d', dvLine(data));

    // Total annotation
    const totalEl = document.getElementById('dv-total');
    if (totalEl) {
      totalEl.textContent = data[data.length - 1].toFixed(2) + ' m/s';
    }
  }

  // ── System Health ────────────────────────────────────────────────────────
  function updateHealth(latency, timestamp) {
    const latencyEl = document.getElementById('health-latency');
    const ingestionEl = document.getElementById('health-ingestion');
    const snapshotEl = document.getElementById('health-snapshot');

    if (latencyEl) {
      latencyEl.textContent = latency + ' ms';
      latencyEl.style.color = latency < 200 ? '#2ecc71' : (latency < 500 ? '#f39c12' : '#e74c3c');
    }

    if (ingestionEl) {
      const rate = API.isDemo() ? '~demo' : '10K obj/s';
      ingestionEl.textContent = rate;
    }

    if (snapshotEl && timestamp) {
      const t = new Date(timestamp);
      snapshotEl.textContent = t.toISOString().slice(11, 19) + 'Z';
    }
  }

  return { init, updateCDMList, updateDvChart, updateHealth };
})();
