# TECHNICAL REPORT
## Autonomous Constellation Manager (ACM) — Project AETHER
**National Space Hackathon 2026**

### 1. Executive Summary
Project AETHER is a high-performance, autonomous solution for Low Earth Orbit (LEO) debris avoidance and constellation management. By combining a C++ physics core with a Python-based autonomy engine, we achieve high-fidelity orbital propagation and real-time conjunction screening for thousands of objects, fulfilling the requirements for the National Space Hackathon 2026.

### 2. Numerical Methods & Physics Engine
The core physics engine is implemented in C++ for maximum performance, exposed to Python via `pybind11`.

#### 2.1 Orbital Propagation (J2 Perturbation)
We implement the J2 perturbation model to account for the Earth's equatorial bulge. The acceleration vector $\vec{a}_{J2}$ is defined as:
$$ \vec{a}_{J2} = \frac{3}{2} \frac{J_2 \mu R_E^2}{|\vec{r}|^5} \dots $$
(Implementation verified in `engine/propagator.cpp`).

#### 2.2 Numerical Integration (RK4)
To ensure high accuracy, we use a **4th-Order Runge-Kutta (RK4)** integrator. This provides a balance between computational efficiency and numerical stability, outperforming simple Euler or semi-implicit methods.

### 3. Spatial Optimization (KD-Tree)
To avoid the $O(N^2)$ bottleneck of checking every satellite against the entire debris cloud (10,000+ objects), we implement a **3D KD-Tree**.
- **Complexity**: $O(N \log N)$ for tree construction and $O(\log N)$ for radius search.
- **Implementation**: The KD-Tree is rebuilt at each simulation tick in C++ to provide real-time conjunction assessment.

### 4. Autonomous Decision Logic
The `AutonomyManager` acts as the "brain," performing multi-stage risk assessment:
1. **Severity Classification**: CRITICAL (< 100m) / WARNING (< 1km).
2. **Strategy Selection**: RTN-frame prograde/retrograde phasing maneuvers (highest fuel efficiency).
3. **Uplink Latency**: All maneuvers are scheduled with a 10-second buffer to account for signal delay.
4. **Thruster Cooldown**: Strictly enforces a 600-second rest period between burns.

### 5. System Architecture
- **Backend**: FastAPI (Python 3.13)
- **Physics Core**: C++ (C++17) + Pybind11
- **API**: Rulebook-compliant (Section 4)
- **Deployment**: Dockerized (Ubuntu 22.04 base)

### 6. Performance Benchmarks
- **Conjunction Assessment**: < 10ms for 50 sats vs 10,000 debris objects.
- **API Latency**: < 50ms average response time.

---
*Created for the IIT Delhi National Space Hackathon 2026.*
