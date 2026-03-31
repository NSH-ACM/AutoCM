#pragma once

#include "propagator.h"
#include <vector>

struct CDMWarning {
    std::string satellite_id;
    std::string debris_id;
    double tca_seconds_from_now;
    double miss_distance_km;
    Vec3   relative_velocity;   // km/s at TCA
};

struct ConjunctionCandidate {
    std::string debris_id;
    double distance_km;
    double tca_seconds;   // time to closest approach (to be filled by caller)
};

class KDTree {
    // Implementation placeholder
};
