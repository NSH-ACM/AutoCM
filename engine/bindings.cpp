/**
 * ═══════════════════════════════════════════════════════════════════════════
 *  ACM PHYSICS ENGINE — bindings.cpp
 *  Pybind11 wrapper to expose C++ engine to Python.
 *  National Space Hackathon 2026
 *
 *  This module collects all functions from propagator.cpp, conjunction.cpp,
 *  and maneuver.cpp into a single Python-importable extension module:
 *
 *    import acm_engine
 *
 *    acm_engine.propagate(objects, dt)
 *    acm_engine.detect_conjunctions(sats, debris, lookahead_s, epoch_iso)
 *    acm_engine.plan_evasion(satellite, debris)
 *    acm_engine.plan_recovery(evasion_dv, mass)
 *    acm_engine.plan_deorbit(satellite)
 *    acm_engine.compute_fuel_consumed(mass, dv)
 *    acm_engine.get_engine_stats()
 * ═══════════════════════════════════════════════════════════════════════════
 */

#include "common.h"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

// Forward declarations from other modules
extern py::list propagate(py::list objects, double dt);
extern py::list detect_conjunctions(py::list satellites, py::list debris,
                                     double lookahead_seconds,
                                     const std::string& epoch_iso);
extern py::object plan_evasion(py::dict satellite, py::dict debris_obj);
extern py::dict plan_recovery(py::dict evasion_dv_eci, double satellite_mass_kg);
extern py::object plan_deorbit(py::dict satellite);
extern double compute_fuel_consumed(double current_mass_kg, double dv_ms);

// ═══════════════════════════════════════════════════════════════════════════
//  ENGINE TELEMETRY
// ═══════════════════════════════════════════════════════════════════════════

py::dict get_engine_stats() {
    uint64_t pc = telemetry::propagate_calls.load(std::memory_order_relaxed);
    uint64_t cc = telemetry::conjunction_calls.load(std::memory_order_relaxed);
    uint64_t mc = telemetry::maneuver_calls.load(std::memory_order_relaxed);
    double   ms;
    {
        std::lock_guard<std::mutex> lock(telemetry::prop_ms_mutex);
        ms = telemetry::propagate_ms_total;
    }
    py::dict d;
    d["propagate_calls"]   = pc;
    d["conjunction_calls"] = cc;
    d["maneuver_calls"]    = mc;
    d["total_prop_ms"]     = ms;
    d["avg_prop_ms"]       = (pc > 0) ? (ms / pc) : 0.0;
    d["engine"]            = "acm_engine_cpp_v4";
#ifdef _OPENMP
    d["openmp"]            = true;
#else
    d["openmp"]            = false;
#endif
    return d;
}

// ═══════════════════════════════════════════════════════════════════════════
//  PYBIND11 MODULE DEFINITION
// ═══════════════════════════════════════════════════════════════════════════

PYBIND11_MODULE(acm_engine, m) {
    m.doc() = "ACM Physics Engine v4 — RK4+J2, conjunction screening, RTN maneuvers";

    // ── Propagation ──────────────────────────────────────────────────────
    m.def("propagate",
          &propagate,
          py::arg("objects"), py::arg("dt"),
          R"doc(
RK4 + J2 orbital propagation (+ atmospheric drag stub).
  objects : list of {id, r:{x,y,z}, v:{x,y,z} [, bstar]}  (km, km/s ECI)
  dt      : seconds (positive = forward, negative = backward)
Returns updated list with same schema.
)doc");

    // ── Conjunction Detection ────────────────────────────────────────────
    m.def("detect_conjunctions",
          &detect_conjunctions,
          py::arg("satellites"), py::arg("debris"),
          py::arg("lookahead_seconds"),
          py::arg("epoch_iso") = "",
          R"doc(
Axis-sweep conjunction screening with parabolic TCA.
  epoch_iso : optional ISO 8601 UTC string of t=0
Returns CDM list: [{satelliteId, debrisId, missDistance, probability, tca}]
Only reports miss_distance < 5 km. One entry per (sat, debris) pair.
)doc");

    // ── Maneuver Planning ────────────────────────────────────────────────
    m.def("plan_evasion",
          &plan_evasion,
          py::arg("satellite"), py::arg("debris"),
          R"doc(
Plan minimum-ΔV evasion burn in RTN frame.
  satellite : {r:{x,y,z}, v:{x,y,z}, fuelKg, currentMass}
  debris    : {r:{x,y,z}, v:{x,y,z}}
Returns {deltaV_ECI, dvMagnitude_ms, fuelCostKg, strategy} or None.
Tries: Prograde → Retrograde → Radial → Normal (cheapest first).
)doc");

    m.def("plan_recovery",
          &plan_recovery,
          py::arg("evasion_dv_eci"), py::arg("satellite_mass_kg"),
          R"doc(
Plan recovery burn (Hohmann-style reversal).
Recovery ΔV ≈ -0.95 × evasion ΔV (accounts for orbital drift).
Returns {deltaV_ECI, dvMagnitude_ms, fuelCostKg}.
)doc");

    m.def("plan_deorbit",
          &plan_deorbit,
          py::arg("satellite"),
          R"doc(
EOL deorbit: retrograde burn to lower perigee into drag regime.
Uses remaining fuel (partial burn if insufficient for 10 m/s).
Returns {deltaV_ECI, dvMagnitude_ms, fuelCostKg} or None.
)doc");

    // ── Utility ──────────────────────────────────────────────────────────
    m.def("compute_fuel_consumed",
          &compute_fuel_consumed,
          py::arg("current_mass_kg"), py::arg("dv_ms"),
          "Tsiolkovsky rocket equation: propellant consumed for a given ΔV.");

    m.def("get_engine_stats",
          &get_engine_stats,
          "Returns engine telemetry: call counts, timing, OpenMP status.");
}
