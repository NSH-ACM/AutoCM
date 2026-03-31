#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include "propagator.h"
#include "conjunction.h"
#include "maneuver.h"

namespace py = pybind11;

PYBIND11_MODULE(autocm_engine, m) {
    m.doc() = "AutoCM Physics Engine";
    
    // Vec3
    py::class_<Vec3>(m, "Vec3")
        .def(py::init<double,double,double>())
        .def_readwrite("x", &Vec3::x)
        .def_readwrite("y", &Vec3::y)
        .def_readwrite("z", &Vec3::z)
        .def("norm", &Vec3::norm);
    
    // StateVector
    py::class_<StateVector>(m, "StateVector")
        .def(py::init<>())
        .def_readwrite("t", &StateVector::t)
        .def_readwrite("r", &StateVector::r)
        .def_readwrite("v", &StateVector::v);
    
    // OrbitalObject
    py::class_<OrbitalObject>(m, "OrbitalObject")
        .def(py::init<>())
        .def_readwrite("id", &OrbitalObject::id)
        .def_readwrite("type", &OrbitalObject::type)
        .def_readwrite("state", &OrbitalObject::state)
        .def_readwrite("mass_dry", &OrbitalObject::mass_dry)
        .def_readwrite("mass_fuel", &OrbitalObject::mass_fuel)
        .def_readwrite("controllable", &OrbitalObject::controllable);
    
    // CDMWarning
    py::class_<CDMWarning>(m, "CDMWarning")
        .def(py::init<>())
        .def_readwrite("satellite_id", &CDMWarning::satellite_id)
        .def_readwrite("debris_id", &CDMWarning::debris_id)
        .def_readwrite("tca_seconds_from_now", &CDMWarning::tca_seconds_from_now)
        .def_readwrite("miss_distance_km", &CDMWarning::miss_distance_km)
        .def_readwrite("relative_velocity", &CDMWarning::relative_velocity);
    
    // ConjunctionCandidate
    py::class_<ConjunctionCandidate>(m, "ConjunctionCandidate")
        .def(py::init<>())
        .def_readwrite("debris_id", &ConjunctionCandidate::debris_id)
        .def_readwrite("distance_km", &ConjunctionCandidate::distance_km)
        .def_readwrite("tca_seconds", &ConjunctionCandidate::tca_seconds);
    
    // Mat3x3
    py::class_<Mat3x3>(m, "Mat3x3")
        .def(py::init<>());
    
    // ManeuverPlan
    py::class_<ManeuverPlan>(m, "ManeuverPlan")
        .def(py::init<>())
        .def_readwrite("burn_id", &ManeuverPlan::burn_id)
        .def_readwrite("satellite_id", &ManeuverPlan::satellite_id)
        .def_readwrite("burn_time_offset_s", &ManeuverPlan::burn_time_offset_s)
        .def_readwrite("dv_eci_kms", &ManeuverPlan::dv_eci_kms)
        .def_readwrite("estimated_fuel_kg", &ManeuverPlan::estimated_fuel_kg)
        .def_readwrite("is_recovery", &ManeuverPlan::is_recovery);
    
    // Free functions
    m.def("propagate", &propagate);
    m.def("run_conjunction_assessment", &run_conjunction_assessment);
    m.def("plan_evasion", &plan_evasion);
    m.def("plan_recovery", &plan_recovery);
    m.def("apply_burn", &apply_burn);
    m.def("needs_graveyard", &needs_graveyard);
    m.def("plan_graveyard", &plan_graveyard);
    m.def("fuel_consumed", &fuel_consumed);
    m.def("eci_to_rtn_matrix", &eci_to_rtn_matrix);
    m.def("rtn_to_eci", &rtn_to_eci);
}
