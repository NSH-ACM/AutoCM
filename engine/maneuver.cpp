#include "maneuver.h"
#include <cmath>
#include <sstream>

// Vector operations
Vec3 cross(const Vec3& a, const Vec3& b) {
    return {
        a.y * b.z - a.z * b.y,
        a.z * b.x - a.x * b.z,
        a.x * b.y - a.y * b.x
    };
}

Vec3 normalize(const Vec3& v) {
    double norm = sqrt(v.x * v.x + v.y * v.y + v.z * v.z);
    if (norm == 0.0) return {0.0, 0.0, 0.0};
    return {v.x / norm, v.y / norm, v.z / norm};
}

Mat3x3 eci_to_rtn_matrix(const Vec3& r, const Vec3& v) {
    Vec3 R_hat = normalize(r);
    Vec3 N_hat = normalize(cross(r, v));
    Vec3 T_hat = cross(N_hat, R_hat);
    
    Mat3x3 rotation;
    rotation.m[0][0] = R_hat.x; rotation.m[0][1] = T_hat.x; rotation.m[0][2] = N_hat.x;
    rotation.m[1][0] = R_hat.y; rotation.m[1][1] = T_hat.y; rotation.m[1][2] = N_hat.y;
    rotation.m[2][0] = R_hat.z; rotation.m[2][1] = T_hat.z; rotation.m[2][2] = N_hat.z;
    
    return rotation;
}

Vec3 rtn_to_eci(const Vec3& dv_rtn, const Vec3& r, const Vec3& v) {
    Mat3x3 rotation = eci_to_rtn_matrix(r, v);
    
    // Transpose the rotation matrix (inverse for rotation matrix)
    Vec3 dv_eci;
    dv_eci.x = rotation.m[0][0] * dv_rtn.x + rotation.m[1][0] * dv_rtn.y + rotation.m[2][0] * dv_rtn.z;
    dv_eci.y = rotation.m[0][1] * dv_rtn.x + rotation.m[1][1] * dv_rtn.y + rotation.m[2][1] * dv_rtn.z;
    dv_eci.z = rotation.m[0][2] * dv_rtn.x + rotation.m[1][2] * dv_rtn.y + rotation.m[2][2] * dv_rtn.z;
    
    return dv_eci;
}

double fuel_consumed(double dv_ms, double mass_current_kg) {
    double dv_kms = dv_ms / 1000.0;  // Convert m/s to km/s
    return mass_current_kg * (1.0 - exp(-dv_ms / (ISP * G0 * 1000.0)));
}

bool apply_burn(OrbitalObject& sat, Vec3 dv_eci_kms) {
    // Check thrust limit (15 m/s = 0.015 km/s)
    double dv_magnitude = sqrt(dv_eci_kms.x * dv_eci_kms.x + 
                              dv_eci_kms.y * dv_eci_kms.y + 
                              dv_eci_kms.z * dv_eci_kms.z);
    
    if (dv_magnitude * 1000.0 > 15.0) {
        return false;  // Exceeds thrust limit
    }
    
    if (sat.mass_fuel <= 0.0) {
        return false;  // No fuel
    }
    
    double total_mass = sat.mass_dry + sat.mass_fuel;
    double dv_ms = dv_magnitude * 1000.0;  // Convert to m/s for fuel calculation
    double delta_m = fuel_consumed(dv_ms, total_mass);
    
    if (sat.mass_fuel - delta_m < 0.0) {
        return false;  // Insufficient fuel
    }
    
    // Apply burn
    sat.state.v.x += dv_eci_kms.x;
    sat.state.v.y += dv_eci_kms.y;
    sat.state.v.z += dv_eci_kms.z;
    sat.mass_fuel -= delta_m;
    
    return true;
}

ManeuverPlan plan_evasion(const OrbitalObject& sat, const CDMWarning& cdm) {
    ManeuverPlan plan;
    plan.satellite_id = sat.id;
    plan.is_recovery = false;
    
    // Generate burn ID
    std::ostringstream oss;
    oss << "EVASION_" << sat.id << "_" << cdm.debris_id;
    plan.burn_id = oss.str();
    
    double t_avail = cdm.tca_seconds_from_now;
    double standoff_km = 1.0;  // Target 1 km standoff (10x threshold)
    
    Vec3 dv_rtn;
    
    if (t_avail < 600.0) {
        // Use Radial burn for fast separation
        dv_rtn.x = (standoff_km * 2.0) / t_avail;
        dv_rtn.y = 0.0;
        dv_rtn.z = 0.0;
    } else {
        // Use Transverse burn (most fuel-efficient)
        dv_rtn.x = 0.0;
        dv_rtn.y = (standoff_km * 2.0) / t_avail;
        dv_rtn.z = 0.0;
    }
    
    // Cap at 10 m/s (0.01 km/s)
    double dv_magnitude = sqrt(dv_rtn.x * dv_rtn.x + dv_rtn.y * dv_rtn.y + dv_rtn.z * dv_rtn.z);
    if (dv_magnitude > 0.01) {
        double scale = 0.01 / dv_magnitude;
        dv_rtn.x *= scale;
        dv_rtn.y *= scale;
        dv_rtn.z *= scale;
    }
    
    // Convert to ECI
    plan.dv_eci_kms = rtn_to_eci(dv_rtn, sat.state.r, sat.state.v);
    
    // Calculate fuel consumption
    double total_mass = sat.mass_dry + sat.mass_fuel;
    double dv_ms = sqrt(plan.dv_eci_kms.x * plan.dv_eci_kms.x + 
                       plan.dv_eci_kms.y * plan.dv_eci_kms.y + 
                       plan.dv_eci_kms.z * plan.dv_eci_kms.z) * 1000.0;
    plan.estimated_fuel_kg = fuel_consumed(dv_ms, total_mass);
    
    // Schedule burn (minimum 10 seconds from now)
    plan.burn_time_offset_s = std::max(10.0, t_avail - 300.0);  // 5 minutes before TCA
    
    return plan;
}

ManeuverPlan plan_recovery(const OrbitalObject& sat, const StateVector& nominal_slot, double time_offset_seconds) {
    ManeuverPlan plan;
    plan.satellite_id = sat.id;
    plan.is_recovery = true;
    
    // Generate burn ID
    std::ostringstream oss;
    oss << "RECOVERY_" << sat.id;
    plan.burn_id = oss.str();
    
    // Calculate position error
    Vec3 delta_r = {
        nominal_slot.r.x - sat.state.r.x,
        nominal_slot.r.y - sat.state.r.y,
        nominal_slot.r.z - sat.state.r.z
    };
    
    double position_error = sqrt(delta_r.x * delta_r.x + delta_r.y * delta_r.y + delta_r.z * delta_r.z);
    
    if (position_error < 10.0) {
        // No recovery needed
        return plan;  // Empty plan
    }
    
    // Compute corrective ∆v in Transverse direction
    double r_norm = sat.state.r.norm();
    double dv_T = -(position_error * MU) / (2.0 * M_PI * r_norm * r_norm);
    
    Vec3 dv_rtn = {0.0, dv_T, 0.0};
    
    // Convert to ECI
    plan.dv_eci_kms = rtn_to_eci(dv_rtn, sat.state.r, sat.state.v);
    
    // Calculate fuel consumption
    double total_mass = sat.mass_dry + sat.mass_fuel;
    double dv_ms = sqrt(plan.dv_eci_kms.x * plan.dv_eci_kms.x + 
                       plan.dv_eci_kms.y * plan.dv_eci_kms.y + 
                       plan.dv_eci_kms.z * plan.dv_eci_kms.z) * 1000.0;
    plan.estimated_fuel_kg = fuel_consumed(dv_ms, total_mass);
    
    // Enforce 600 s cooldown from evasion burn
    plan.burn_time_offset_s = time_offset_seconds + 600.0;
    
    return plan;
}

bool needs_graveyard(const OrbitalObject& sat) {
    return (sat.mass_fuel / 50.0) < 0.05;  // Below 5% of initial fuel
}

ManeuverPlan plan_graveyard(const OrbitalObject& sat) {
    ManeuverPlan plan;
    plan.satellite_id = sat.id;
    plan.is_recovery = false;
    plan.burn_id = "GRAVEYARD_BURN";
    
    // Raise orbit by ~25 km for LEO graveyard
    double r_norm = sat.state.r.norm();
    double delta_a = 25.0;  // km
    
    // Hohmann transfer apoapsis raise
    double dv_T = sqrt(MU / r_norm) * (sqrt(2.0 * (r_norm + delta_a) / (2.0 * r_norm + delta_a)) - 1.0);
    
    Vec3 dv_rtn = {0.0, dv_T, 0.0};
    
    // Convert to ECI
    plan.dv_eci_kms = rtn_to_eci(dv_rtn, sat.state.r, sat.state.v);
    
    // Calculate fuel consumption
    double total_mass = sat.mass_dry + sat.mass_fuel;
    double dv_ms = sqrt(plan.dv_eci_kms.x * plan.dv_eci_kms.x + 
                       plan.dv_eci_kms.y * plan.dv_eci_kms.y + 
                       plan.dv_eci_kms.z * plan.dv_eci_kms.z) * 1000.0;
    plan.estimated_fuel_kg = fuel_consumed(dv_ms, total_mass);
    
    plan.burn_time_offset_s = 0.0;  // Execute immediately
    
    return plan;
}
