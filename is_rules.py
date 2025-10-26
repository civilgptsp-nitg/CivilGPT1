"""
is_rules.py
---------------
Central repository of IS code–based constants and helper functions
for CivilGPT (concrete mix designer).
Enhanced for HPC, Purpose-Based Optimization, and Expanded Grade Range.
"""

import numpy as np
import pandas as pd

# =========================
# IS 456 Durability Rules
# =========================
EXPOSURE_WB_LIMITS = {
    "Mild": 0.60,
    "Moderate": 0.55,
    "Severe": 0.50,
    "Very Severe": 0.45,
    "Marine": 0.40,
}

EXPOSURE_MIN_CEMENT = {
    "Mild": 300,
    "Moderate": 300,
    "Severe": 320,
    "Very Severe": 340,
    "Marine": 360,
}

EXPOSURE_MIN_GRADE = {
    "Mild": "M20",
    "Moderate": "M25",
    "Severe": "M30",
    "Very Severe": "M35",
    "Marine": "M40",
}

# =========================
# Concrete Grades (IS 456) - EXPANDED RANGE
# =========================
GRADE_STRENGTH = {
    "M10": 10, "M15": 15, "M20": 20, "M25": 25, "M30": 30, 
    "M35": 35, "M40": 40, "M45": 45, "M50": 50, "M60": 60, 
    "M70": 70, "M80": 80, "M90": 90, "M100": 100
}

# =========================
# Purpose-Based Constraints (Pseudocode Implementation)
# =========================
PURPOSE_PROFILES = {
    "General": {
        "description": "A balanced, default mix. Follows IS code minimums without specific optimization bias.",
        "wb_limit": 1.0,
        "scm_limit": 0.5,
        "min_binder": 0.0,
        "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2},
        "hard_constraints": {}
    },
    "Slab": {
        "description": "Prioritizes workability and cost-effectiveness. Strength is often not the primary driver.",
        "wb_limit": 0.55,
        "scm_limit": 0.5,
        "min_binder": 300,
        "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2},
        "hard_constraints": {
            "max_deflection_proxy": 0.8,
            "min_modulus": 25000
        }
    },
    "Beam": {
        "description": "Prioritizes strength (modulus) and durability. Often heavily reinforced.",
        "wb_limit": 0.50,
        "scm_limit": 0.4,
        "min_binder": 320,
        "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4},
        "hard_constraints": {
            "min_compressive_strength": 30,
            "max_shrinkage_risk": 15.0
        }
    },
    "Column": {
        "description": "Prioritizes high compressive strength and durability. Congestion is common.",
        "wb_limit": 0.45,
        "scm_limit": 0.35,
        "min_binder": 340,
        "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5},
        "hard_constraints": {
            "min_compressive_strength": 35,
            "max_shrinkage_risk": 12.0
        }
    },
    "Pavement": {
        "description": "Prioritizes durability, flexural strength (fatigue), and abrasion resistance.",
        "wb_limit": 0.45,
        "scm_limit": 0.4,
        "min_binder": 340,
        "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3},
        "hard_constraints": {
            "min_flexural_strength": 4.5,
            "fatigue_proxy_min": 0.7,
            "max_wb_for_frost": 0.45
        }
    },
    "Precast": {
        "description": "Prioritizes high early strength, surface finish, and cost reproducibility.",
        "wb_limit": 0.45,
        "scm_limit": 0.3,
        "min_binder": 360,
        "weights": {"co2": 0.2, "cost": 0.5, "purpose": 0.3},
        "hard_constraints": {
            "min_early_strength": 15,
            "max_bleeding": 2.0
        }
    },
    "RPC/HPC": {
        "description": "High-Performance Concrete with silica fume, very low w/b ratios, and high strength.",
        "wb_limit": 0.35,
        "scm_limit": 0.25,
        "min_binder": 450,
        "weights": {"co2": 0.4, "cost": 0.1, "purpose": 0.5},
        "hard_constraints": {
            "min_strength": 60,
            "max_wb": 0.35,
            "min_silica_fume": 0.05
        }
    }
}

# =========================
# HPC-Specific Rules (Pseudocode Implementation)
# =========================
HPC_OPTIONS = {
    "silica_fume": {
        "max_frac": 0.10,
        "water_demand_multiplier": 1.05,
        "sp_effectiveness_boost": 1.2,
        "co2_factor": 0.1,
        "cost_factor": 15.0,
        "density": 2200.0
    }
}

HPC_WB_RANGE = (0.25, 0.40)
HPC_MIN_BINDER_STRENGTH = 60  # MPa
HPC_SP_MAX_LIMIT = 0.03  # 3% of binder content
HPC_MIN_FINES_CONTENT = 400  # kg/m³ for pumpability

# =========================
# IS 10262 – Water Content & Aggregate Shape Adjustments
# =========================
WATER_BASELINE = {10: 208, 12.5: 202, 20: 186, 40: 165}

AGG_SHAPE_WATER_ADJ = {
    "Angular (baseline)": 0.00,
    "Sub-angular": -0.03,
    "Sub-rounded": -0.05,
    "Rounded": -0.07,
    "Flaky/Elongated": +0.03
}

ENTRAPPED_AIR_VOL = {10: 0.02, 12.5: 0.015, 20: 0.01, 40: 0.008}

# Binder ranges expanded for HPC grades
BINDER_RANGES = {
    "M10": (220, 320), "M15": (250, 350), "M20": (300, 400),
    "M25": (320, 420), "M30": (340, 450), "M35": (360, 480),
    "M40": (380, 500), "M45": (400, 520), "M50": (420, 540),
    "M60": (460, 700), "M70": (500, 760), "M80": (540, 820),
    "M90": (580, 880), "M100": (620, 940)
}

# Coarse aggregate fraction by zone (IS 10262 Table 5)
COARSE_AGG_FRAC_BY_ZONE = {
    10: {"Zone I": 0.50, "Zone II": 0.48, "Zone III": 0.46, "Zone IV": 0.44},
    12.5: {"Zone I": 0.59, "Zone II": 0.57, "Zone III": 0.55, "Zone IV": 0.53},
    20: {"Zone I": 0.66, "Zone II": 0.64, "Zone III": 0.62, "Zone IV": 0.60},
    40: {"Zone I": 0.71, "Zone II": 0.69, "Zone III": 0.67, "Zone IV": 0.65}
}

# Quality Control Standard Deviation (IS 10262)
QC_STDDEV = {"Good": 5.0, "Fair": 7.5, "Poor": 10.0}

def water_for_slump_and_shape(nom_max_mm: int, slump_mm: int, agg_shape: str, uses_sp: bool=False, sp_reduction_frac: float=0.0) -> float:
    """
    Estimate mixing water for given slump & aggregate size (IS 10262 style).
    Enhanced with aggregate shape adjustments and HPC considerations.
    """
    base = WATER_BASELINE.get(int(nom_max_mm), 186.0)
    
    # Slump adjustment
    if slump_mm <= 50:
        water = base
    else:
        extra_25 = max(0, (slump_mm - 50) / 25.0)
        water = base * (1 + 0.03 * extra_25)  # +3% per 25 mm increment
    
    # Aggregate shape adjustment
    shape_factor = AGG_SHAPE_WATER_ADJ.get(agg_shape, 0.0)
    water *= (1.0 + shape_factor)
    
    # Superplasticizer reduction
    if uses_sp and sp_reduction_frac > 0:
        water *= (1 - sp_reduction_frac)
    
    return float(water)

def aggregate_correction(delta_moisture_pct: float, agg_mass_ssd: float):
    """
    Adjust aggregate batch mass for field moisture deviation.
    Returns: (free_water_contribution, corrected_mass).
    """
    water_delta = (delta_moisture_pct / 100.0) * agg_mass_ssd
    corrected_mass = agg_mass_ssd * (1 + delta_moisture_pct / 100.0)
    return float(water_delta), float(corrected_mass)

def get_coarse_agg_fraction(nom_max_mm: float, fa_zone: str, wb_ratio: float) -> float:
    """
    Get coarse aggregate fraction based on nominal max size, fine aggregate zone, and w/b ratio.
    Includes w/b ratio correction as per IS 10262 guidelines.
    """
    base_fraction = COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)
    
    # Correction for w/b ratio (IS 10262 adjustment)
    correction = ((0.50 - wb_ratio) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    
    # Ensure reasonable limits
    return max(0.4, min(0.8, corrected_fraction))

def reasonable_binder_range(grade: str):
    """Get reasonable binder range for a given grade."""
    return BINDER_RANGES.get(grade, (300, 500))

# =========================
# IS 383 – Sieve Limits (Enhanced for multiple aggregate sizes)
# =========================
FINE_AGG_ZONE_LIMITS = {
    "Zone I":  {"10.0": (100,100),"4.75": (90,100),"2.36": (60,95),"1.18": (30,70),"0.600": (15,34),"0.300": (5,20),"0.150": (0,10)},
    "Zone II": {"10.0": (100,100),"4.75": (90,100),"2.36": (75,100),"1.18": (55,90),"0.600": (35,59),"0.300": (8,30),"0.150": (0,10)},
    "Zone III":{"10.0": (100,100),"4.75": (90,100),"2.36": (85,100),"1.18": (75,100),"0.600": (60,79),"0.300": (12,40),"0.150": (0,10)},
    "Zone IV": {"10.0": (95,100),"4.75": (95,100),"2.36": (95,100),"1.18": (90,100),"0.600": (80,100),"0.300": (15,50),"0.150": (0,15)},
}

COARSE_LIMITS = {
    10: {"20.0": (100,100), "10.0": (85,100),    "4.75": (0,20)},
    20: {"40.0": (95,100), "20.0": (95,100), "10.0": (25,55), "4.75": (0,10)},
    40: {"80.0": (95,100), "40.0": (95,100), "20.0": (30,70), "10.0": (0,15)}
}

def sieve_check_fa(df: pd.DataFrame, zone: str):
    """
    Verify fine aggregate sieve analysis against IS 383 limits.
    """
    limits = FINE_AGG_ZONE_LIMITS[zone]
    ok = True
    msgs = []
    for sieve, (lo, hi) in limits.items():
        row = df.loc[df["Sieve_mm"].astype(str) == sieve]
        if row.empty:
            msgs.append(f"Missing sieve size: {sieve} mm.")
            ok = False
            continue
        p = float(row["PercentPassing"].iloc[0])
        if not (lo <= p <= hi):
            ok = False
            msgs.append(f"Sieve {sieve} mm: {p:.1f}% passing is outside {lo}-{hi}%.")
    if ok and not msgs:
        msgs = [f"Fine aggregate conforms to IS 383 for {zone}."]
    return ok, msgs

def sieve_check_ca(df: pd.DataFrame, nominal_mm: int):
    """
    Verify coarse aggregate sieve analysis against IS 383 limits for given nominal size.
    Enhanced to handle multiple aggregate sizes.
    """
    limits = COARSE_LIMITS.get(int(nominal_mm), {})
    if not limits:
        return False, [f"No IS 383 limits defined for {nominal_mm} mm aggregate."]
    
    ok = True
    msgs = []
    for sieve, (lo, hi) in limits.items():
        row = df.loc[df["Sieve_mm"].astype(str) == sieve]
        if row.empty:
            msgs.append(f"Missing sieve size: {sieve} mm.")
            ok = False
            continue
        p = float(row["PercentPassing"].iloc[0])
        if not (lo <= p <= hi):
            ok = False
            msgs.append(f"Sieve {sieve} mm: {p:.1f}% passing is outside {lo}-{hi}%.")
    if ok and not msgs:
        msgs = [f"Coarse aggregate conforms to IS 383 for {nominal_mm} mm graded aggregate."]
    return ok, msgs

# =========================
# Purpose-Specific Evaluation Functions (Pseudocode Implementation)
# =========================

def evaluate_purpose_specific_metrics(candidate_meta: dict, purpose: str) -> dict:
    """
    Compute approximate metrics needed for purpose evaluation.
    Enhanced with HPC-aware calculations.
    """
    try:
        fck_target = float(candidate_meta.get('fck_target', 30.0))
        wb = float(candidate_meta.get('w_b', 0.5))
        binder = float(candidate_meta.get('cementitious', 350.0))
        water = float(candidate_meta.get('water_target', 180.0))
        sf_frac = float(candidate_meta.get('sf_frac', 0.0))
        
        # Enhanced modulus calculation for HPC
        if sf_frac > 0.05:  # Significant silica fume content
            modulus_proxy = 5500 * np.sqrt(fck_target)  # HPC has higher modulus
        else:
            modulus_proxy = 5000 * np.sqrt(fck_target)
            
        shrinkage_risk_index = (binder * water) / 10000.0
        
        # Enhanced fatigue calculation for pavements
        fatigue_proxy = (1.0 - wb) * (binder / 1000.0)
        if sf_frac > 0.02:  # Silica fume improves fatigue
            fatigue_proxy *= 1.2
            
        # HPC-specific metric
        hpc_strength_index = fck_target / (wb * 100) if wb > 0 else 0
        
        # Flexural strength proxy (for pavements)
        flexural_strength_proxy = 0.7 * np.sqrt(fck_target)
        
        # Early strength proxy (for precast)
        early_strength_proxy = fck_target * 0.4  # 40% at 3 days
        
        return {
            "estimated_modulus_proxy (MPa)": round(modulus_proxy, 0),
            "shrinkage_risk_index": round(shrinkage_risk_index, 2),
            "pavement_fatigue_proxy": round(fatigue_proxy, 2),
            "flexural_strength_proxy (MPa)": round(flexural_strength_proxy, 2),
            "early_strength_proxy (MPa)": round(early_strength_proxy, 2),
            "hpc_strength_efficiency": round(hpc_strength_index, 2) if sf_frac > 0 else None,
        }
    except Exception as e:
        return {"error": f"Purpose metrics calculation failed: {str(e)}"}

def compute_purpose_penalty(candidate_meta: dict, purpose_profile: dict) -> float:
    """
    Evaluate key purpose-related penalties for composite objective function.
    """
    if not purpose_profile:
        return 0.0
    
    penalty = 0.0
    try:
        wb_limit = purpose_profile.get('wb_limit', 1.0)
        current_wb = candidate_meta.get('w_b', 0.5)
        if current_wb > wb_limit:
            penalty += (current_wb - wb_limit) * 1000
            
        scm_limit = purpose_profile.get('scm_limit', 0.5)
        current_scm = candidate_meta.get('scm_total_frac', 0.0)
        if current_scm > scm_limit:
            penalty += (current_scm - scm_limit) * 100
            
        min_binder = purpose_profile.get('min_binder', 0.0)
        current_binder = candidate_meta.get('cementitious', 300.0)
        if current_binder < min_binder:
            penalty += (min_binder - current_binder) * 0.1
            
        # Purpose-specific hard constraints
        hard_constraints = purpose_profile.get('hard_constraints', {})
        
        # Flexural strength constraint for pavements
        if 'min_flexural_strength' in hard_constraints:
            flexural_proxy = 0.7 * np.sqrt(candidate_meta.get('fck_target', 30))
            if flexural_proxy < hard_constraints['min_flexural_strength']:
                penalty += (hard_constraints['min_flexural_strength'] - flexural_proxy) * 50
                
        # Shrinkage risk constraint
        if 'max_shrinkage_risk' in hard_constraints:
            shrinkage_risk = (current_binder * candidate_meta.get('water_target', 180)) / 10000.0
            if shrinkage_risk > hard_constraints['max_shrinkage_risk']:
                penalty += (shrinkage_risk - hard_constraints['max_shrinkage_risk']) * 20
                
        return float(max(0.0, penalty))
        
    except Exception:
        return 0.0

def check_hpc_pumpability(fines_content: float, sp_content: float, binder_content: float) -> tuple:
    """
    Validate HPC mix for pumpability based on fines content and SP dosage.
    """
    min_fines = HPC_MIN_FINES_CONTENT
    max_sp_frac = HPC_SP_MAX_LIMIT
    sp_frac = sp_content / binder_content if binder_content > 0 else 0
    
    fines_ok = fines_content >= min_fines
    sp_ok = sp_frac <= max_sp_frac
    
    return fines_ok and sp_ok, fines_ok, sp_ok

# =========================
# Helper Functions for Vectorized Operations
# =========================

def get_coarse_agg_fraction_vectorized(nom_max_mm: float, fa_zone: str, wb_ratio_series: pd.Series) -> pd.Series:
    """
    Vectorized version of get_coarse_agg_fraction for optimization grid.
    """
    base_fraction = COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)
    correction = ((0.50 - wb_ratio_series) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return corrected_fraction.clip(0.4, 0.8)

def aggregate_correction_vectorized(delta_moisture_pct: float, agg_mass_ssd_series: pd.Series):
    """
    Vectorized version of aggregate_correction.
    """
    water_delta_series = (delta_moisture_pct / 100.0) * agg_mass_ssd_series
    corrected_mass_series = agg_mass_ssd_series * (1 + delta_moisture_pct / 100.0)
    return water_delta_series, corrected_mass_series
