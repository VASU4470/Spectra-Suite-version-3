import numpy as np
from scipy.signal import savgol_filter
from scipy import sparse
from scipy.sparse.linalg import spsolve
from config import state

def baseline_als(y, lam=10**8, p=0.99, itermax=10):
    """Reverted back to p=0.99 (Hugs the bottom of the data)"""
    L = len(y)
    D = sparse.diags([1, -2, 1], [0, -1, -2], shape=(L, L-2))
    w = np.ones(L)
    for i in range(itermax):
        W = sparse.spdiags(w, 0, L, L)
        Z = W + lam * D.dot(D.transpose())
        z = spsolve(Z, w * y)
        w = p * (y > z) + (1 - p) * (y < z)
    return z

def process_spectrum(x, y, stem):
    fs = state.file_set[stem]
    y_proc = np.copy(y)
    
    # 1. SMOOTHING
    raw_smooth = fs.get('smooth', 0)
    if raw_smooth > 0:
        # Ensure it is an odd number
        sm = raw_smooth if raw_smooth % 2 != 0 else raw_smooth + 1
        
        # FIX: Ensure it is strictly greater than the polyorder of 3!
        if sm < 5: 
            sm = 5 
            
        if len(y_proc) > sm: 
            y_proc = savgol_filter(y_proc, sm, 3)

    # 2. BASELINE CORRECTION (ALS)
    if fs.get('do_baseline', False):
        lam_val = 10 ** fs.get('als_lam', 8.0) 
        # Note: p=0.99 hugs the BOTTOM of the graph (ideal for Absorbance peaks)
        baseline = baseline_als(y_proc, lam=lam_val, p=0.99)
        y_proc = y_proc - baseline

    # 3. DERIVATIVES
    deriv = fs.get('derivative', 0)
    if deriv == 1:
        # Safe to use sm here since we forced it to be >= 5 above (if smoothing was on)
        # If smoothing was OFF, we should default to a safe window like 5 just for the derivative
        d_sm = sm if raw_smooth > 0 else 5
        if len(y_proc) > d_sm:
            y_proc = savgol_filter(y_proc, d_sm, 3, deriv=1)
            
    elif deriv == 2:
        d_sm = sm if raw_smooth > 0 else 5
        if len(y_proc) > d_sm:
            y_proc = savgol_filter(y_proc, d_sm, 3, deriv=2)

    return x, y_proc

def assign_peak_group(x_val):
    from config import IR_TABLE
    for (low, high, group) in IR_TABLE:
        if low <= x_val <= high:
            return group
    return "Unknown"
