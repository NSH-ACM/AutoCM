#include "conjunction.h"
#include <algorithm>
#include <cmath>
#include <queue>
#include <unordered_map>

// Optimized distance calculation using squared distance to avoid sqrt
static inline double distance_squared(const Vec3& a, const Vec3& b) {
    double dx = a.x - b.x;
    double dy = a.y - b.y;
    double dz = a.z - b.z;
    return dx*dx + dy*dy + dz*dz;
}

double KDTree::distance(const Vec3& a, const Vec3& b) const {
    return sqrt(distance_squared(a, b));
}

std::shared_ptr<KDNode> KDTree::buildTree(std::vector<std::pair<Vec3, std::string>>& points,
                                         int start, int end, int axis) {
    if (start >= end) {
        return nullptr;
    }
    
    int mid = (start + end) / 2;
    
    // Sort points based on current axis using nth_element for O(N) median finding
    auto compare = [axis](const std::pair<Vec3, std::string>& a, 
                          const std::pair<Vec3, std::string>& b) {
        if (axis == 0) return a.first.x < b.first.x;
        if (axis == 1) return a.first.y < b.first.y;
        return a.first.z < b.first.z;
    };
    
    std::nth_element(points.begin() + start, points.begin() + mid, points.begin() + end, compare);
    
    auto node = std::make_shared<KDNode>(points[mid].first, points[mid].second, axis);
    
    // Precompute bounding box for pruning
    for (int i = start; i < end; ++i) {
        node->bbox_min.x = std::min(node->bbox_min.x, points[i].first.x);
        node->bbox_min.y = std::min(node->bbox_min.y, points[i].first.y);
        node->bbox_min.z = std::min(node->bbox_min.z, points[i].first.z);
        node->bbox_max.x = std::max(node->bbox_max.x, points[i].first.x);
        node->bbox_max.y = std::max(node->bbox_max.y, points[i].first.y);
        node->bbox_max.z = std::max(node->bbox_max.z, points[i].first.z);
    }
    
    int next_axis = (axis + 1) % 3;
    node->left = buildTree(points, start, mid, next_axis);
    node->right = buildTree(points, mid + 1, end, next_axis);
    
    return node;
}

void KDTree::build(const std::vector<std::pair<Vec3, std::string>>& points) {
    if (points.empty()) {
        root = nullptr;
        return;
    }
    
    std::vector<std::pair<Vec3, std::string>> mutable_points = points;
    root = buildTree(mutable_points, 0, mutable_points.size(), 0);
}

// Fast bounding box check for early pruning
static inline bool bbox_intersects(const KDNode* node, const Vec3& center, double radius_sq) {
    double dx = 0, dy = 0, dz = 0;
    
    if (center.x < node->bbox_min.x) dx = center.x - node->bbox_min.x;
    else if (center.x > node->bbox_max.x) dx = center.x - node->bbox_max.x;
    
    if (center.y < node->bbox_min.y) dy = center.y - node->bbox_min.y;
    else if (center.y > node->bbox_max.y) dy = center.y - node->bbox_max.y;
    
    if (center.z < node->bbox_min.z) dz = center.z - node->bbox_min.z;
    else if (center.z > node->bbox_max.z) dz = center.z - node->bbox_max.z;
    
    return (dx*dx + dy*dy + dz*dz) <= radius_sq;
}

void KDTree::radiusSearch(const std::shared_ptr<KDNode>& node,
                         const Vec3& center, double radius,
                         std::vector<ConjunctionCandidate>& results) {
    if (!node) return;
    
    double radius_sq = radius * radius;
    
    // Early pruning using bounding box
    if (!bbox_intersects(node.get(), center, radius_sq)) {
        return;
    }
    
    // Check if current node is within radius
    double dist_sq = distance_squared(node->point, center);
    if (dist_sq <= radius_sq) {
        ConjunctionCandidate candidate;
        candidate.debris_id = node->id;
        candidate.distance_km = sqrt(dist_sq);
        candidate.tca_seconds = 0.0;
        results.push_back(candidate);
    }
    
    // Calculate distance from center to splitting plane
    double axis_dist;
    if (node->axis == 0) axis_dist = center.x - node->point.x;
    else if (node->axis == 1) axis_dist = center.y - node->point.y;
    else axis_dist = center.z - node->point.z;
    
    // Search the side that contains the center first (better pruning)
    if (axis_dist <= 0) {
        radiusSearch(node->left, center, radius, results);
        if (axis_dist * axis_dist <= radius_sq) {
            radiusSearch(node->right, center, radius, results);
        }
    } else {
        radiusSearch(node->right, center, radius, results);
        if (axis_dist * axis_dist <= radius_sq) {
            radiusSearch(node->left, center, radius, results);
        }
    }
}

std::vector<ConjunctionCandidate> KDTree::query_radius(const Vec3& center, double radius_km) {
    std::vector<ConjunctionCandidate> results;
    results.reserve(100);  // Pre-allocate for typical query size
    radiusSearch(root, center, radius_km, results);
    return results;
}

// Bulk query for all satellites - optimized for 10,000+ objects
std::vector<CDMWarning> run_conjunction_assessment(
    const std::vector<OrbitalObject>& satellites,
    const std::vector<OrbitalObject>& debris,
    double lookahead_seconds,
    double dt_step,
    double distance_threshold_km) {
    
    std::vector<CDMWarning> warnings;
    warnings.reserve(50);  // Typical number of warnings
    
    // Build KD-Tree from debris positions - O(N log N)
    std::vector<std::pair<Vec3, std::string>> debris_points;
    debris_points.reserve(debris.size());
    
    // Create lookup map for O(1) debris access
    std::unordered_map<std::string, const OrbitalObject*> debris_map;
    debris_map.reserve(debris.size());
    
    for (const auto& deb : debris) {
        debris_points.emplace_back(deb.state.r, deb.id);
        debris_map[deb.id] = &deb;
    }
    
    KDTree debris_tree;
    debris_tree.build(debris_points);
    
    // Process satellites in parallel batches for cache efficiency
    const size_t BATCH_SIZE = 64;
    
    for (size_t batch_start = 0; batch_start < satellites.size(); batch_start += BATCH_SIZE) {
        size_t batch_end = std::min(batch_start + BATCH_SIZE, satellites.size());
        
        for (size_t i = batch_start; i < batch_end; ++i) {
            const auto& sat = satellites[i];
            
            // Coarse filter: find debris within 50 km using KD-Tree - O(log N) per query
            auto candidates = debris_tree.query_radius(sat.state.r, 50.0);
            
            // Process candidates
            for (auto& candidate : candidates) {
                auto it = debris_map.find(candidate.debris_id);
                if (it == debris_map.end()) continue;
                
                const OrbitalObject* deb_obj = it->second;
                
                // Fast analytical TCA estimation (Section 6.3)
                Vec3 dr = {
                    sat.state.r.x - deb_obj->state.r.x,
                    sat.state.r.y - deb_obj->state.r.y,
                    sat.state.r.z - deb_obj->state.r.z
                };
                Vec3 dv = {
                    sat.state.v.x - deb_obj->state.v.x,
                    sat.state.v.y - deb_obj->state.v.y,
                    sat.state.v.z - deb_obj->state.v.z
                };
                
                // Time to closest approach: t = - (dr · dv) / |dv|²
                double dr_dot_dv = dr.x*dv.x + dr.y*dv.y + dr.z*dv.z;
                double dv_sq = dv.x*dv.x + dv.y*dv.y + dv.z*dv.z;
                
                sat_state = sat_next;
                deb_state = deb_next;
            }
            
            // Check if this is a conjunction (< threshold)
            if (min_distance < distance_threshold_km) {
                CDMWarning warning;
                warning.satellite_id = sat.id;
                warning.debris_id = candidate.debris_id;
                warning.tca_seconds_from_now = tca;
                warning.miss_distance_km = min_distance;
                
                double tca = -dr_dot_dv / dv_sq;
                
                // Skip if TCA is outside lookahead window
                if (tca < 0 || tca > lookahead_seconds) continue;
                
                // Calculate miss distance at TCA
                Vec3 dr_tca = {
                    dr.x + dv.x * tca,
                    dr.y + dv.y * tca,
                    dr.z + dv.z * tca
                };
                double miss_distance = sqrt(dr_tca.x*dr_tca.x + dr_tca.y*dr_tca.y + dr_tca.z*dr_tca.z);
                
                // Check if conjunction (< 5 km threshold per Section 6.3)
                if (miss_distance < 5.0) {
                    CDMWarning warning;
                    warning.satellite_id = sat.id;
                    warning.debris_id = candidate.debris_id;
                    warning.tca_seconds_from_now = tca;
                    warning.miss_distance_km = miss_distance;
                    warning.relative_velocity = dv;
                    
                    warnings.push_back(warning);
                }
            }
        }
    }
    
    return warnings;
}
