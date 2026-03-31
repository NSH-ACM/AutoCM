/**
 * ═══════════════════════════════════════════════════════════════════════════
 *  ACM PHYSICS ENGINE — conjunction.cpp
 *  Axis-sweep collision detection with parabolic TCA refinement.
 *  National Space Hackathon 2026
 *
 *  Algorithm: O(N log M) collision detection using:
 *    1. Sorted debris array (x-axis) with binary search (axis-sweep)
 *    2. Broad-phase: 50 km gate on x, y, z axes
 *    3. Narrow-phase: Parabolic (2nd-order) TCA via Cardano's method
 *    4. Insertion sort for O(N) avg re-sorting after each time step
 *
 *  Functions:
 *    closest_approach_parabolic(rs, vs, rd, vd, window) — TCA calculator
 *    detect_conjunctions(sats, debris, lookahead, epoch) — main screener
 *
 *  Reference: Alfano & Greer, "Determining If Two Ellipsoidal Bodies Are
 *             Close/Collision Candidate", AAS 92-121.
 * ═══════════════════════════════════════════════════════════════════════════
 */

#include "common.h"

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

namespace py = pybind11;

// Forward declarations from propagator.cpp
extern Vec3 accel_j2(const Vec3& r);
extern std::pair<Vec3, Vec3> rk4_step(Vec3 r, Vec3 v, double dt, double bstar);

// ═══════════════════════════════════════════════════════════════════════════
//  PARABOLIC TCA (2nd-order closest approach)
// ═══════════════════════════════════════════════════════════════════════════

struct TCA { double t_sec, miss_dist_km; };

/**
 * Parabolic TCA: includes relative acceleration so that relative range²
 * is modeled as:
 *   f(t) = |dr + dv·t + ½·da·t²|²
 *
 * Setting f'(t) = 0 leads to a cubic solved via Cardano's depressed cubic.
 * Falls back to quadratic/linear for degenerate cases.
 */
static TCA closest_approach_parabolic(const Vec3& rs, const Vec3& vs,
                                       const Vec3& rd, const Vec3& vd,
                                       double window_s) {
    Vec3 dr = rs - rd;
    Vec3 dv = vs - vd;
    Vec3 da = accel_j2(rs) - accel_j2(rd);

    // Cubic coefficients for f'(t)/2 = 0
    double a3 = da.dot(da) * 0.25;
    double a2 = dv.dot(da);
    double a1 = dv.dot(dv) + dr.dot(da);
    double a0 = dr.dot(dv);

    std::array<double, 8> candidates = {0.0, window_s, -1, -1, -1, -1, -1, -1};
    int nc = 2;

    auto miss_at = [&](double t) -> double {
        Vec3 d = dr + dv * t + da * (0.5 * t * t);
        return d.norm();
    };

    if (std::abs(a3) < 1e-20) {
        if (std::abs(a2) < 1e-20) {
            if (std::abs(a1) > 1e-20) candidates[nc++] = -a0 / a1;
        } else {
            double disc = a1*a1 - 4.0*a2*a0;
            if (disc >= 0.0) {
                double sq = std::sqrt(disc);
                candidates[nc++] = (-a1 + sq) / (2.0 * a2);
                candidates[nc++] = (-a1 - sq) / (2.0 * a2);
            }
        }
    } else {
        // Full cubic via depressed form (Cardano)
        double inv3a3 = 1.0 / (3.0 * a3);
        double p = (a1 - a2*a2*inv3a3) * inv3a3;
        double q = (2.0*a2*a2*a2/(27.0*a3*a3) - a1*a2/(3.0*a3) + a0) * inv3a3;
        double shift = -a2 * inv3a3;

        double disc = q*q/4.0 + p*p*p/27.0;
        if (disc > 0.0) {
            double sq = std::sqrt(disc);
            candidates[nc++] = std::cbrt(-q/2.0 + sq) + std::cbrt(-q/2.0 - sq) + shift;
        } else {
            double r_val = std::sqrt(-p*p*p / 27.0);
            double theta = std::acos(std::clamp(-q / (2.0 * r_val), -1.0, 1.0));
            double mag   = 2.0 * std::cbrt(r_val);
            candidates[nc++] = mag * std::cos( theta            / 3.0) + shift;
            candidates[nc++] = mag * std::cos((theta + 2*M_PI) / 3.0) + shift;
            candidates[nc++] = mag * std::cos((theta + 4*M_PI) / 3.0) + shift;
        }
    }

    TCA best{ 0.0, miss_at(0.0) };
    for (int i = 0; i < nc; ++i) {
        double t = candidates[i];
        if (t < 0.0 || t > window_s) continue;
        double m = miss_at(t);
        if (m < best.miss_dist_km) best = {t, m};
    }
    return best;
}

// ═══════════════════════════════════════════════════════════════════════════
//  INSERTION SORT (O(N) on nearly-sorted data)
// ═══════════════════════════════════════════════════════════════════════════

template<typename T, typename KeyFn>
static void insertion_sort_by(std::vector<T>& v, KeyFn key) {
    for (int i = 1; i < (int)v.size(); ++i) {
        T tmp = v[i];
        double k = key(tmp);
        int j = i - 1;
        while (j >= 0 && key(v[j]) > k) {
            v[j + 1] = v[j];
            --j;
        }
        v[j + 1] = tmp;
    }
}

// ═══════════════════════════════════════════════════════════════════════════
//  CDM DEDUPLICATION
// ═══════════════════════════════════════════════════════════════════════════

struct PairHash {
    size_t operator()(const std::pair<std::string,std::string>& p) const noexcept {
        size_t h1 = std::hash<std::string>{}(p.first);
        size_t h2 = std::hash<std::string>{}(p.second);
        return h1 ^ (h2 + 0x9e3779b97f4a7c15ULL + (h1 << 6) + (h1 >> 2));
    }
};

// ═══════════════════════════════════════════════════════════════════════════
//  ISO 8601 TIME ARITHMETIC
// ═══════════════════════════════════════════════════════════════════════════

static std::string add_seconds_to_iso(const std::string& epoch_iso, double offset_s) {
    int Y=2000, Mo=1, D=1, h=0, mi=0;
    double s=0.0;
    int parsed = std::sscanf(epoch_iso.c_str(),
                             "%d-%d-%dT%d:%d:%lf", &Y, &Mo, &D, &h, &mi, &s);
    if (parsed < 6) {
        std::ostringstream ss;
        ss << "T+" << static_cast<long long>(offset_s) << "s";
        return ss.str();
    }

    double total_s = h * 3600.0 + mi * 60.0 + s + offset_s;
    int extra_days = static_cast<int>(std::floor(total_s / 86400.0));
    total_s -= extra_days * 86400.0;

    if (extra_days != 0) {
        int a = (14 - Mo) / 12;
        int y = Y + 4800 - a;
        int m = Mo + 12 * a - 3;
        int jdn = D + (153*m+2)/5 + 365*y + y/4 - y/100 + y/400 - 32045;
        jdn += extra_days;
        int f  = jdn + 1401 + (((4*jdn+274277)/146097)*3)/4 - 38;
        int e  = 4*f + 3;
        int g  = (e%1461)/4;
        int h_ = 5*g + 2;
        D  = (h_%153)/5 + 1;
        Mo = (h_/153 + 2)%12 + 1;
        Y  = e/1461 - 4716 + (14-Mo)/12;
    }

    int out_h  = static_cast<int>(total_s / 3600);
    int out_mi = static_cast<int>((total_s - out_h * 3600.0) / 60);
    double out_s = total_s - out_h * 3600.0 - out_mi * 60.0;

    char buf[64];
    std::snprintf(buf, sizeof(buf), "%04d-%02d-%02dT%02d:%02d:%06.3fZ",
                  Y, Mo, D, out_h, out_mi, out_s);
    return buf;
}

// ═══════════════════════════════════════════════════════════════════════════
//  MAIN CONJUNCTION SCREENER
// ═══════════════════════════════════════════════════════════════════════════

/**
 * detect_conjunctions(satellites, debris, lookahead_seconds [, epoch_iso])
 *   -> list[CDM]
 *
 * Algorithm:
 *   1. Parse all debris, sort by x (axis-sweep).
 *   2. For each time step (60s intervals):
 *      a. Binary search to find debris within 50km broad gate.
 *      b. Parabolic TCA on candidates.
 *      c. Record best miss per (sat, debris) pair.
 *      d. Advance all objects. Insertion sort debris.
 *   3. Output CDMs with miss < 5 km.
 */
py::list detect_conjunctions(py::list satellites, py::list debris,
                              double lookahead_seconds,
                              const std::string& epoch_iso = "") {
    telemetry::conjunction_calls.fetch_add(1, std::memory_order_relaxed);

    if (lookahead_seconds <= 0.0)
        throw std::invalid_argument("detect_conjunctions: lookahead_seconds must be > 0");

    const double BROAD_GATE_KM  = 50.0;
    const double REPORT_DIST_KM = 5.0;
    const double STEP_S         = 60.0;
    const double CDM_PROB_SCALE = 1e-4;

    auto parse_states = [](py::list lst) {
        std::vector<ObjState> v;
        v.reserve(py::len(lst));
        for (auto item : lst) {
            py::dict d = item.cast<py::dict>();
            py::dict r = d["r"].cast<py::dict>();
            py::dict vv = d["v"].cast<py::dict>();
            ObjState os;
            os.id = d["id"].cast<std::string>();
            os.r = { r["x"].cast<double>(), r["y"].cast<double>(), r["z"].cast<double>() };
            os.v = { vv["x"].cast<double>(), vv["y"].cast<double>(), vv["z"].cast<double>() };
            v.push_back(os);
        }
        return v;
    };

    std::vector<ObjState> deb_now = parse_states(debris);
    std::vector<ObjState> sat_now = parse_states(satellites);

    const int steps = std::max(1, static_cast<int>(lookahead_seconds / STEP_S));

    auto key_x = [](const ObjState& s) { return s.r.x; };
    std::sort(deb_now.begin(), deb_now.end(),
              [](const ObjState& a, const ObjState& b){ return a.r.x < b.r.x; });

    using PairKey = std::pair<std::string,std::string>;
    struct BestCDM { double miss_km; double t_s; };
    std::unordered_map<PairKey, BestCDM, PairHash> best;

    for (int step = 0; step < steps; ++step) {
        const double t_step    = step * STEP_S;
        const double remaining = lookahead_seconds - t_step;

        for (auto& sat : sat_now) {
            auto lo = std::lower_bound(deb_now.begin(), deb_now.end(),
                sat.r.x - BROAD_GATE_KM,
                [](const ObjState& d, double val){ return d.r.x < val; });
            auto hi = std::upper_bound(deb_now.begin(), deb_now.end(),
                sat.r.x + BROAD_GATE_KM,
                [](double val, const ObjState& d){ return val < d.r.x; });

            for (auto it = lo; it != hi; ++it) {
                if (std::abs(it->r.y - sat.r.y) > BROAD_GATE_KM) continue;
                if (std::abs(it->r.z - sat.r.z) > BROAD_GATE_KM) continue;
                Vec3 diff = sat.r - it->r;
                if (diff.norm2() > BROAD_GATE_KM * BROAD_GATE_KM) continue;

                TCA tca = closest_approach_parabolic(
                    sat.r, sat.v, it->r, it->v, remaining);
                if (tca.miss_dist_km >= REPORT_DIST_KM) continue;

                PairKey key{sat.id, it->id};
                double  abs_t = t_step + tca.t_sec;
                auto    found = best.find(key);
                if (found == best.end() || tca.miss_dist_km < found->second.miss_km)
                    best[key] = { tca.miss_dist_km, abs_t };
            }
        }

        // Advance all objects by one time step
        for (auto& d : deb_now) std::tie(d.r, d.v) = rk4_step(d.r, d.v, STEP_S, 0.0);
        insertion_sort_by(deb_now, key_x);

        for (auto& s : sat_now) std::tie(s.r, s.v) = rk4_step(s.r, s.v, STEP_S, 0.0);
    }

    // Build CDM output
    py::list cdms;
    for (auto& [key, cdm] : best) {
        double prob = CDM_PROB_SCALE / (cdm.miss_km * cdm.miss_km + 0.001);
        prob = std::min(prob, 0.9999);

        std::string tca_str = epoch_iso.empty()
            ? ("T+" + std::to_string(static_cast<long long>(cdm.t_s)) + "s")
            : add_seconds_to_iso(epoch_iso, cdm.t_s);

        py::dict item;
        item["satelliteId"]  = key.first;
        item["debrisId"]     = key.second;
        item["missDistance"] = cdm.miss_km;
        item["probability"]  = prob;
        item["tca_offset_s"] = cdm.t_s;
        item["tca"]          = tca_str;
        cdms.append(item);
    }
    return cdms;
}
