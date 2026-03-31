#include <cassert>
#include <iostream>
#include <cmath>
#include "../propagator.h"

void test_circular_orbit_propagation() {
    std::cout << "Testing circular orbit propagation..." << std::endl;
    
    // Create a circular LEO orbit at 500 km altitude
    double altitude = 500.0;  // km
    double r_norm = RE + altitude;
    double v_circular = sqrt(MU / r_norm);
    
    StateVector initial_state;
    initial_state.t = 0.0;
    initial_state.r = {r_norm, 0.0, 0.0};
    initial_state.v = {0.0, v_circular, 0.0};
    
    // Calculate orbital period: T = 2π * sqrt(a³/MU)
    double period = 2.0 * M_PI * sqrt(pow(r_norm, 3) / MU);
    
    // Propagate for exactly one orbital period
    StateVector final_state = propagate(initial_state, period);
    
    // Check that radius changed by less than 1 km
    double final_r_norm = final_state.r.norm();
    double radius_change = std::abs(final_r_norm - r_norm);
    
    std::cout << "Initial radius: " << r_norm << " km" << std::endl;
    std::cout << "Final radius: " << final_r_norm << " km" << std::endl;
    std::cout << "Radius change: " << radius_change << " km" << std::endl;
    
    assert(radius_change < 1.0 && "Radius change should be < 1 km for one orbital period");
    
    // Check that satellite returns within 5 km of starting position
    double position_error = sqrt(
        pow(final_state.r.x - initial_state.r.x, 2) +
        pow(final_state.r.y - initial_state.r.y, 2) +
        pow(final_state.r.z - initial_state.r.z, 2)
    );
    
    std::cout << "Position error after one period: " << position_error << " km" << std::endl;
    assert(position_error < 5.0 && "Position error should be < 5 km for one orbital period");
    
    std::cout << "Circular orbit test PASSED!" << std::endl << std::endl;
}

void test_j2_raan_drift() {
    std::cout << "Testing J2-induced RAAN drift..." << std::endl;
    
    // Create an inclined circular orbit (should show RAAN drift)
    double altitude = 500.0;  // km
    double inclination = 45.0 * M_PI / 180.0;  // 45 degrees in radians
    double r_norm = RE + altitude;
    double v_circular = sqrt(MU / r_norm);
    
    StateVector initial_state;
    initial_state.t = 0.0;
    
    // Start in orbital plane with inclination
    initial_state.r = {r_norm * cos(inclination), 0.0, r_norm * sin(inclination)};
    initial_state.v = {0.0, v_circular, 0.0};
    
    // Propagate for 24 hours
    double propagation_time = 86400.0;  // 24 hours in seconds
    StateVector final_state = propagate(initial_state, propagation_time);
    
    // Calculate initial and final orbital planes
    // Initial orbital plane normal: r × v
    Vec3 initial_node = {
        initial_state.r.y * initial_state.v.z - initial_state.r.z * initial_state.v.y,
        initial_state.r.z * initial_state.v.x - initial_state.r.x * initial_state.v.z,
        initial_state.r.x * initial_state.v.y - initial_state.r.y * initial_state.v.x
    };
    
    Vec3 final_node = {
        final_state.r.y * final_state.v.z - final_state.r.z * final_state.v.y,
        final_state.r.z * final_state.v.x - final_state.r.x * final_state.v.z,
        final_state.r.x * final_state.v.y - final_state.r.y * final_state.v.x
    };
    
    // Normalize
    double initial_node_norm = initial_node.norm();
    double final_node_norm = final_node.norm();
    initial_node = {initial_node.x / initial_node_norm, 
                    initial_node.y / initial_node_norm, 
                    initial_node.z / initial_node_norm};
    final_node = {final_node.x / final_node_norm, 
                  final_node.y / final_node_norm, 
                  final_node.z / final_node_norm};
    
    // Calculate RAAN change using dot product
    double dot_product = initial_node.x * final_node.x + 
                        initial_node.y * final_node.y + 
                        initial_node.z * final_node.z;
    dot_product = std::max(-1.0, std::min(1.0, dot_product));  // Clamp to [-1, 1]
    
    double raan_change_rad = acos(dot_product);
    double raan_change_deg = raan_change_rad * 180.0 / M_PI;
    
    std::cout << "RAAN change over 24 hours: " << raan_change_deg << " degrees" << std::endl;
    
    assert(raan_change_deg > 0.0 && "RAAN should drift due to J2 perturbation");
    assert(raan_change_deg > 0.1 && "RAAN drift should be measurable (> 0.1 degrees)");
    
    std::cout << "J2 RAAN drift test PASSED!" << std::endl << std::endl;
}

void test_energy_conservation() {
    std::cout << "Testing energy conservation..." << std::endl;
    
    // Create an elliptical orbit
    double perigee_altitude = 400.0;  // km
    double apogee_altitude = 600.0;   // km
    
    double r_perigee = RE + perigee_altitude;
    double r_apogee = RE + apogee_altitude;
    double semi_major_axis = (r_perigee + r_apogee) / 2.0;
    
    // Velocity at perigee for elliptical orbit
    double v_perigee = sqrt(MU * (2.0/r_perigee - 1.0/semi_major_axis));
    
    StateVector initial_state;
    initial_state.t = 0.0;
    initial_state.r = {r_perigee, 0.0, 0.0};
    initial_state.v = {0.0, v_perigee, 0.0};
    
    // Calculate specific orbital energy
    auto specific_energy = [](const StateVector& state) -> double {
        double r_norm = state.r.norm();
        double v_norm = state.v.norm();
        return v_norm*v_norm/2.0 - MU/r_norm;
    };
    
    double initial_energy = specific_energy(initial_state);
    
    // Propagate for several orbits
    double period = 2.0 * M_PI * sqrt(pow(semi_major_axis, 3) / MU);
    StateVector final_state = propagate(initial_state, period * 3.0);
    
    double final_energy = specific_energy(final_state);
    double energy_change = std::abs(final_energy - initial_energy);
    double relative_change = energy_change / std::abs(initial_energy);
    
    std::cout << "Initial specific energy: " << initial_energy << " km²/s²" << std::endl;
    std::cout << "Final specific energy: " << final_energy << " km²/s²" << std::endl;
    std::cout << "Relative energy change: " << relative_change * 100 << "%" << std::endl;
    
    assert(relative_change < 0.001 && "Energy should be conserved to within 0.1%");
    
    std::cout << "Energy conservation test PASSED!" << std::endl << std::endl;
}

int main() {
    std::cout << "Running AutoCM Propagator Unit Tests" << std::endl;
    std::cout << "=====================================" << std::endl << std::endl;
    
    try {
        test_circular_orbit_propagation();
        test_j2_raan_drift();
        test_energy_conservation();
        
        std::cout << "All tests PASSED!" << std::endl;
        return 0;
    } catch (const std::exception& e) {
        std::cerr << "Test failed with exception: " << e.what() << std::endl;
        return 1;
    } catch (...) {
        std::cerr << "Test failed with unknown exception" << std::endl;
        return 1;
    }
}
