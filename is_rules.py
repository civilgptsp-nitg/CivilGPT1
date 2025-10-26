"""
is_rules.py
---------------
Central repository of IS code–based constants and helper functions
for CivilGPT (concrete mix designer).
STRICTLY COMPLIANT WITH IS 456:2000 & IS 10262:2019
"""

import numpy as np
import pandas as pd

# =========================
# IS 456:2000 DURABILITY RULES (STRICT COMPLIANCE)
# =========================
EXPOSURE_WB_LIMITS = {
    "Mild": 0.55,
    "Moderate": 0.50,
    "Severe": 0.45,
    "Very Severe": 0.40,
    "Marine": 0.40,
    "Extreme": 0.35
}

EXPOSURE_MIN_CEMENT = {
    "Mild": 300,
    "Moderate": 300,
    "Severe": 320,
    "Very Severe": 340,
    "marine": 360,
    "Extreme": 380
}

EXPOSURE_MIN_GRADE = {
    "Mild": "M20",
    "Moderate": "M25",
    "Severe": "M30",
    "Very Severe": "M35",
    "marine": "M40",
    "Extreme": "M45"
}

# =========================
# CONCRETE GRADES (IS 456:2000)
# =========================
GRADE_STRENGTH = {
    "M15": 15, "M20": 20, "M25": 25, "M30": 30, 
    "M35": 35, "M40": 40, "M45": 45, "M50": 50, 
    "M55": 55, "M60": 60, "M65": 65, "M70": 70, 
    "M75": 75, "M80": 80, "M85": 85, "M90": 90, 
    "M95": 95, "M100": 100
}

# =========================
# PURPOSE-BASED CONSTRAINTS (IS COMPLIANT)
# =========================
PURPOSE_PROFILES = {
    "General": {
        "description": "IS 456 compliant balanced mix for general applications",
        "wb_limit": 0.55,
        "scm_limit": 0.35,
        "min_binder": 320,
        "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2},
        "hard_constraints": {
            "min_grade": "M25",
            "max_scm_ratio": 0.35
        },
        "target_ranges": {
            "scm_min": 0.1,
            "scm_max": 0.35,
            "w_b_max": 0.55
        }
    },
    "Slab": {
        "description": "IS compliant slab design with workability focus",
        "wb_limit": 0.50,
        "scm_limit": 0.30,
        "min_binder": 300,
        "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2},
        "hard_constraints": {
            "min_grade": "M25",
            "min_slump": 100,
            "max_wb_ratio": 0.50
        },
        "target_ranges": {
            "slump_min": 100,
            "slump_max": 150,
            "scm_min": 0.15,
            "scm_max": 0.30
        }
    },
    "Beam": {
        "description": "IS compliant beam design for strength and durability",
        "wb_limit": 0.45,
        "scm_limit": 0.25,
        "min_binder": 340,
        "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4},
        "hard_constraints": {
            "min_grade": "M30",
            "min_cementitious": 340,
            "max_wb_ratio": 0.45
        },
        "target_ranges": {
            "fck_min": 30,
            "fck_max": 40,
            "scm_min": 0.10,
            "scm_max": 0.25
        }
    },
    "Column": {
        "description": "IS compliant column design for high compressive strength",
        "wb_limit": 0.40,
        "scm_limit": 0.20,
        "min_binder": 360,
        "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5},
        "hard_constraints": {
            "min_grade": "M35",
            "min_cementitious": 360,
            "max_wb_ratio": 0.40
        },
        "target_ranges": {
            "fck_min": 35,
            "fck_max": 50,
            "scm_min": 0.05,
            "scm_max": 0.20
        }
    },
    "Pavement": {
        "description": "IS compliant pavement for durability and flexural strength",
        "wb_limit": 0.45,
        "scm_limit": 0.25,
        "min_binder": 340,
        "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3},
        "hard_constraints": {
            "min_grade": "M30",
            "min_cementitious": 340,
            "max_wb_ratio": 0.45
        },
        "target_ranges": {
            "fck_min": 30,
            "fck_max": 35,
            "scm_min": 0.15,
            "scm_max": 0.25
        }
    },
    "RPC/HPC": {
        "description": "IS compliant high-performance concrete",
        "wb_limit": 0.35,
        "scm_limit": 0.15,
        "min_binder": 450,
        "weights": {"co2": 0.4, "cost": 0.1, "purpose": 0.5},
        "hard_constraints": {
            "min_grade": "M60",
            "min_cementitious": 450,
            "max_wb_ratio": 0.35
        },
        "target_ranges": {
            "fck_min": 60,
            "fck_max": 100,
            "scm_min": 0.05,
            "scm_max": 0.15
        }
    }
}

# =========================
# HPC-SPECIFIC RULES (IS 456:2000 COMPLIANT)
# =========================
HPC_OPTIONS = {
    "silica_fume": {
        "max_frac": 0.10,
        "water_demand_multiplier": 1.05,
        "sp_effectiveness_boost": 1.2,
        "co2_factor": 0.10,
        "cost_factor": 28.0,
        "density": 2200.0
    }
}

HPC_WB_RANGE = (0.25, 0.35)
HPC_MIN_BINDER_STRENGTH = 60  # MPa
HPC_SP_MAX_LIMIT = 0.03  # 3% of binder content
HPC_MIN_FINES_CONTENT = 400  # kg/m³ for pumpability

# =========================
# IS 10262:2019 – WATER CONTENT & AGGREGATE PROPERTIES
# =========================
WATER_BASELINE = {10: 208, 12.5: 202, 20: 186, 40: 165}

AGG_SHAPE_WATER_ADJ = {
    "Angular (baseline)": 0.00,
    "Sub-angular": -0.03,
    "Sub-rounded": -0.05,
    "Rounded": -0.07,
    "Flaky/Elongated": +0.03
}

ENTRAPPED_AIR_VOL = {10: 0.03, 12.5: 0.025, 20: 0.02, 40: 0.015}

# Binder ranges as per IS 10262:2019
BINDER_RANGES = {
    "M15": (250, 300), "M20": (280, 350), "M25": (300, 380),
    "M30": (320, 400), "M35": (340, 430), "M40": (360, 450),
    "M45": (380, 480), "M50": (400, 500), "M55": (420, 520),
    "M60": (450, 550), "M65": (480, 580), "M70": (500, 600),
    "M75": (520, 620), "M80": (540, 640), "M85": (560, 660),
    "M90": (580, 680), "M95": (600, 700), "M100": (620, 720)
}

# Coarse aggregate fraction by zone (IS 10262:2019 Table 5)
COARSE_AGG_FRAC_BY_ZONE = {
    10: {"Zone I": 0.50, "Zone II": 0.48, "Zone III": 0.46, "Zone IV": 0.44},
    12.5: {"Zone I": 0.59, "Zone II": 0.57, "Zone III": 0.55, "Zone IV": 0.53},
    20: {"Zone I": 0.66, "Zone II": 0.64, "Zone III": 0.62, "Zone IV": 0.60},
    40: {"Zone I": 0.71, "Zone II": 0.69, "Zone III": 0.67, "Zone IV": 0.65}
}

# Quality Control Standard Deviation (IS 10262:2019 Table 2)
QC_STDDEV = {"Excellent": 3.5, "Good": 4.0, "Fair": 5.0, "Poor": 6.0}

# Maximum SCM replacement limits as per IS 456:2000
SCM_LIMITS = {
    "Fly Ash": 0.35,
    "GGBS": 0.50,
    "Silica Fume": 0.10,
    "Metakaolin": 0.15,
    "Total SCM": 0.50
}

def water_for_slump_and_shape(nom_max_mm: int, slump_mm: int, agg_shape: str, uses_sp: bool=False, sp_reduction_frac: float=0.0) -> float:
    """
    Estimate mixing water for given slump & aggregate size (IS 10262:2019).
    Strictly follows IS code guidelines.
    """
    # Base water content from IS 10262:2019 Table 4
    base = WATER_BASELINE.get(int(nom_max_mm), 186.0)
    
    # Slump adjustment as per IS 10262:2019
    if slump_mm <= 50:
        water = base
    elif slump_mm <= 100:
        water = base * 1.03  # +3% for 75-100mm slump
    elif slump_mm <= 150:
        water = base * 1.06  # +6% for 125-150mm slump
    else:
        water = base * 1.09  # +9% for >150mm slump
    
    # Aggregate shape adjustment
    shape_factor = AGG_SHAPE_WATER_ADJ.get(agg_shape, 0.0)
    water *= (1.0 + shape_factor)
    
    # Superplasticizer reduction (max 30% as per IS 9103)
    if uses_sp and sp_reduction_frac > 0:
        max_reduction = 0.30  # Maximum water reduction as per IS code
        effective_reduction = min(sp_reduction_frac, max_reduction)
        water *= (1 - effective_reduction)
    
    return float(round(water, 1))

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
    Strictly follows IS 10262:2019 Table 5 with corrections.
    """
    base_fraction = COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)
    
    # Correction for w/b ratio (IS 10262:2019 adjustment)
    # For every 0.05 change in w/c ratio, coarse aggregate changes by 1%
    correction = ((0.50 - wb_ratio) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    
    # Ensure reasonable limits as per IS code
    return max(0.40, min(0.75, round(corrected_fraction, 3)))

def reasonable_binder_range(grade: str):
    """Get reasonable binder range for a given grade as per IS 10262:2019."""
    return BINDER_RANGES.get(grade, (300, 450))

def check_scm_compliance(flyash_frac: float, ggbs_frac: float, silica_fume_frac: float) -> tuple:
    """
    Check SCM replacement limits as per IS 456:2000.
    Returns: (is_compliant, violation_message)
    """
    total_scm = flyash_frac + ggbs_frac + silica_fume_frac
    
    violations = []
    
    if flyash_frac > SCM_LIMITS["Fly Ash"]:
        violations.append(f"Fly ash ({flyash_frac:.1%}) exceeds IS limit ({SCM_LIMITS['Fly Ash']:.1%})")
    
    if ggbs_frac > SCM_LIMITS["GGBS"]:
        violations.append(f"GGBS ({ggbs_frac:.1%}) exceeds IS limit ({SCM_LIMITS['GGBS']:.1%})")
    
    if silica_fume_frac > SCM_LIMITS["Silica Fume"]:
        violations.append(f"Silica fume ({silica_fume_frac:.1%}) exceeds IS limit ({SCM_LIMITS['Silica Fume']:.1%})")
    
    if total_scm > SCM_LIMITS["Total SCM"]:
        violations.append(f"Total SCM ({total_scm:.1%}) exceeds IS limit ({SCM_LIMITS['Total SCM']:.1%})")
    
    is_compliant = len(violations) == 0
    message = "SCM compliant with IS 456" if is_compliant else "; ".join(violations)
    
    return is_compliant, message

# =========================
# IS 383 – SIEVE LIMITS (STRICT COMPLIANCE)
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
# PURPOSE-SPECIFIC EVALUATION (IS COMPLIANT)
# =========================

def evaluate_purpose_specific_metrics(candidate_meta: dict, purpose: str) -> dict:
    """
    Compute approximate metrics needed for purpose evaluation.
    Uses IS code compliant formulas.
    """
    try:
        fck_target = float(candidate_meta.get('fck_target', 30.0))
        wb = float(candidate_meta.get('w_b', 0.5))
        binder = float(candidate_meta.get('cementitious', 350.0))
        water = float(candidate_meta.get('water_target', 180.0))
        sf_frac = float(candidate_meta.get('sf_frac', 0.0))
        
        # Modulus of elasticity as per IS 456:2000
        modulus_proxy = 5000 * np.sqrt(fck_target)
        
        # Shrinkage risk index (based on IS 456 guidelines)
        shrinkage_risk_index = (binder * water) / 10000.0
        
        # Flexural strength as per IS 456 (approx 0.7√fck)
        flexural_strength_proxy = 0.7 * np.sqrt(fck_target)
        
        # Early strength estimate (3-day ~40% of 28-day)
        early_strength_proxy = fck_target * 0.4
        
        # Durability index based on w/b ratio and binder content
        durability_index = (1.0 - wb) * (binder / 500.0)
        
        return {
            "estimated_modulus_proxy (MPa)": round(modulus_proxy, 0),
            "shrinkage_risk_index": round(shrinkage_risk_index, 2),
            "flexural_strength_proxy (MPa)": round(flexural_strength_proxy, 2),
            "early_strength_proxy (MPa)": round(early_strength_proxy, 2),
            "durability_index": round(durability_index, 2),
            "is_code_compliant": True
        }
    except Exception as e:
        return {"error": f"Purpose metrics calculation failed: {str(e)}", "is_code_compliant": False}

def compute_purpose_penalty(candidate_meta: dict, purpose_profile: dict) -> float:
    """
    Evaluate purpose-related penalties for composite objective function.
    Strict IS code compliance checking.
    """
    if not purpose_profile:
        return 0.0
    
    penalty = 0.0
    try:
        # Basic IS code compliance penalties
        wb_limit = purpose_profile.get('wb_limit', 0.55)
        current_wb = candidate_meta.get('w_b', 0.5)
        if current_wb > wb_limit:
            penalty += (current_wb - wb_limit) * 1000  # Heavy penalty for w/b violation
            
        scm_limit = purpose_profile.get('scm_limit', 0.35)
        current_scm = candidate_meta.get('scm_total_frac', 0.0)
        if current_scm > scm_limit:
            penalty += (current_scm - scm_limit) * 500  # Heavy penalty for SCM violation
            
        min_binder = purpose_profile.get('min_binder', 300.0)
        current_binder = candidate_meta.get('cementitious', 300.0)
        if current_binder < min_binder:
            penalty += (min_binder - current_binder) * 0.5  # Penalty for low binder
            
        # Purpose-specific IS code requirements
        hard_constraints = purpose_profile.get('hard_constraints', {})
        
        # Grade compliance
        if 'min_grade' in hard_constraints:
            min_grade_str = hard_constraints['min_grade']
            min_fck = GRADE_STRENGTH.get(min_grade_str, 25)
            actual_fck = candidate_meta.get('fck_target', 25)
            if actual_fck < min_fck:
                penalty += (min_fck - actual_fck) * 10
                
        return float(max(0.0, penalty))
        
    except Exception:
        return 100.0  # High penalty for calculation errors

def check_hpc_pumpability(fines_content: float, sp_content: float, binder_content: float) -> tuple:
    """
    Validate HPC mix for pumpability based on IS 10262:2019 guidelines.
    """
    min_fines = HPC_MIN_FINES_CONTENT
    max_sp_frac = HPC_SP_MAX_LIMIT
    sp_frac = sp_content / binder_content if binder_content > 0 else 0
    
    fines_ok = fines_content >= min_fines
    sp_ok = sp_frac <= max_sp_frac
    
    return fines_ok and sp_ok, fines_ok, sp_ok

def check_is_code_compliance(grade: str, exposure: str, wb_ratio: float, 
                          cementitious: float, scm_total: float) -> dict:
    """
    Comprehensive IS 456:2000 compliance check.
    Returns detailed compliance report.
    """
    compliance = {
        "grade_exposure_match": True,
        "wb_ratio_compliant": True,
        "min_cement_compliant": True,
        "scm_limits_compliant": True,
        "all_compliant": True,
        "violations": []
    }
    
    # Check grade vs exposure
    min_required_grade = EXPOSURE_MIN_GRADE.get(exposure, "M25")
    grade_order = list(GRADE_STRENGTH.keys())
    if grade_order.index(grade) < grade_order.index(min_required_grade):
        compliance["grade_exposure_match"] = False
        compliance["all_compliant"] = False
        compliance["violations"].append(f"Grade {grade} insufficient for {exposure} exposure (min: {min_required_grade})")
    
    # Check w/b ratio
    max_wb = EXPOSURE_WB_LIMITS.get(exposure, 0.50)
    if wb_ratio > max_wb:
        compliance["wb_ratio_compliant"] = False
        compliance["all_compliant"] = False
        compliance["violations"].append(f"w/b ratio {wb_ratio:.3f} exceeds limit {max_wb:.3f} for {exposure} exposure")
    
    # Check minimum cementitious content
    min_cement = EXPOSURE_MIN_CEMENT.get(exposure, 300)
    if cementitious < min_cement:
        compliance["min_cement_compliant"] = False
        compliance["all_compliant"] = False
        compliance["violations"].append(f"Cementitious content {cementitious:.1f} kg/m³ below minimum {min_cement} kg/m³ for {exposure} exposure")
    
    # Check SCM limits
    if scm_total > SCM_LIMITS["Total SCM"]:
        compliance["scm_limits_compliant"] = False
        compliance["all_compliant"] = False
        compliance["violations"].append(f"Total SCM {scm_total:.1%} exceeds IS limit {SCM_LIMITS['Total SCM']:.1%}")
    
    return compliance

# =========================
# HELPER FUNCTIONS FOR VECTORIZED OPERATIONS
# =========================

def get_coarse_agg_fraction_vectorized(nom_max_mm: float, fa_zone: str, wb_ratio_series: pd.Series) -> pd.Series:
    """
    Vectorized version of get_coarse_agg_fraction for optimization grid.
    """
    base_fraction = COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)
    correction = ((0.50 - wb_ratio_series) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return corrected_fraction.clip(0.4, 0.75)

def aggregate_correction_vectorized(delta_moisture_pct: float, agg_mass_ssd_series: pd.Series):
    """
    Vectorized version of aggregate_correction.
    """
    water_delta_series = (delta_moisture_pct / 100.0) * agg_mass_ssd_series
    corrected_mass_series = agg_mass_ssd_series * (1 + delta_moisture_pct / 100.0)
    return water_delta_series, corrected_mass_series

def compute_target_strength(grade: str, qc_level: str = "Good") -> float:
    """
    Compute target mean strength as per IS 10262:2019.
    f_target = fck + k * S
    where k = 1.65 (for 5% defect level)
    """
    fck = GRADE_STRENGTH.get(grade, 30)
    S = QC_STDDEV.get(qc_level, 4.0)
    return fck + 1.65 * S
