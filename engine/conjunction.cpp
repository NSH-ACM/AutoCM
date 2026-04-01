#include "conjunction.h"
#include <algorithm>
#include <cmath>

double KDTree::distance(const Vec3& a, const Vec3& b) const {
    double dx = a.x - b.x;
    double dy = a.y - b.y;
    double dz = a.z - b.z;
    return sqrt(dx*dx + dy*dy + dz*dz);
}

std::shared_ptr<KDNode> KDTree::buildTree(std::vector<std::pair<Vec3, std::string>>& points,
                                         int start, int end, int axis) {
    if (start >= end) {
        return nullptr;
    }
    
    int mid = (start + end) / 2;
    
    // Sort points based on current axis
    auto compare = [axis](const std::pair<Vec3, std::string>& a, 
                          const std::pair<Vec3, std::string>& b) {
        if (axis == 0) return a.first.x < b.first.x;
        if (axis == 1) return a.first.y < b.first.y;
        return a.first.z < b.first.z;
    };
    
    std::nth_element(points.begin() + start, points.begin() + mid, points.begin() + end, compare);
    
    auto node = std::make_shared<KDNode>(points[mid].first, points[mid].second, axis);
    
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

void KDTree::radiusSearch(const std::shared_ptr<KDNode>& node,
                         const Vec3& center, double radius,
                         std::vector<ConjunctionCandidate>& results) {
    if (!node) return;
    
    // Check if current node is within radius
    double dist = distance(node->point, center);
    if (dist <= radius) {
        ConjunctionCandidate candidate;
        candidate.debris_id = node->id;
        candidate.distance_km = dist;
        candidate.tca_seconds = 0.0;  // To be filled by caller
        results.push_back(candidate);
    }
    
    // Calculate distance from center to splitting plane
    double axis_dist;
    if (node->axis == 0) axis_dist = center.x - node->point.x;
    else if (node->axis == 1) axis_dist = center.y - node->point.y;
    else axis_dist = center.z - node->point.z;
    
    // Search the side that contains the center
    if (axis_dist <= 0) {
        radiusSearch(node->left, center, radius, results);
        // Check if we need to search the other side
        if (axis_dist * axis_dist <= radius * radius) {
            radiusSearch(node->right, center, radius, results);
        }
    } else {
        radiusSearch(node->right, center, radius, results);
        // Check if we need to search the other side
        if (axis_dist * axis_dist <= radius * radius) {
            radiusSearch(node->left, center, radius, results);
        }
    }
}

std::vector<ConjunctionCandidate> KDTree::query_radius(const Vec3& center, double radius_km) {
    std::vector<ConjunctionCandidate> results;
    radiusSearch(root, center, radius_km, results);
    return results;
}

std::vector<CDMWarning> run_conjunction_assessment(
    const std::vector<OrbitalObject>& satellites,
    const std::vector<OrbitalObject>& debris,
    double lookahead_seconds,
    double dt_step,
    double distance_threshold_km) {
    
    std::vector<CDMWarning> warnings;
    
    auto distance = [](const Vec3& a, const Vec3& b) -> double {
        double dx = a.x - b.x;
        double dy = a.y - b.y;
        double dz = a.z - b.z;
        return sqrt(dx*dx + dy*dy + dz*dz);
    };
    
    // Build KD-Tree from current debris positions
    std::vector<std::pair<Vec3, std::string>> debris_points;
    for (const auto& deb : debris) {
        debris_points.emplace_back(deb.state.r, deb.id);
    }
    
    KDTree debris_tree;
    debris_tree.build(debris_points);
    
    // For each satellite, find nearby debris and assess conjunctions
    for (const auto& sat : satellites) {
        // Coarse filter: find debris within 50 km
        auto candidates = debris_tree.query_radius(sat.state.r, 50.0);
        
        for (auto& candidate : candidates) {
            // Find the debris object
            const OrbitalObject* deb_obj = nullptr;
            for (const auto& deb : debris) {
                if (deb.id == candidate.debris_id) {
                    deb_obj = &deb;
                    break;
                }
            }
            
            if (!deb_obj) continue;
            
            // Propagate both objects forward to find TCA
            StateVector sat_state = sat.state;
            StateVector deb_state = deb_obj->state;
            
            double min_distance = candidate.distance_km;
            double tca = 0.0;
            double current_time = 0.0;
            
            // Propagate forward in time steps
            while (current_time < lookahead_seconds) {
                current_time += dt_step;
                
                StateVector sat_next = propagate(sat_state, dt_step);
                StateVector deb_next = propagate(deb_state, dt_step);
                
                double current_distance = distance(sat_next.r, deb_next.r);
                
                if (current_distance < min_distance) {
                    min_distance = current_distance;
                    tca = current_time;
                    
                    // Early exit if we're getting farther again
                    if (min_distance < 0.1) break;
                }
                
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
                
                // Calculate relative velocity at TCA
                StateVector sat_tca = propagate(sat.state, tca);
                StateVector deb_tca = propagate(deb_obj->state, tca);
                warning.relative_velocity = {
                    sat_tca.v.x - deb_tca.v.x,
                    sat_tca.v.y - deb_tca.v.y,
                    sat_tca.v.z - deb_tca.v.z
                };
                
                warnings.push_back(warning);
            }
        }
    }
    
    return warnings;
}
