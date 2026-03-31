/**
 * ═══════════════════════════════════════════════════════════════════════════
 *  ACM PHYSICS ENGINE — maneuver.cpp
 *  RTN-frame burn logic and Hohmann recovery.
 *  National Space Hackathon 2026
 *
 *  Functions:
 *    plan_evasion(satellite, debris, tca_s, burn_time_offset_s)
 *      → {deltaV_ECI, dvMagnitude_ms, fuelCostKg, strategy}
 *
 *    plan_recovery(evasion_dv, satellite_mass)
 *      → {deltaV_ECI, dvMagnitude_ms, fuelCostKg}
 *
 *    compute_fuel_consumed(mass_kg, dv_ms)
 *      → propellant mass consumed (Tsiolkovsky)
 *
 *  Burn strategy preference order:
 *    Prograde → Retrograde → Radial Out → Radial In → Normal ±
 *    (cheapest first, plane changes as last resort)
 *
 *  Units: km, km/s, seconds (ECI J2000 frame)
 * ═══════════════════════════════════════════════════════════════════════════
 */

#include "common.h"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

// ═══════════════════════════════════════════════════════════════════════════
//  TSIOLKOVSKY ROCKET EQUATION
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Propellant mass consumed for an impulsive burn.
 * Δm = m_current × (1 − e^(−|Δv| / (Isp × g0)))
 */
double compute_fuel_consumed(double current_mass_kg, double dv_ms) {
    return current_mass_kg * (1.0 - std::exp(-std::abs(dv_ms) / (ISP_S * G0_MS2)));
}

// ═══════════════════════════════════════════════════════════════════════════
//  MISS DISTANCE ESTIMATION (Linear TCA — O(1))
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Estimate the closest approach distance between sat and debris
 * using a linear relative-motion model:
 *   t_ca = -(Δr · Δv) / |Δv|²
 *   miss = |Δr + Δv · max(0, t_ca)|
 */
static double estimate_miss_distance(const Vec3& sat_r, const Vec3& sat_v,
                                      const Vec3& deb_r, const Vec3& deb_v) {
    Vec3 dr = sat_r - deb_r;
    Vec3 dv = sat_v - deb_v;
    double relSpeed2 = dv.dot(dv);

    if (relSpeed2 < 1e-18) return dr.norm();  // Parallel trajectories

    double tca = -dr.dot(dv) / relSpeed2;
    Vec3 miss_vec = dr + dv * std::max(0.0, tca);
    return miss_vec.norm();
}

/**
 * Estimate miss distance after applying a ΔV to the satellite.
 */
static double estimate_miss_with_dv(const Vec3& sat_r, const Vec3& sat_v,
                                     const Vec3& deb_r, const Vec3& deb_v,
                                     const Vec3& dv_eci) {
    Vec3 new_v = sat_v + dv_eci;
    return estimate_miss_distance(sat_r, new_v, deb_r, deb_v);
}

// ═══════════════════════════════════════════════════════════════════════════
//  EVASION BURN PLANNING
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Try a single burn strategy (direction + sign) at increasing ΔV magnitudes.
 * Returns a Python dict with burn params if successful, None otherwise.
 */
static py::object try_strategy(const Vec3& sat_r, const Vec3& sat_v,
                                const Vec3& deb_r, const Vec3& deb_v,
                                const Vec3& dir, double sign,
                                const std::string& name,
                                double mass_kg, double fuel_kg) {
    const double SAFETY_MARGIN_KM = 0.2;    // Target 200m miss (2× safety)
    const double MIN_DV_KMS       = 0.010;  // 10 m/s
    const double DV_STEP_KMS      = 0.002;  // 2 m/s step
    const double MAX_DV_KMS       = MAX_DV_MS / 1000.0;  // 15 m/s cap

    double dvMag = MIN_DV_KMS;

    while (dvMag <= MAX_DV_KMS) {
        Vec3 dv_eci = dir * (sign * dvMag);
        double new_miss = estimate_miss_with_dv(sat_r, sat_v, deb_r, deb_v, dv_eci);

        if (new_miss >= SAFETY_MARGIN_KM) {
            double dv_ms = dvMag * 1000.0;
            double fuel_cost = compute_fuel_consumed(mass_kg, dv_ms);

            if (fuel_cost > fuel_kg) return py::none();

            py::dict result;
            result["deltaV_ECI"] = py::dict(
                py::arg("x")=dv_eci.x,
                py::arg("y")=dv_eci.y,
                py::arg("z")=dv_eci.z
            );
            result["dvMagnitude_ms"] = dv_ms;
            result["fuelCostKg"]     = fuel_cost;
            result["strategy"]       = name;
            result["newMissKm"]      = new_miss;
            return result;
        }

        dvMag += DV_STEP_KMS;
    }
    return py::none();
}

/**
 * plan_evasion(satellite, debris) -> dict | None
 *
 * Calculates minimum-ΔV evasion burn in RTN frame, converted to ECI.
 * Tries strategies in order of fuel efficiency:
 *   Prograde → Retrograde → Radial Out → Radial In → Normal ±
 *
 * satellite: {id, r:{x,y,z}, v:{x,y,z}, fuelKg, currentMass}
 * debris:    {id, r:{x,y,z}, v:{x,y,z}}
 */
py::object plan_evasion(py::dict satellite, py::dict debris_obj) {
    telemetry::maneuver_calls.fetch_add(1, std::memory_order_relaxed);

    // Parse satellite state
    py::dict sr = satellite["r"].cast<py::dict>();
    py::dict sv = satellite["v"].cast<py::dict>();
    Vec3 sat_r = { sr["x"].cast<double>(), sr["y"].cast<double>(), sr["z"].cast<double>() };
    Vec3 sat_v = { sv["x"].cast<double>(), sv["y"].cast<double>(), sv["z"].cast<double>() };
    double fuel_kg = satellite.contains("fuelKg") ? satellite["fuelKg"].cast<double>() : 50.0;
    double mass_kg = satellite.contains("currentMass") ? satellite["currentMass"].cast<double>() : 500.0;

    // Parse debris state
    py::dict dr = debris_obj["r"].cast<py::dict>();
    py::dict dv = debris_obj["v"].cast<py::dict>();
    Vec3 deb_r = { dr["x"].cast<double>(), dr["y"].cast<double>(), dr["z"].cast<double>() };
    Vec3 deb_v = { dv["x"].cast<double>(), dv["y"].cast<double>(), dv["z"].cast<double>() };

    // Compute RTN frame
    RTNFrame rtn = computeRTN(sat_r, sat_v);

    // Try strategies in order of efficiency
    struct Strategy { std::string name; Vec3 dir; double sign; };
    std::vector<Strategy> strategies = {
        {"PROGRADE",   rtn.T_hat,  +1.0},
        {"RETROGRADE", rtn.T_hat,  -1.0},
        {"RADIAL_OUT", rtn.R_hat,  +1.0},
        {"RADIAL_IN",  rtn.R_hat,  -1.0},
        {"NORMAL_POS", rtn.N_hat,  +1.0},
        {"NORMAL_NEG", rtn.N_hat,  -1.0},
    };

    for (const auto& strat : strategies) {
        py::object result = try_strategy(
            sat_r, sat_v, deb_r, deb_v,
            strat.dir, strat.sign, strat.name,
            mass_kg, fuel_kg
        );
        if (!result.is_none()) return result;
    }

    return py::none();
}

// ═══════════════════════════════════════════════════════════════════════════
//  RECOVERY BURN (HOHMANN-STYLE REVERSAL)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * plan_recovery(evasion_dv_eci, satellite_mass_kg) -> dict
 *
 * Plans the return burn to re-enter the nominal orbital slot.
 * Recovery ΔV ≈ −0.95 × evasion ΔV (accounts for orbital drift).
 * A perfect reversal would overshoot due to changed orbital elements.
 */
py::dict plan_recovery(py::dict evasion_dv_eci, double satellite_mass_kg) {
    const double RECOVERY_SCALE = 0.95;

    double ex = evasion_dv_eci["x"].cast<double>();
    double ey = evasion_dv_eci["y"].cast<double>();
    double ez = evasion_dv_eci["z"].cast<double>();

    Vec3 recovery_dv = { -ex * RECOVERY_SCALE, -ey * RECOVERY_SCALE, -ez * RECOVERY_SCALE };
    double dv_kms = recovery_dv.norm();
    double dv_ms  = dv_kms * 1000.0;
    double fuel_cost = compute_fuel_consumed(satellite_mass_kg, dv_ms);

    py::dict result;
    result["deltaV_ECI"] = py::dict(
        py::arg("x")=recovery_dv.x,
        py::arg("y")=recovery_dv.y,
        py::arg("z")=recovery_dv.z
    );
    result["dvMagnitude_ms"] = dv_ms;
    result["fuelCostKg"]     = fuel_cost;
    result["strategy"]       = "RECOVERY_REVERSAL";
    return result;
}

/**
 * plan_deorbit(satellite) -> dict
 *
 * EOL handler: plans a retrograde deorbit burn to lower perigee.
 * Uses remaining fuel (partial burn if insufficient for full 10 m/s).
 */
py::object plan_deorbit(py::dict satellite) {
    py::dict sr = satellite["r"].cast<py::dict>();
    py::dict sv = satellite["v"].cast<py::dict>();
    Vec3 sat_r = { sr["x"].cast<double>(), sr["y"].cast<double>(), sr["z"].cast<double>() };
    Vec3 sat_v = { sv["x"].cast<double>(), sv["y"].cast<double>(), sv["z"].cast<double>() };
    double fuel_kg = satellite.contains("fuelKg") ? satellite["fuelKg"].cast<double>() : 0.0;
    double mass_kg = satellite.contains("currentMass") ? satellite["currentMass"].cast<double>() : 500.0;

    RTNFrame rtn = computeRTN(sat_r, sat_v);

    double target_dv_ms = 10.0;  // 10 m/s retrograde
    double fuel_needed = compute_fuel_consumed(mass_kg, target_dv_ms);

    // If not enough fuel, binary search for max achievable ΔV
    if (fuel_needed > fuel_kg) {
        double lo = 0.0, hi = target_dv_ms;
        for (int i = 0; i < 20; ++i) {
            double mid = (lo + hi) / 2.0;
            if (compute_fuel_consumed(mass_kg, mid) <= fuel_kg) lo = mid;
            else hi = mid;
        }
        target_dv_ms = lo;
        if (target_dv_ms < 0.5) return py::none();  // Not worth burning
    }

    double dv_kms = target_dv_ms / 1000.0;
    Vec3 dv_eci = rtn.T_hat * (-dv_kms);  // Negative T = retrograde

    py::dict result;
    result["deltaV_ECI"] = py::dict(
        py::arg("x")=dv_eci.x,
        py::arg("y")=dv_eci.y,
        py::arg("z")=dv_eci.z
    );
    result["dvMagnitude_ms"] = target_dv_ms;
    result["fuelCostKg"]     = compute_fuel_consumed(mass_kg, target_dv_ms);
    result["strategy"]       = "DEORBIT_RETROGRADE";
    return result;
}
