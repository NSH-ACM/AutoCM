#include <iostream>
#include <chrono>
#include <vector>
#include "../propagator.h"
#include "../conjunction.h"

int main() {
    std::cout << "Testing Conjunction Assessment Performance..." << std::endl;
    
    // Create test data: 100 satellites, 5000 debris
    std::vector<OrbitalObject> satellites;
    std::vector<OrbitalObject> debris;
    
    // Generate satellites
    for (int i = 1; i <= 100; ++i) {
        OrbitalObject sat;
        sat.id = "SAT-TEST-" + std::to_string(i);
        sat.type = "SATELLITE";
        sat.mass_dry = 500.0;
        sat.mass_fuel = 50.0;
        sat.controllable = true;
        
        // Random LEO orbit
        double altitude = 450.0 + (i % 150);  // 450-600 km
        double r_norm = RE + altitude;
        double v_circular = sqrt(MU / r_norm);
        
        sat.state.t = 0.0;
        sat.state.r = {r_norm, 0.0, 0.0};
        sat.state.v = {0.0, v_circular, 0.0};
        
        satellites.push_back(sat);
    }
    
    // Generate debris
    for (int i = 1; i <= 5000; ++i) {
        OrbitalObject deb;
        deb.id = "DEB-TEST-" + std::to_string(i);
        deb.type = "DEBRIS";
        deb.mass_dry = 0.0;
        deb.mass_fuel = 0.0;
        deb.controllable = false;
        
        // Random LEO orbit
        double altitude = 400.0 + (i % 250);  // 400-650 km
        double r_norm = RE + altitude;
        double v_circular = sqrt(MU / r_norm);
        
        deb.state.t = 0.0;
        deb.state.r = {r_norm * cos(i * 0.01), r_norm * sin(i * 0.01), 0.0};
        deb.state.v = {-v_circular * sin(i * 0.01), v_circular * cos(i * 0.01), 0.0};
        
        debris.push_back(deb);
    }
    
    std::cout << "Generated " << satellites.size() << " satellites and " 
              << debris.size() << " debris objects" << std::endl;
    
    // Run performance test
    auto start_time = std::chrono::high_resolution_clock::now();
    
    std::vector<CDMWarning> warnings = run_conjunction_assessment(
        satellites, debris, 86400.0, 30.0);
    
    auto end_time = std::chrono::high_resolution_clock::now();
    auto duration = std::chrono::duration_cast<std::chrono::milliseconds>(end_time - start_time);
    
    std::cout << "Conjunction assessment completed in " << duration.count() << " ms" << std::endl;
    std::cout << "Found " << warnings.size() << " conjunction warnings" << std::endl;
    
    // Check performance requirement (< 10 seconds)
    if (duration.count() < 10000) {
        std::cout << "PERFORMANCE TEST PASSED: < 10 seconds" << std::endl;
        return 0;
    } else {
        std::cout << "PERFORMANCE TEST FAILED: > 10 seconds" << std::endl;
        return 1;
    }
}
