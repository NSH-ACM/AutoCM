#include "propagator.h"

Vec3 Vec3::operator+(const Vec3& other) const {
    return {x + other.x, y + other.y, z + other.z};
}

Vec3 Vec3::operator*(double scalar) const {
    return {x * scalar, y * scalar, z * scalar};
}

double Vec3::norm() const {
    return sqrt(x*x + y*y + z*z);
}
