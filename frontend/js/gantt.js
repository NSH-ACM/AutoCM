/* ═══════════════════════════════════════════════════════════════════════════
   ORBITAL INSIGHT — Maneuver Timeline Gantt (D3.js)
   ═══════════════════════════════════════════════════════════════════════════ */

const Gantt = (() => {
  let svg = null;
  let g = null;
  let xScale = null;
  let xAxis = null;
  let xAxisGroup = null;
  let nowLine = null;
  let width = 0;
  let height = 0;
  let tooltipEl = null;
  let isInitialized = false;
  let zoom = null;

  const MARGIN = { top: 24, right: 10, bottom: 4, left: 70 };
  const ROW_HEIGHT = 22;
  const HOURS_VISIBLE = 8; // ±4h

  const BLOCK_COLORS = {
    'EVASION BURN':    { fill: '#1a3a6b', stroke: '#4a9eff', label: 'EVA' },
    'COOLDOWN':        { fill: '#2a1a08', stroke: '#f39c12', label: 'COOL' },
    'RECOVERY BURN':   { fill: '#0a2a1a', stroke: '#1abc9c', label: 'REC' },
    'GRAVEYARD BURN':  { fill: '#3a0a0a', stroke: '#e74c3c', label: 'EOL' },
  };

  function init() {
    if (isInitialized) return;
    isInitialized = true;

    const container = document.getElementById('gantt-svg-container');
    if (!container) return;

    const rect = container.getBoundingClientRect();
    width = rect.width - MARGIN.left - MARGIN.right;
    height = rect.height - MARGIN.top - MARGIN.bottom;

    tooltipEl = document.getElementById('gantt-tooltip');

    svg = d3.select('#gantt-svg')
      .attr('width', rect.width)
      .attr('height', rect.height);

    // Clip path
    svg.append('defs')
      .append('clipPath')
      .attr('id', 'gantt-clip')
      .append('rect')
      .attr('width', width)
      .attr('height', height);

    g = svg.append('g')
      .attr('transform', `translate(${MARGIN.left},${MARGIN.top})`);

    // Time scale
    const now = new Date();
    xScale = d3.scaleTime()
      .domain([new Date(now.getTime() - 4*3600000), new Date(now.getTime() + 4*3600000)])
      .range([0, width]);

    // X axis
    xAxis = d3.axisTop(xScale)
      .ticks(d3.timeMinute.every(30))
      .tickFormat(d3.timeFormat('%H:%M'))
      .tickSize(-height);

    xAxisGroup = g.append('g')
      .attr('class', 'gantt-axis')
      .call(xAxis);

    // Style axis
    xAxisGroup.selectAll('text')
      .attr('fill', '#5a7a9a')
      .attr('font-size', '8px')
      .attr('font-family', 'JetBrains Mono');
    xAxisGroup.selectAll('line')
      .attr('stroke', '#1a2a3e')
      .attr('stroke-width', 0.5);
    xAxisGroup.select('.domain')
      .attr('stroke', '#1a2a3e');

    // NOW line
    nowLine = g.append('line')
      .attr('class', 'now-line')
      .attr('y1', 0)
      .attr('y2', height)
      .attr('stroke', '#e74c3c')
      .attr('stroke-width', 1.5)
      .attr('stroke-dasharray', '4,2');

    g.append('text')
      .attr('class', 'now-label')
      .attr('fill', '#e74c3c')
      .attr('font-size', '8px')
      .attr('font-family', 'JetBrains Mono')
      .attr('letter-spacing', '1px')
      .attr('text-anchor', 'middle')
      .attr('y', -6)
      .text('NOW');

    // Blocks group
    g.append('g').attr('class', 'gantt-blocks').attr('clip-path', 'url(#gantt-clip)');

    // Row labels group
    g.append('g').attr('class', 'gantt-labels');

    // Zoom behavior (X only)
    zoom = d3.zoom()
      .scaleExtent([0.5, 4])
      .translateExtent([[-width, 0], [width * 2, height]])
      .on('zoom', (event) => {
        const newX = event.transform.rescaleX(xScale);
        xAxisGroup.call(xAxis.scale(newX));
        xAxisGroup.selectAll('text')
          .attr('fill', '#5a7a9a')
          .attr('font-size', '8px')
          .attr('font-family', 'JetBrains Mono');
        xAxisGroup.selectAll('line').attr('stroke', '#1a2a3e').attr('stroke-width', 0.5);
        xAxisGroup.select('.domain').attr('stroke', '#1a2a3e');
        updateBlockPositions(newX);
      });

    svg.call(zoom);
  }

  // ── Update ───────────────────────────────────────────────────────────────
  function update(maneuvers, simTimestamp) {
    if (!g || !xScale) return;

    const now = new Date(simTimestamp);

    // Update time domain
    xScale.domain([new Date(now.getTime() - 4*3600000), new Date(now.getTime() + 4*3600000)]);
    xAxisGroup.call(xAxis.scale(xScale));
    xAxisGroup.selectAll('text').attr('fill', '#5a7a9a').attr('font-size', '8px').attr('font-family', 'JetBrains Mono');
    xAxisGroup.selectAll('line').attr('stroke', '#1a2a3e').attr('stroke-width', 0.5);
    xAxisGroup.select('.domain').attr('stroke', '#1a2a3e');

    // NOW line
    const nowX = xScale(now);
    nowLine.attr('x1', nowX).attr('x2', nowX);
    g.select('.now-label').attr('x', nowX);

    // Group maneuvers by satellite
    const satMap = {};
    maneuvers.forEach(m => {
      if (!satMap[m.satelliteId]) satMap[m.satelliteId] = [];
      satMap[m.satelliteId].push(m);
    });

    const satIds = Object.keys(satMap).sort();

    // Row labels
    const labels = g.select('.gantt-labels')
      .selectAll('.gantt-row-label')
      .data(satIds, d => d);

    labels.enter()
      .append('text')
      .attr('class', 'gantt-row-label')
      .attr('fill', '#5a7a9a')
      .attr('font-size', '9px')
      .attr('font-family', 'JetBrains Mono')
      .attr('text-anchor', 'end')
      .attr('dominant-baseline', 'central')
      .merge(labels)
      .attr('x', -6)
      .attr('y', (d, i) => i * ROW_HEIGHT + ROW_HEIGHT / 2)
      .text(d => d.replace('SAT-',''));

    labels.exit().remove();

    // Blocks
    const allBlocks = [];
    satIds.forEach((satId, rowIdx) => {
      satMap[satId].forEach(m => {
        allBlocks.push({ ...m, rowIdx });
      });
    });

    const blocks = g.select('.gantt-blocks')
      .selectAll('.gantt-block')
      .data(allBlocks, d => d.burnId);

    const enter = blocks.enter()
      .append('g')
      .attr('class', 'gantt-block');

    enter.append('rect')
      .attr('class', 'gantt-block-bg')
      .attr('height', ROW_HEIGHT - 4)
      .attr('rx', 0);

    enter.append('text')
      .attr('class', 'gantt-block-label');

    const merged = enter.merge(blocks);

    merged.each(function(d) {
      const group = d3.select(this);
      const burnTime = new Date(d.burnTime);
      const duration = d.duration || 180;
      const endTime = new Date(burnTime.getTime() + duration * 1000);
      const colors = BLOCK_COLORS[d.type] || BLOCK_COLORS['EVASION BURN'];

      const x = xScale(burnTime);
      const w = Math.max(8, xScale(endTime) - xScale(burnTime));
      const y = d.rowIdx * ROW_HEIGHT + 2;

      const rect = group.select('.gantt-block-bg')
        .attr('x', x)
        .attr('y', y)
        .attr('width', w)
        .attr('fill', colors.fill)
        .attr('stroke', colors.stroke)
        .attr('stroke-width', 1)
        .attr('opacity', d.status === 'EXECUTED' ? 0.5 : 1);

      // Cooldown stripes
      if (d.type === 'COOLDOWN') {
        rect.style('fill', `repeating-linear-gradient(45deg, ${colors.fill}, ${colors.fill} 5px, rgba(243,156,18,0.15) 5px, rgba(243,156,18,0.15) 10px)`);
        rect.classed('cooldown-stripes', true);
      }

      group.select('.gantt-block-label')
        .attr('x', x + w/2)
        .attr('y', y + (ROW_HEIGHT - 4)/2)
        .text(colors.label);
    });

    // Tooltip hover
    merged.on('mouseenter', function(event, d) {
      if (!tooltipEl) return;
      const burnTime = new Date(d.burnTime);
      const dvMag = d.deltaV ? Math.sqrt(d.deltaV.x**2 + (d.deltaV.y||0)**2 + (d.deltaV.z||0)**2) * 1000 : 0;
      tooltipEl.innerHTML = `
        <div style="color:#4a9eff;font-weight:600;margin-bottom:4px">${d.burnId}</div>
        <div><span style="color:#5a7a9a">TYPE</span> ${d.type}</div>
        <div><span style="color:#5a7a9a">TIME</span> ${burnTime.toISOString().slice(11,19)}Z</div>
        <div><span style="color:#5a7a9a">ΔV</span> ${dvMag.toFixed(2)} m/s</div>
        <div><span style="color:#5a7a9a">FUEL</span> ${d.fuelCost?.toFixed(3) || '—'} kg</div>
        <div><span style="color:#5a7a9a">STATUS</span> ${d.status}</div>
      `;
      tooltipEl.style.left = (event.offsetX + 10) + 'px';
      tooltipEl.style.top = (event.offsetY - 80) + 'px';
      tooltipEl.classList.add('visible');
    })
    .on('mouseleave', () => {
      if (tooltipEl) tooltipEl.classList.remove('visible');
    });

    blocks.exit().remove();
  }

  function updateBlockPositions(newXScale) {
    g.select('.gantt-blocks')
      .selectAll('.gantt-block')
      .each(function(d) {
        const group = d3.select(this);
        const burnTime = new Date(d.burnTime);
        const duration = d.duration || 180;
        const endTime = new Date(burnTime.getTime() + duration * 1000);

        const x = newXScale(burnTime);
        const w = Math.max(8, newXScale(endTime) - newXScale(burnTime));

        group.select('.gantt-block-bg').attr('x', x).attr('width', w);
        group.select('.gantt-block-label').attr('x', x + w/2);
      });
  }

  function resize() {
    isInitialized = false;
    if (svg) svg.selectAll('*').remove();
    init();
  }

  return { init, update, resize };
})();
