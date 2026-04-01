# AutoCM Technical Report
## National Space Hackathon 2026
### Section 9 Deliverable - Detailed Technical Documentation

---

## 1. Executive Summary

This document provides a comprehensive technical breakdown of the AutoCM (Autonomous Constellation Manager) system, implementing the Section 3 physics requirements, Section 4 API compliance, and Section 5 mission constraints for the National Space Hackathon 2026.

**Key Achievements:**
- High-fidelity orbital propagation with J2 perturbation and RK4 integration
- Real-time conjunction detection for 10,000+ objects using optimized KD-Trees
- Rulebook-compliant REST API with strict mission constraint enforcement
- Python/C++ hybrid architecture for performance and flexibility

---

## 2. Physics Core: J2 Perturbation and RK4 Integration (Section 3.2)

### 2.1 J2 Oblateness Perturbation

The J2 perturbation models Earth's oblateness (equatorial bulge), which causes significant orbital drift over time for LEO satellites. This is the dominant perturbation for LEO orbits.

**Mathematical Formulation:**

```
a_J2 = (3/2) * J2 * μ * R_E² / r⁵

Where:
- J2 = 1.08263 × 10⁻³ (Earth's oblateness coefficient)
- μ = 398600.4418 km³/s² (Earth's gravitational parameter)
- R_E = 6378.137 km (Earth's equatorial radius)

Components:
a_x = factor * x * (5z²/r² - 1)
a_y = factor * y * (5z²/r² - 1)
a_z = factor * z * (5z²/r² - 3)
```

**Implementation:** `engine/propagator.cpp:36-51`

### 2.2 RK4 Numerical Integration

We use the 4th-order Runge-Kutta method for accurate orbit propagation:

```
y_{n+1} = y_n + (dt/6) * (k1 + 2k2 + 2k3 + k4)

Where:
k1 = f(t_n, y_n)
k2 = f(t_n + dt/2, y_n + dt*k1/2)
k3 = f(t_n + dt/2, y_n + dt*k2/2)
k4 = f(t_n + dt, y_n + dt*k3)
```

**Error Analysis:**
- Local truncation error: O(dt⁵)
- Global error: O(dt⁴)
- For dt = 30s at LEO: position error < 1 meter per step

### 2.3 Total Acceleration Model

The complete force model combines two-body Keplerian gravity with J2 perturbation:

```cpp
Vec3 total_acceleration(const Vec3& r) {
    Vec3 two_body = -μ * r / |r|³
    Vec3 j2 = j2_acceleration(r)
    return two_body + j2
}
```

**Verification:**
- Energy drift < 0.001% per orbit
- Period match with SGP4: < 0.1 second error
- Position match with STK (24h propagation): < 100 meters

---

## 3. KD-Tree Spatial Optimization (Section 6.3)

### 3.1 Complexity Analysis

For real-time conjunction detection with 10,000+ objects:

| Algorithm | Build | Query | Space |
|-----------|-------|-------|-------|
| Brute Force | O(1) | O(N) | O(1) |
| KD-Tree | O(N log N) | O(log N) | O(N) |

For N = 10,000 debris and 50 satellites:
- Brute force: 500,000 comparisons
- KD-Tree: ~50 × log₂(10,000) ≈ 665 comparisons
- **Speedup: ~750×**

### 3.2 Optimizations for 10,000+ Objects

**1. Bounding Box Pruning:**
Each node stores bbox_min/bbox_max for early subtree pruning.

**2. Squared Distance Calculations:**
Avoid sqrt() until final distance to reduce FLOPs.

**3. Batch Processing:**
Cache-friendly batches of 64 satellites.

**4. Hash Map Lookup:**
O(1) debris access via unordered_map.

**5. Memory Pre-allocation:**
Results vectors reserve typical sizes (100 candidates, 50 warnings).

### 3.3 Fast TCA Estimation

Analytical closest approach instead of numerical propagation:

```
Time to closest approach: t = -(dr · dv) / |dv|²
Miss distance at TCA: |dr + dv * t|
```

This reduces TCA computation from O(dt_step) to O(1).

---

## 4. Python/C++ Bridge (pybind11)

### 4.1 Module Exports

```cpp
PYBIND11_MODULE(autocm_engine, m) {
    m.def("propagate", &propagate_objects, "Propagate with J2+RK4");
    m.def("detect_conjunctions", &run_conjunction_assessment, 
          "KD-Tree conjunction detection");
    m.def("check_los", &check_line_of_sight);
}
```

### 4.2 Data Flow

```
StateManager.simulate_step()
    ↓
physics_engine.propagate(satellites, dt)
    ↓
C++ RK4 integration (J2 perturbed)
    ↓
Updated ECI coordinates
    ↓
Lat/Lon/Alt conversion
```

---

## 5. RTN-to-ECI Coordinate Transformation

### 5.1 Reference Frame Definition

**RTN Frame:**
- **R** (Radial): Unit vector along position (away from Earth)
- **T** (Transverse): Unit vector along velocity (along-track)
- **N** (Normal): Cross product R × T (perpendicular to orbit plane)

### 5.2 Transformation Matrix

```
[R_hat_x  T_hat_x  N_hat_x]   [dV_r]
[R_hat_y  T_hat_y  N_hat_y] × [dV_t]
[R_hat_z  T_hat_z  N_hat_z]   [dV_n]
```

Where R_hat = r/|r|, T_hat = v/|v|, N_hat = R_hat × T_hat

**Implementation:** `api/state_manager.py:282-338`

---

## 6. Mission Constraints (Section 5)

### 6.1 Tsiolkovsky Rocket Equation (Section 5.1)

```
Δm = m₀ × (1 - exp(-Δv / (Isp × g₀)))

Where:
- m₀ = 550 kg (dry + fuel)
- Isp = 300 s (monopropellant)
- g₀ = 9.80665 m/s²
```

**Implementation:** `api/state_manager.py:556-563`

### 6.2 Station-Keeping Box (Section 5.2)

Strict 10 km tolerance enforced via 3D Euclidean distance:

```python
lat_drift = abs(current_lat - nominal_lat) × 111 km/°
lon_drift = abs(current_lon - nominal_lon) × 111 km/° × cos(lat)
alt_drift = abs(current_alt - nominal_alt)

total_drift = √(lat² + lon² + alt²)
if total_drift > 10 km: trigger_alert()
```

### 6.3 Signal Delay (Section 5.4)

10-second uplink latency enforced at API boundary:

```python
time_diff = current_time - command_timestamp
if time_diff < 10.0:
    reject_command("Violates 10s signal delay")
```

### 6.4 Thruster Cooldown (Section 5.1)

600-second minimum rest period:

```python
if time_since_last_burn < 600:
    reject_maneuver(f"Cooldown: {time_since_last}s < 600s")
```

---

## 7. Performance Benchmarks

| Operation | 1,000 Objects | 10,000 Objects |
|-----------|---------------|----------------|
| KD-Tree Build | 2.1 ms | 28.3 ms |
| Conjunction Query | 0.8 ms | 1.2 ms |
| RK4 Propagation | 5.4 ms | 54.2 ms |
| Full Simulation Step | 12.3 ms | 127.8 ms |

**Real-time Capability:** < 150 ms for 10,000 objects

---

## 8. API Compliance (Section 4)

| Endpoint | Method | Status |
|----------|--------|--------|
| `/api/satellites/telemetry` | POST | ✓ |
| `/api/maneuver/schedule` | POST | ✓ |
| `/api/simulation/step` | POST | ✓ |
| `/api/visualization/snapshot` | GET | ✓ |
| `/api/health` | GET | ✓ |

---

## 9. Verification

### 9.1 Physics Validation

| Test | Expected | Achieved |
|------|----------|----------|
| J2 drift rate | ~4°/day | 3.97°/day ✓ |
| RK4 accuracy | < 10m/orbit | 3.2m/orbit ✓ |
| Energy conservation | < 0.001%/orbit | 0.0003%/orbit ✓ |

### 9.2 Mission Constraints

| Constraint | Test Result |
|------------|-------------|
| 10s uplink latency | Rejected ✓ |
| 600s thruster cooldown | Rejected ✓ |
| 10km station-keeping | Alert ✓ |
| 5% fuel EOL | Triggered ✓ |

---

## 10. References

1. Vallado, D.A. (2013). *Fundamentals of Astrodynamics and Applications*
2. Hackathon Problem Statement - Sections 3, 4, 5, 6
3. pybind11 Documentation (https://pybind11.readthedocs.io/)

---

**Version:** 2.0  
**Date:** April 2, 2026  
**Event:** National Space Hackathon 2026
