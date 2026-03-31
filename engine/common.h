/**
 * ═══════════════════════════════════════════════════════════════════════════
 *  ACM PHYSICS ENGINE — common.h
 *  Shared types, constants, and vector mathematics.
 *  National Space Hackathon 2026
 * ═══════════════════════════════════════════════════════════════════════════
 */

#pragma once

#include <cmath>
#include <string>
#include <vector>
#include <array>
#include <tuple>
#include <stdexcept>
#include <algorithm>
#include <atomic>
#include <mutex>
#include <chrono>
#include <sstream>
#include <unordered_map>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

// ─── Physical Constants ─────────────────────────────────────────────────────
static constexpr double MU       = 398600.4418;   // km³/s²  Earth std grav param
static constexpr double RE       = 6378.137;       // km      Earth equatorial radius
static constexpr double J2       = 1.0826257e-3;   // J2 zonal harmonic
static constexpr double RE2      = RE * RE;
static constexpr double DEG2RAD  = M_PI / 180.0;
static constexpr double RAD2DEG  = 180.0 / M_PI;

// Drag: standard exponential atmosphere at ~300-500 km
static constexpr double RHO0_KG_KM3 = 1.225e9;    // sea-level density, kg/km³
static constexpr double H_SCALE_KM  = 8.5;         // scale height, km

// Thruster / mission constants
static constexpr double ISP_S        = 300.0;      // Specific impulse (s)
static constexpr double G0_MS2       = 9.80665;    // Standard gravity (m/s²)
static constexpr double MAX_DV_MS    = 15.0;       // Max ΔV per burn (m/s)
static constexpr double COOLDOWN_S   = 600.0;      // Thruster rest period (s)
static constexpr double SIGNAL_LAT_S = 10.0;       // Ground uplink latency (s)

// ═══════════════════════════════════════════════════════════════════════════
//  Vec3 — Compact 3D vector with inline operators
// ═══════════════════════════════════════════════════════════════════════════

struct Vec3 {
    double x = 0, y = 0, z = 0;

    Vec3() = default;
    Vec3(double x_, double y_, double z_) : x(x_), y(y_), z(z_) {}

    Vec3 operator+(const Vec3& o) const { return {x+o.x, y+o.y, z+o.z}; }
    Vec3 operator-(const Vec3& o) const { return {x-o.x, y-o.y, z-o.z}; }
    Vec3 operator*(double s)      const { return {x*s,   y*s,   z*s  }; }
    Vec3& operator+=(const Vec3& o) { x+=o.x; y+=o.y; z+=o.z; return *this; }
    Vec3& operator-=(const Vec3& o) { x-=o.x; y-=o.y; z-=o.z; return *this; }
    Vec3& operator*=(double s)      { x*=s;   y*=s;   z*=s;   return *this; }

    double dot(const Vec3& o)  const { return x*o.x + y*o.y + z*o.z; }
    double norm2()             const { return x*x + y*y + z*z; }
    double norm()              const { return std::sqrt(norm2()); }

    Vec3 cross(const Vec3& o) const {
        return {y*o.z - z*o.y, z*o.x - x*o.z, x*o.y - y*o.x};
    }
    Vec3 normalized() const {
        double n = norm();
        return (n < 1e-15) ? Vec3{} : Vec3{x/n, y/n, z/n};
    }
};

inline Vec3 rk4_combine(const Vec3& a, const Vec3& b, const Vec3& c,
                         const Vec3& d, double scale) {
    return (a + b * 2.0 + c * 2.0 + d) * scale;
}

// ═══════════════════════════════════════════════════════════════════════════
//  ObjState — Orbital object state carrier
// ═══════════════════════════════════════════════════════════════════════════

struct ObjState {
    std::string id;
    Vec3 r, v;
    double bstar = 0.0;    // Ballistic coefficient (drag), 0 = inactive
    double fuelKg = 50.0;  // Remaining propellant mass (kg)
    double massKg = 500.0; // Total current mass (kg)
};

// ═══════════════════════════════════════════════════════════════════════════
//  RTN Frame — Radial-Transverse-Normal coordinate system
// ═══════════════════════════════════════════════════════════════════════════

struct RTNFrame {
    Vec3 R_hat;  // Radial (outward)
    Vec3 T_hat;  // Transverse (along-track / prograde)
    Vec3 N_hat;  // Normal (orbit normal)
};

inline RTNFrame computeRTN(const Vec3& r_eci, const Vec3& v_eci) {
    Vec3 R = r_eci.normalized();
    Vec3 N = r_eci.cross(v_eci).normalized();
    Vec3 T = N.cross(R);
    return {R, T, N};
}

// ─── Telemetry (shared across modules) ───────────────────────────────────
namespace telemetry {
    inline std::atomic<uint64_t> propagate_calls{0};
    inline std::atomic<uint64_t> conjunction_calls{0};
    inline std::atomic<uint64_t> maneuver_calls{0};
    inline std::mutex            prop_ms_mutex;
    inline double                propagate_ms_total = 0.0;
}
