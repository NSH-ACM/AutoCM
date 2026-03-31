#include "propagator.h"
#include <cmath>

Vec3 Vec3::operator+(const Vec3& other) const {
    return {x + other.x, y + other.y, z + other.z};
}

Vec3 Vec3::operator-(const Vec3& other) const {
    return {x - other.x, y - other.y, z - other.z};
}

Vec3 Vec3::operator*(double scalar) const {
    return {x * scalar, y * scalar, z * scalar};
}

Vec3 Vec3::operator/(double scalar) const {
    return {x / scalar, y / scalar, z / scalar};
}

double Vec3::norm() const {
    return sqrt(x*x + y*y + z*z);
}

double Vec3::dot(const Vec3& other) const {
    return x * other.x + y * other.y + z * other.z;
}

Vec3 Vec3::cross(const Vec3& other) const {
    return {
        y * other.z - z * other.y,
        z * other.x - x * other.z,
        x * other.y - y * other.x
    };
}

Vec3 j2_acceleration(const Vec3& r) {
    double r_norm = r.norm();
    double r_squared = r_norm * r_norm;
    double r_fifth = r_squared * r_squared * r_norm;
    
    double factor = (3.0/2.0) * J2 * MU * RE * RE / r_fifth;
    double z_squared = r.z * r.z;
    double term = (5.0 * z_squared / r_squared) - 1.0;
    
    Vec3 accel;
    accel.x = factor * r.x * term;
    accel.y = factor * r.y * term;
    accel.z = factor * r.z * ((5.0 * z_squared / r_squared) - 3.0);
    
    return accel;
}

Vec3 total_acceleration(const Vec3& r) {
    Vec3 two_body_accel;
    double r_norm = r.norm();
    double r_cubed = r_norm * r_norm * r_norm;
    
    two_body_accel.x = -MU * r.x / r_cubed;
    two_body_accel.y = -MU * r.y / r_cubed;
    two_body_accel.z = -MU * r.z / r_cubed;
    
    Vec3 j2_acc = j2_acceleration(r);
    
    return two_body_accel + j2_acc;
}

StateVector rk4_step(const StateVector& s, double dt) {
    auto state_derivative = [](const StateVector& state) -> StateVector {
        StateVector derivative;
        derivative.t = state.t;
        derivative.r = state.v;
        derivative.v = total_acceleration(state.r);
        return derivative;
    };
    
    // k1 = f(s)
    StateVector k1 = state_derivative(s);
    
    // k2 = f(s + dt/2 * k1)
    StateVector s_temp = s;
    s_temp.r = s_temp.r + k1.r * (dt/2.0);
    s_temp.v = s_temp.v + k1.v * (dt/2.0);
    StateVector k2 = state_derivative(s_temp);
    
    // k3 = f(s + dt/2 * k2)
    s_temp = s;
    s_temp.r = s_temp.r + k2.r * (dt/2.0);
    s_temp.v = s_temp.v + k2.v * (dt/2.0);
    StateVector k3 = state_derivative(s_temp);
    
    // k4 = f(s + dt * k3)
    s_temp = s;
    s_temp.r = s_temp.r + k3.r * dt;
    s_temp.v = s_temp.v + k3.v * dt;
    StateVector k4 = state_derivative(s_temp);
    
    // s_new = s + (dt/6)*(k1 + 2k2 + 2k3 + k4)
    StateVector s_new = s;
    s_new.r = s_new.r + (k1.r + k2.r * 2.0 + k3.r * 2.0 + k4.r) * (dt/6.0);
    s_new.v = s_new.v + (k1.v + k2.v * 2.0 + k3.v * 2.0 + k4.v) * (dt/6.0);
    s_new.t = s_new.t + dt;
    
    return s_new;
}

StateVector propagate(const StateVector& s0, double dt_total, double dt_step) {
    StateVector current = s0;
    double remaining_time = dt_total;
    
    while (remaining_time > 0) {
        double step = (remaining_time < dt_step) ? remaining_time : dt_step;
        current = rk4_step(current, step);
        remaining_time -= step;
    }
    
    return current;
}
