#pragma once

#include <string>
#include <vector>

// Physics constants
constexpr double MU = 398600.4418;    // km³/s²
constexpr double RE = 6378.137;       // km
constexpr double J2 = 1.08263e-3;

struct Vec3 {
    double x, y, z;
    Vec3 operator+(const Vec3&) const;
    Vec3 operator*(double) const;
    double norm() const;
};

struct StateVector {
    double t;        // epoch in seconds since J2000
    Vec3 r;          // position in km
    Vec3 v;          // velocity in km/s
};

struct OrbitalObject {
    std::string id;
    std::string type;   // "SATELLITE" or "DEBRIS"
    StateVector state;
    double mass_dry;    // kg  (500.0 for sats, 0 for debris)
    double mass_fuel;   // kg  (50.0 for sats, 0 for debris)
    bool controllable;
};

// Function declarations
Vec3 j2_acceleration(const Vec3& r);
Vec3 total_acceleration(const Vec3& r);
StateVector rk4_step(const StateVector& s, double dt);
StateVector propagate(const StateVector& s0, double dt_total, double dt_step = 1.0);
