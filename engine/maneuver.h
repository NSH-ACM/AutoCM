#pragma once

#include "propagator.h"
#include "conjunction.h"
#include <string>

// Constants
constexpr double ISP = 300.0;      // seconds
constexpr double G0 = 9.80665 / 1000.0;  // km/s² (converted from m/s²)

struct ManeuverPlan {
    std::string burn_id;
    std::string satellite_id;
    double burn_time_offset_s;     // seconds from now
    Vec3   dv_eci_kms;
    double estimated_fuel_kg;
    bool   is_recovery;
};

// Matrix 3x3 for coordinate transformations
struct Mat3x3 {
    double m[3][3];
    Mat3x3() {
        for (int i = 0; i < 3; i++) {
            for (int j = 0; j < 3; j++) {
                m[i][j] = 0.0;
            }
        }
    }
};

// Function declarations
Mat3x3 eci_to_rtn_matrix(const Vec3& r, const Vec3& v);
Vec3 rtn_to_eci(const Vec3& dv_rtn, const Vec3& r, const Vec3& v);
double fuel_consumed(double dv_ms, double mass_current_kg);
bool apply_burn(OrbitalObject& sat, Vec3 dv_eci_kms);
ManeuverPlan plan_evasion(const OrbitalObject& sat, const CDMWarning& cdm);
ManeuverPlan plan_recovery(const OrbitalObject& sat, const StateVector& nominal_slot, double time_offset_seconds);
bool needs_graveyard(const OrbitalObject& sat);
ManeuverPlan plan_graveyard(const OrbitalObject& sat);
