#pragma once

#include <string>
#include <vector>

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
