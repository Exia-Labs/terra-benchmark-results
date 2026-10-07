"""Evaluator-only vectorized Vincenty inverse, independent of production PROJ Geod.

Used only for the bounded country-local task fixtures. Nonconvergence is a setup
blocker, never an approximate fallback. GeographicLib supplies independent checks.
"""

import numpy as np

from .common import Blocked


def vincenty_metres(lon1, lat1, lon2, lat2):
    a = 6378137.0
    f = 1 / 298.257223563
    b = a * (1 - f)
    phi1, phi2 = np.deg2rad(lat1), np.deg2rad(lat2)
    u1, u2 = np.arctan((1 - f) * np.tan(phi1)), np.arctan((1 - f) * np.tan(phi2))
    su1, cu1, su2, cu2 = np.sin(u1), np.cos(u1), np.sin(u2), np.cos(u2)
    length = np.deg2rad((np.asarray(lon2) - np.asarray(lon1) + 180) % 360 - 180)
    lam = length.copy()
    for _ in range(100):
        sl, cl = np.sin(lam), np.cos(lam)
        sin_sigma = np.sqrt((cu2 * sl) ** 2 + (cu1 * su2 - su1 * cu2 * cl) ** 2)
        cos_sigma = su1 * su2 + cu1 * cu2 * cl
        sigma = np.arctan2(sin_sigma, cos_sigma)
        sin_alpha = np.divide(cu1 * cu2 * sl, sin_sigma, out=np.zeros_like(sin_sigma), where=sin_sigma != 0)
        cos2_alpha = 1 - sin_alpha**2
        cos2_middle = cos_sigma - np.divide(
            2 * su1 * su2, cos2_alpha, out=np.zeros_like(cos_sigma), where=cos2_alpha > 1e-15
        )
        c = f / 16 * cos2_alpha * (4 + f * (4 - 3 * cos2_alpha))
        updated = length + (1 - c) * f * sin_alpha * (
            sigma + c * sin_sigma * (cos2_middle + c * cos_sigma * (-1 + 2 * cos2_middle**2))
        )
        if np.max(np.abs(updated - lam), initial=0) < 1e-13:
            break
        lam = updated
    else:
        raise Blocked("Independent Vincenty oracle did not converge; no approximate answer is accepted.")
    u2_term = cos2_alpha * (a * a - b * b) / (b * b)
    coeff_a = 1 + u2_term / 16384 * (4096 + u2_term * (-768 + u2_term * (320 - 175 * u2_term)))
    coeff_b = u2_term / 1024 * (256 + u2_term * (-128 + u2_term * (74 - 47 * u2_term)))
    delta = (
        coeff_b
        * sin_sigma
        * (
            cos2_middle
            + coeff_b
            / 4
            * (
                cos_sigma * (-1 + 2 * cos2_middle**2)
                - coeff_b / 6 * cos2_middle * (-3 + 4 * sin_sigma**2) * (-3 + 4 * cos2_middle**2)
            )
        )
    )
    return b * coeff_a * (sigma - delta)


def nearest_distances(lon, lat, points):
    result = np.full(np.shape(lon), np.inf)
    for px, py in points:
        result = np.minimum(result, vincenty_metres(lon, lat, px, py))
    if not np.isfinite(result).all():
        raise Blocked("Independent nearest-distance oracle has no complete finite result.")
    return result
