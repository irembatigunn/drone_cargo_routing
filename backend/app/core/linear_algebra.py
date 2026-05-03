"""
Linear Algebra Layer — Section 5.6 of PRD.
Eigenvector centrality via power iteration on similarity matrix derived from distance matrix.
Also reports Frobenius norm of distance matrix.
"""
from __future__ import annotations

import math
import numpy as np


def compute_centrality(
    interest_keys: list[str],
    dist_matrix: dict,
    sigma: float | None = None,
    max_iter: int = 200,
    tol: float = 1e-8,
) -> dict:
    """
    1. Build distance sub-matrix D for interest_keys.
    2. Similarity: S = exp(-D / sigma), sigma = mean(D).
    3. Row-normalize → stochastic matrix P.
    4. Power iteration → dominant eigenvector (centrality scores).
    5. Frobenius norm of D.

    Returns:
        {
          "centrality": {node_key: float},
          "frobenius_norm": float,
          "eigenvalue": float,
        }
    """
    n = len(interest_keys)
    if n == 0:
        return {"centrality": {}, "frobenius_norm": 0.0, "eigenvalue": 0.0}

    # Build D matrix
    D = np.zeros((n, n))
    for i, ki in enumerate(interest_keys):
        for j, kj in enumerate(interest_keys):
            if i == j:
                D[i, j] = 0.0
            else:
                try:
                    D[i, j] = dist_matrix[ki][kj]
                except KeyError:
                    try:
                        D[i, j] = dist_matrix[kj][ki]
                    except KeyError:
                        D[i, j] = 9999.0

    # Similarity matrix
    if sigma is None:
        sigma = float(np.mean(D[D > 0])) if np.any(D > 0) else 1.0

    S = np.exp(-D / sigma)
    np.fill_diagonal(S, 0.0)

    # Row-normalize → stochastic matrix P
    row_sums = S.sum(axis=1, keepdims=True)
    row_sums[row_sums == 0] = 1.0
    P = S / row_sums

    # Power iteration
    v = np.ones(n) / n
    eigenvalue = 1.0
    for _ in range(max_iter):
        v_new = P.T @ v
        norm = np.linalg.norm(v_new)
        if norm < 1e-10:
            break
        eigenvalue = float(norm)
        v_new /= norm
        if np.linalg.norm(v_new - v) < tol:
            v = v_new
            break
        v = v_new

    # Normalize to [0, 1]
    v_min, v_max = v.min(), v.max()
    if v_max > v_min:
        v_norm = (v - v_min) / (v_max - v_min)
    else:
        v_norm = np.ones(n) / n

    frobenius = float(np.linalg.norm(D, "fro"))

    return {
        "centrality": {k: round(float(v_norm[i]), 4) for i, k in enumerate(interest_keys)},
        "frobenius_norm": round(frobenius, 2),
        "eigenvalue": round(eigenvalue, 6),
    }
