/**
 * ═══════════════════════════════════════════════════════════════════════════
 *  ACM PHYSICS ENGINE — propagator.cpp
 *  RK4 Integrator with J2 perturbation (+ atmospheric drag stub).
 *  National Space Hackathon 2026
 *
 *  Functions:
 *    accel_j2(r)             — J2-perturbed Keplerian acceleration
 *    accel_drag(r, v, bstar) — Atmospheric drag (stub, returns zero)
 *    accel_total(r, v, bstar)— Combined force model
 *    rk4_step(r, v, dt)      — Single RK4 step
 *    propagate(objects, dt)   — Batch propagation with adaptive sub-stepping
 *
 *  Units: km, km/s, seconds (ECI J2000 frame)
 *  OpenMP: objects propagated in parallel if compiled with -fopenmp
 *
 *  Reference: Bate, Mueller & Saylor, "Fundamentals of Astrodynamics"
 * ═══════════════════════════════════════════════════════════════════════════
 */

#include "common.h"

#ifdef _OPENMP
#include <omp.h>
#endif

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

// ═══════════════════════════════════════════════════════════════════════════
//  FORCE MODELS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * J2-perturbed ECI acceleration.
 * Includes both Keplerian two-body and J2 zonal harmonic terms.
 */
Vec3 accel_j2(const Vec3& r) {
    const double r2  = r.norm2();
    const double r1  = std::sqrt(r2);
    const double r3  = r2 * r1;
    const double r5  = r3 * r2;

    // Keplerian: a = -μ/r³ · r
    const Vec3 a_kep = r * (-MU / r3);

    // J2 perturbation
    const double f   = 1.5 * J2 * MU * RE2 / r5;
    const double zr2 = (r.z / r1) * (r.z / r1);
    const Vec3 a_j2 = {
        f * r.x * (1.0 - 5.0 * zr2),
        f * r.y * (1.0 - 5.0 * zr2),
        f * r.z * (3.0 - 5.0 * zr2)
    };

    return a_kep + a_j2;
}

/**
 * Atmospheric drag acceleration stub.
 * Returns zero until bstar (ballistic coefficient) is wired through.
 *
 * To activate:
 *   1. Add a `bstar` field to the object dict
 *   2. Uncomment the implementation below
 *
 * Model: exponential atmosphere, Harris-Priester approximation.
 */
Vec3 accel_drag(const Vec3& r, const Vec3& v, double bstar) {
    // Uncomment once bstar is wired through:
    //
    // double alt_km   = r.norm() - RE;
    // double rho      = RHO0_KG_KM3 * std::exp(-alt_km / H_SCALE_KM);
    // double v_mag    = v.norm();
    // double drag_acc = -rho * bstar * v_mag;
    // return v.normalized() * drag_acc;

    (void)r; (void)v; (void)bstar;
    return {};
}

/** Total acceleration: J2 + drag (drag is zero until bstar is provided). */
Vec3 accel_total(const Vec3& r, const Vec3& v, double bstar = 0.0) {
    return accel_j2(r) + accel_drag(r, v, bstar);
}

// ═══════════════════════════════════════════════════════════════════════════
//  RK4 INTEGRATOR
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Single RK4 step: (r, v) → (r_new, v_new) over dt seconds.
 * Classic 4th-order Runge-Kutta for the 2nd-order ODE of motion.
 */
std::pair<Vec3, Vec3> rk4_step(Vec3 r, Vec3 v, double dt, double bstar) {
    const double h2 = dt * 0.5;
    const double h6 = dt / 6.0;

    Vec3 k1r = v,                k1v = accel_total(r, v, bstar);
    Vec3 k2r = v + k1v * h2,     k2v = accel_total(r + k1r*h2, k2r, bstar);
    Vec3 k3r = v + k2v * h2,     k3v = accel_total(r + k2r*h2, k3r, bstar);
    Vec3 k4r = v + k3v * dt,     k4v = accel_total(r + k3r*dt,  k4r, bstar);

    return {
        r + rk4_combine(k1r, k2r, k3r, k4r, h6),
        v + rk4_combine(k1v, k2v, k3v, k4v, h6)
    };
}

/**
 * propagate(objects, dt) -> list[dict]
 *
 * Each object: {id, r:{x,y,z}, v:{x,y,z} [, bstar]}
 * Adaptive sub-stepping: max 60 s per RK4 step.
 * OpenMP: parallel propagation across objects.
 */
py::list propagate(py::list objects, double dt) {
    if (!std::isfinite(dt))
        throw std::invalid_argument("propagate: dt must be finite");
    if (std::abs(dt) > 86400.0 * 30)
        throw std::invalid_argument("propagate: |dt| > 30 days, likely a unit error");

    auto t0 = std::chrono::high_resolution_clock::now();
    telemetry::propagate_calls.fetch_add(1, std::memory_order_relaxed);

    const double MAX_SUBSTEP = 60.0;
    const int    n_steps     = std::max(1, (int)std::ceil(std::abs(dt) / MAX_SUBSTEP));
    const double sub_dt      = dt / n_steps;

    // Pre-parse into C++ structs for OpenMP safety
    struct ObjIn { std::string id; Vec3 r, v; double bstar; };
    std::vector<ObjIn> in_vec;
    in_vec.reserve(py::len(objects));

    for (auto item : objects) {
        py::dict obj = item.cast<py::dict>();
        if (!obj.contains("r") || !obj.contains("v") || !obj.contains("id"))
            throw std::invalid_argument("propagate: each object needs 'id', 'r', 'v'");
        py::dict r_d = obj["r"].cast<py::dict>();
        py::dict v_d = obj["v"].cast<py::dict>();
        Vec3 r = { r_d["x"].cast<double>(), r_d["y"].cast<double>(), r_d["z"].cast<double>() };
        Vec3 v = { v_d["x"].cast<double>(), v_d["y"].cast<double>(), v_d["z"].cast<double>() };
        if (!std::isfinite(r.norm2()) || !std::isfinite(v.norm2()))
            throw std::invalid_argument("propagate: non-finite position/velocity in input");
        double bstar = obj.contains("bstar") ? obj["bstar"].cast<double>() : 0.0;
        in_vec.push_back({obj["id"].cast<std::string>(), r, v, bstar});
    }

    struct ObjOut { std::string id; Vec3 r, v; };
    std::vector<ObjOut> out_vec(in_vec.size());

    // --- Parallel propagation ---
#ifdef _OPENMP
    #pragma omp parallel for schedule(dynamic, 8)
#endif
    for (int i = 0; i < (int)in_vec.size(); ++i) {
        Vec3 r = in_vec[i].r, v = in_vec[i].v;
        double bstar = in_vec[i].bstar;
        for (int s = 0; s < n_steps; ++s)
            std::tie(r, v) = rk4_step(r, v, sub_dt, bstar);
        out_vec[i] = { in_vec[i].id, r, v };
    }

    // Build Python result
    py::list result;
    for (const auto& o : out_vec) {
        py::dict out;
        out["id"] = o.id;
        out["r"]  = py::dict(py::arg("x")=o.r.x, py::arg("y")=o.r.y, py::arg("z")=o.r.z);
        out["v"]  = py::dict(py::arg("x")=o.v.x, py::arg("y")=o.v.y, py::arg("z")=o.v.z);
        result.append(out);
    }

    double ms = std::chrono::duration<double, std::milli>(
        std::chrono::high_resolution_clock::now() - t0).count();
    {
        std::lock_guard<std::mutex> lock(telemetry::prop_ms_mutex);
        telemetry::propagate_ms_total += ms;
    }
    return result;
}
