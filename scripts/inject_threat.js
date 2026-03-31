const http = require('http');

async function injectCriticalThreat() {
  console.log("Injecting guaranteed collision threat for SAT-Alpha-01...");
  
  // SAT-Alpha-01 nominal altitude is ~500km, roughly r: { "x": 6878...}
  // Let's first fetch the current state to know exactly where SAT-Alpha-01 is right now.
  let state = await new Promise((resolve) => {
    http.get('http://127.0.0.1:8000/api/visualization/snapshot', (res) => {
      let d = '';
      res.on('data', c => d+=c);
      res.on('end', () => resolve(JSON.parse(d)));
    });
  });

  const sat = state.satellites.find(s => s.id === 'SAT-Alpha-01');
  if (!sat) {
    console.log("SAT-Alpha-01 not found! Cannot inject threat.");
    return;
  }

  // Inject a debris piece exactly 1km away in the X direction, moving fast towards it
  const debrisX = sat.r.x + 1.0;
  const debrisY = sat.r.y;
  const debrisZ = sat.r.z;
  
  const vx = -0.5; // moving towards the sat relative to it
  const vy = sat.v.y;
  const vz = sat.v.z;

  const payload = JSON.stringify({
    timestamp: new Date().toISOString(),
    objects: [{
      id: "DEB-KILLER-01",
      type: "DEBRIS",
      r: { x: debrisX, y: debrisY, z: debrisZ },
      v: { x: sat.v.x - 0.5, y: sat.v.y, z: sat.v.z } // head-on approach (0.5 km/s closing speed)
    }]
  });

  const req = http.request({
    hostname: '127.0.0.1', port: 8000, path: '/api/telemetry', method: 'POST',
    headers: { 'Content-Type': 'application/json', 'Content-Length': Buffer.byteLength(payload) }
  }, (res) => {
    console.log("Threat Injected! HTTP " + res.statusCode);
  });
  req.write(payload);
  req.end();
}

injectCriticalThreat();
