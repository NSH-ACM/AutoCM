#pragma once

#include "propagator.h"
#include <string>

struct ManeuverPlan {
    std::string burn_id;
    std::string satellite_id;
    double burn_time_offset_s;     // seconds from now
    Vec3   dv_eci_kms;
    double estimated_fuel_kg;
    bool   is_recovery;
};
