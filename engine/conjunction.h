#pragma once

#include "propagator.h"
#include <vector>
#include <memory>
#include <string>

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

struct KDNode {
    Vec3 point;
    std::string id;
    int axis;
    Vec3 bbox_min;  // Bounding box for spatial pruning
    Vec3 bbox_max;
    std::shared_ptr<KDNode> left;
    std::shared_ptr<KDNode> right;
    
    KDNode(const Vec3& p, const std::string& i, int a) 
        : point(p), id(i), axis(a), 
          bbox_min(p), bbox_max(p),  // Initialize bbox to point
          left(nullptr), right(nullptr) {}
};

class KDTree {
private:
    std::shared_ptr<KDNode> root;
    
    std::shared_ptr<KDNode> buildTree(std::vector<std::pair<Vec3, std::string>>& points, 
                                     int start, int end, int axis);
    
    void radiusSearch(const std::shared_ptr<KDNode>& node, 
                     const Vec3& center, double radius, 
                     std::vector<ConjunctionCandidate>& results);
    
    double distance(const Vec3& a, const Vec3& b) const;
    
public:
    void build(const std::vector<std::pair<Vec3, std::string>>& points);
    std::vector<ConjunctionCandidate> query_radius(const Vec3& center, double radius_km);
};

// Function declarations
std::vector<CDMWarning> run_conjunction_assessment(
    const std::vector<OrbitalObject>& satellites,
    const std::vector<OrbitalObject>& debris,
    double lookahead_seconds = 86400.0,
    double dt_step = 30.0);
