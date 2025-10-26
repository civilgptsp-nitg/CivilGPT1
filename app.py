import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import json
import re
from io import BytesIO
from difflib import get_close_matches
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from functools import lru_cache
from itertools import product
import traceback # Added for cleaner error logging
import uuid # For dynamic key
import time # Added for time.sleep in a non-rerun scenario if needed

# ==============================================================================
# PART 1: CONSTANTS & CORE DATA
# ==============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAB_FILE = "lab_processed_mgrades_only.xlsx"
MIX_FILE = "concrete_mix_design_data_cleaned_standardized.xlsx"

class CONSTANTS:
    # Extended grade mapping (includes HPC grades up to M100)
    GRADE_STRENGTH = {
        "M10": 10, "M15": 15, "M20": 20, "M25": 25, "M30": 30, "M35": 35,
        "M40": 40, "M45": 45, "M50": 50,
        # HPC grades (new)
        "M55": 55, "M60": 60, "M65": 65, "M70": 70, "M75": 75,
        "M80": 80, "M90": 90, "M100": 100
    }
    EXPOSURE_WB_LIMITS = {"Mild": 0.60, "Moderate": 0.55, "Severe": 0.50, "Very Severe": 0.45, "Marine": 0.40}
    EXPOSURE_MIN_CEMENT = {"Mild": 300, "Moderate": 300, "Severe": 320, "Very Severe": 340, "Marine": 360}
    EXPOSURE_MIN_GRADE = {"Mild": "M20", "Moderate": "M25", "Severe": "M30", "Very Severe": "M35", "Marine": "M40"}
    WATER_BASELINE = {10: 208, 12.5: 202, 20: 186, 40: 165}
    AGG_SHAPE_WATER_ADJ = {"Angular (baseline)": 0.00, "Sub-angular": -0.03, "Sub-rounded": -0.05, "Rounded": -0.07, "Flaky/Elongated": +0.03}
    QC_STDDEV = {"Good": 5.0, "Fair": 7.5, "Poor": 10.0}
    ENTRAPPED_AIR_VOL = {10: 0.02, 12.5: 0.015, 20: 0.01, 40: 0.008}
    BINDER_RANGES = {
        "M10": (220, 320), "M15": (250, 350), "M20": (300, 400),
        "M25": (320, 420), "M30": (340, 450), "M35": (360, 480),
        "M40": (380, 500), "M45": (400, 520), "M50": (420, 540),
        # HPC binder ranges (typical guidance — adjust if you want different bounds)
        "M55": (440, 560), "M60": (460, 580), "M65": (480, 600),
        "M70": (500, 620), "M75": (520, 640), "M80": (540, 660),
        "M90": (580, 700), "M100": (620, 750)
    }
    COARSE_AGG_FRAC_BY_ZONE = {
        10: {"Zone I": 0.50, "Zone II": 0.48, "Zone III": 0.46, "Zone IV": 0.44},
        12.5: {"Zone I": 0.59, "Zone II": 0.57, "Zone III": 0.55, "Zone IV": 0.53},
        20: {"Zone I": 0.66, "Zone II": 0.64, "Zone III": 0.62, "Zone IV": 0.60},
        40: {"Zone I": 0.71, "Zone II": 0.69, "Zone III": 0.67, "Zone IV": 0.65}
    }
    FINE_AGG_ZONE_LIMITS = {
        "Zone I":     {"10.0": (100,100),"4.75": (90,100),"2.36": (60,95),"1.18": (30,70),"0.600": (15,34),"0.300": (5,20),"0.150": (0,10)},
        "Zone II":    {"10.0": (100,100),"4.75": (90,100),"2.36": (75,100),"1.18": (55,90),"0.600": (35,59),"0.300": (8,30),"0.150": (0,10)},
        "Zone III": {"10.0": (100,100),"4.75": (90,100),"2.36": (85,100),"1.18": (75,90),"0.600": (60,79),"0.300": (12,40),"0.150": (0,10)},
        "Zone IV":    {"10.0": (95,100),"4.75": (95,100),"2.36": (95,100),"1.18": (90,100),"0.600": (80,100),"0.300": (15,50),"0.150": (0,15)},
    }
    COARSE_LIMITS = {
        10: {"20.0": (100,100), "10.0": (85,100),    "4.75": (0,20)},
        20: {"40.0": (95,100),  "20.0": (95,100),  "10.0": (25,55), "4.75": (0,10)},
        40: {"80.0": (95,100),  "40.0": (95,100),  "20.0": (30,70), "10.0": (0,15)}
    }
    EMISSIONS_COL_MAP = {
        "material": "Material", "co2_factor_kg_co2_per_kg": "CO2_Factor(kg_CO2_per_kg)",
        "co2_factor": "CO2_Factor(kg_CO2_per_kg)", "co2factor": "CO2_Factor(kg_CO2_per_kg)",
        "emission_factor": "CO2_Factor(kg_CO2_per_kg)", "co2factor_kgco2perkg": "CO2_Factor(kg_CO2_per_kg)",
        "co2": "CO2_Factor(kg_CO2_per_kg)"
    }
    COSTS_COL_MAP = {
        "material": "Material", "cost_kg": "Cost(₹/kg)", "cost_rs_kg": "Cost(₹/kg)",
        "cost": "Cost(₹/kg)", "cost_per_kg": "Cost(₹/kg)", "costperkg": "Cost(₹/kg)",
        "price": "Cost(₹/kg)", "kg": "Cost(₹/kg)", "rs_kg": "Cost(₹/kg)",
        "costper": "Cost(₹/kg)", "price_kg": "Cost(₹/kg)", "priceperkg": "Cost(₹/kg)",
    }
    MATERIALS_COL_MAP = {
        "material": "Material", "specificgravity": "SpecificGravity", "specific_gravity": "SpecificGravity",
        "moisturecontent": "MoistureContent", "moisture_content": "MoistureContent",
        "waterabsorption": "WaterAbsorption", "water_absorption": "WaterAbsorption"
    }
    PURPOSE_PROFILES = {
        "General": {"description": "A balanced, default mix. Follows IS code minimums without specific optimization bias.", "wb_limit": 1.0, "scm_limit": 0.5, "min_binder": 0.0, "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2}},
        "Slab": {"description": "Prioritizes workability (slump) and cost-effectiveness. Strength is often not the primary driver.", "wb_limit": 0.55, "scm_limit": 0.5, "min_binder": 300, "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2}},
        "Beam": {"description": "Prioritizes strength (modulus) and durability. Often heavily reinforced.", "wb_limit": 0.50, "scm_limit": 0.4, "min_binder": 320, "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4}},
        "Column": {"description": "Prioritizes high compressive strength and durability. Congestion is common.", "wb_limit": 0.45, "scm_limit": 0.35, "min_binder": 340, "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5}},
        "Pavement": {"description": "Prioritizes durability, flexural strength (fatigue), and abrasion resistance. Cost is a major factor.", "wb_limit": 0.45, "scm_limit": 0.4, "min_binder": 340, "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3}},
        "Precast": {"description": "Prioritizes high early strength (for form stripping), surface finish, and cost (reproducibility).", "wb_limit": 0.45, "scm_limit": 0.3, "min_binder": 360, "weights": {"co2": 0.2, "cost": 0.5, "purpose": 0.3}}
    }
    CEMENT_TYPES = ["OPC 33", "OPC 43", "OPC 53", "PPC"]
    
    # Normalized names for vectorized computation
    NORM_CEMENT = "cement"
    NORM_FLYASH = "fly ash"
    NORM_GGBS = "ggbs"
    NORM_WATER = "water"
    NORM_SP = "pce superplasticizer"
    NORM_FINE_AGG = "fine aggregate"
    NORM_COARSE_AGG = "coarse aggregate"
    
    # Chat Mode Required Fields
    CHAT_REQUIRED_FIELDS = ["grade", "exposure", "target_slump", "nom_max", "cement_choice"]

    # --- HPC-specific overrides ---
    # If HPC mode is enabled these values will be enforced/used by the generation logic
    HPC_OVERRIDES = {
        "allowed_grades": ["M55","M60","M65","M70","M75","M80","M90","M100"],
        "wb_cap": 0.35,               # enforce w/b <= 0.35
        "force_sp": True,             # force superplasticizer ON
        "max_flyash_frac": 0.40,      # allow higher SCMs for HPC
        "max_ggbs_frac": 0.60,
        "wb_min": 0.30                # lower bound for exploration
    }

# ==============================================================================
# PART 2: CACHED LOADERS & BACKEND LOGIC
# ==============================================================================

# --- LLM Client Initialization (Robust & Failsafe) ---
client = None
try:
    from groq import Groq
    GROQ_API_KEY = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", None)
    
    if GROQ_API_KEY:
        client = Groq(api_key=GROQ_API_KEY)
        st.session_state["llm_enabled"] = True
        st.session_state["llm_init_message"] = ("success", "✅ LLM features enabled via Groq API.")
    else:
        client = None
        st.session_state["llm_enabled"] = False
        st.session_state["llm_init_message"] = ("info", "ℹ️ LLM parser disabled (no API key found). Using regex-based fallback.")
except ImportError:
    client = None
    st.session_state["llm_enabled"] = False
    st.session_state["llm_init_message"] = ("warning", "⚠️ Groq library not found. `pip install groq`. Falling back to regex parser.")
except Exception as e:
    client = None
    st.session_state["llm_enabled"] = False
    st.session_state["llm_init_message"] = ("warning", f"⚠️ LLM initialization failed: {e}. Falling back to regex parser.")

@st.cache_data
def load_default_excel(file_name):
    paths_to_try = [
        os.path.join(SCRIPT_DIR, file_name),
        os.path.join(SCRIPT_DIR, "data", file_name)
    ]
    for p in paths_to_try:
        if os.path.exists(p):
            try: return pd.read_excel(p)
            except Exception:
                try: return pd.read_excel(p, engine="openpyxl")
                except Exception as e:
                    st.warning(f"Failed to read {p}: {e}")
    return None

lab_df = load_default_excel(LAB_FILE)
mix_df = load_default_excel(MIX_FILE)

def _normalize_header(header):
    s = str(header).strip().lower()
    s = re.sub(r'[ \-/\.\(\)]+', '_', s)
    s = re.sub(r'[^a-z0-9_]+', '', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_')

@lru_cache(maxsize=128)
def _normalize_material_value(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().lower()
    s = re.sub(r'\b(\d+mm)\b', r'\1', s)
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().replace('mm', '').strip()
    synonyms = {
        "m sand": CONSTANTS.NORM_FINE_AGG, "msand": CONSTANTS.NORM_FINE_AGG, "m-sand": CONSTANTS.NORM_FINE_AGG,
        "fine aggregate": CONSTANTS.NORM_FINE_AGG, "sand": CONSTANTS.NORM_FINE_AGG,
        "20 coarse aggregate": CONSTANTS.NORM_COARSE_AGG, "20mm coarse aggregate": CONSTANTS.NORM_COARSE_AGG,
        "20 coarse": CONSTANTS.NORM_COARSE_AGG, "20": CONSTANTS.NORM_COARSE_AGG, "coarse aggregate": CONSTANTS.NORM_COARSE_AGG,
        "20mm": CONSTANTS.NORM_COARSE_AGG, "pce superplasticizer": CONSTANTS.NORM_SP,
        "pce superplasticiser": CONSTANTS.NORM_SP, "pce": CONSTANTS.NORM_SP,
        "opc 33": "opc 33", "opc 43": "opc 43", "opc 53": "opc 53", "ppc": "ppc",
        "fly ash": CONSTANTS.NORM_FLYASH, "ggbs": CONSTANTS.NORM_GGBS, "water": CONSTANTS.NORM_WATER,
    }
    if s in synonyms: return synonyms[s]
    cand = get_close_matches(s, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    key2 = re.sub(r'^\d+\s*', '', s)
    cand = get_close_matches(key2, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    
    if s.startswith("opc"): return s # Handle cement types not explicitly in synonyms
    
    return s

def _normalize_columns(df, column_map):
    canonical_cols = list(dict.fromkeys(column_map.values()))
    if df is None or df.empty:
        return pd.DataFrame(columns=canonical_cols)
    df = df.copy()
    norm_cols = {}
    for col in df.columns:
        norm_col = _normalize_header(col)
        if norm_col not in norm_cols:
            norm_cols[norm_col] = col
    rename_dict = {}
    for variant, canonical in column_map.items():
        if variant in norm_cols:
            original_col_name = norm_cols[variant]
            if canonical not in rename_dict.values():
                rename_dict[original_col_name] = canonical
    df = df.rename(columns=rename_dict)
    found_canonical = [col for col in canonical_cols if col in df.columns]
    return df[found_canonical]

def _minmax_scale(series: pd.Series) -> pd.Series:
    min_val, max_val = series.min(), series.max()
    if pd.isna(min_val) or pd.isna(max_val) or (max_val - min_val) == 0:
        return pd.Series(0.0, index=series.index, dtype=float)
    return (series - min_val) / (max_val - min_val)

@st.cache_data
def load_purpose_profiles(filepath=None):
    return CONSTANTS.PURPOSE_PROFILES

def evaluate_purpose_specific_metrics(candidate_meta: dict, purpose: str) -> dict:
    try:
        fck_target = float(candidate_meta.get('fck_target', 30.0))
        wb = float(candidate_meta.get('w_b', 0.5))
        binder = float(candidate_meta.get('cementitious', 350.0))
        water = float(candidate_meta.get('water_target', 180.0))
        modulus_proxy = 5000 * np.sqrt(fck_target)
        shrinkage_risk_index = (binder * water) / 10000.0
        fatigue_proxy = (1.0 - wb) * (binder / 1000.0)
        return {
            "estimated_modulus_proxy (MPa)": round(modulus_proxy, 0),
            "shrinkage_risk_index": round(shrinkage_risk_index, 2),
            "pavement_fatigue_proxy": round(fatigue_proxy, 2)
        }
    except Exception:
        return {"estimated_modulus_proxy (MPa)": None, "shrinkage_risk_index": None, "pavement_fatigue_proxy": None}

def compute_purpose_penalty(candidate_meta: dict, purpose_profile: dict) -> float:
    if not purpose_profile: return 0.0
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
        return float(max(0.0, penalty))
    except Exception:
        return 0.0

@st.cache_data
def compute_purpose_penalty_vectorized(df: pd.DataFrame, purpose_profile: dict) -> pd.Series:
    """Vectorized version of compute_purpose_penalty for the optimization grid."""
    if not purpose_profile:
        return pd.Series(0.0, index=df.index)
    
    penalty = pd.Series(0.0, index=df.index)
    
    wb_limit = purpose_profile.get('wb_limit', 1.0)
    penalty += (df['w_b'] - wb_limit).clip(lower=0) * 1000
    
    scm_limit = purpose_profile.get('scm_limit', 0.5)
    penalty += (df['scm_total_frac'] - scm_limit).clip(lower=0) * 100
    
    min_binder = purpose_profile.get('min_binder', 0.0)
    penalty += (min_binder - df['binder']).clip(lower=0) * 0.1
    
    return penalty.fillna(0.0)

@st.cache_data
def load_data(materials_file=None, emissions_file=None, cost_file=None):
    def _safe_read(file, default):
        if file is not None:
            try:
                if hasattr(file, 'seek'): file.seek(0)
                # Attempt to read as CSV (assuming user uploaded CSV per design)
                return pd.read_csv(file)
            except Exception as e:
                st.warning(f"Could not read uploaded file {file.name}: {e}")
                return default
        return default
    
    def _load_fallback(default_names):
        paths_to_try = [os.path.join(SCRIPT_DIR, name) for name in default_names]
        for p in paths_to_try:
            if os.path.exists(p):
                try: return pd.read_csv(p)
                except Exception as e: st.warning(f"Could not read {p}: {e}")
        return None

    # Use uploaded files or fallbacks
    materials = _safe_read(materials_file, _load_fallback(["materials_library.csv", "data/materials_library.csv"]))
    emissions = _safe_read(emissions_file, _load_fallback(["emission_factors.csv", "data/emission_factors.csv"]))
    costs = _safe_read(cost_file, _load_fallback(["cost_factors.csv", "data/cost_factors.csv"]))

    materials = _normalize_columns(materials, CONSTANTS.MATERIALS_COL_MAP)
    if "Material" in materials.columns:
        materials["Material"] = materials["Material"].astype(str).str.strip()
    if materials.empty or "Material" not in materials.columns:
        st.warning("Could not load 'materials_library.csv'. Using empty library.", icon="ℹ️")
        materials = pd.DataFrame(columns=list(dict.fromkeys(CONSTANTS.MATERIALS_COL_MAP.values())))

    emissions = _normalize_columns(emissions, CONSTANTS.EMISSIONS_COL_MAP)
    if "Material" in emissions.columns:
        emissions["Material"] = emissions["Material"].astype(str).str.strip()
    if emissions.empty or "Material" not in emissions.columns or "CO2_Factor(kg_CO2_per_kg)" not in emissions.columns:
        st.warning("⚠️ Could not load 'emission_factors.csv'. CO2 calculations will be zero.")
        emissions = pd.DataFrame(columns=list(dict.fromkeys(CONSTANTS.EMISSIONS_COL_MAP.values())))
        	
    costs = _normalize_columns(costs, CONSTANTS.COSTS_COL_MAP)
    if "Material" in costs.columns:
        costs["Material"] = costs["Material"].astype(str).str.strip()
    if costs.empty or "Material" not in costs.columns or "Cost(₹/kg)" not in costs.columns:
        st.warning("⚠️ Could not load 'cost_factors.csv'. Cost calculations will be zero.")
        costs = pd.DataFrame(columns=list(dict.fromkeys(CONSTANTS.COSTS_COL_MAP.values())))

    return materials, emissions, costs

def _merge_and_warn(main_df: pd.DataFrame, factor_df: pd.DataFrame, factor_col: str, warning_session_key: str, warning_prefix: str) -> pd.DataFrame:
    """Helper to merge factor dataframes and issue warnings for missing values."""
    if factor_df is not None and not factor_df.empty and factor_col in factor_df.columns:
        factor_df_norm = factor_df.copy()
        factor_df_norm['Material'] = factor_df_norm['Material'].astype(str)
        factor_df_norm["Material_norm"] = factor_df_norm["Material"].apply(_normalize_material_value)
        factor_df_norm = factor_df_norm.drop_duplicates(subset=["Material_norm"])
        
        merged_df = main_df.merge(factor_df_norm[["Material_norm", factor_col]], on="Material_norm", how="left")
        
        missing_rows = merged_df[merged_df[factor_col].isna()]
        missing_items = [m for m in missing_rows["Material"].tolist() if m and str(m).strip()]
        
        if missing_items:
            if warning_session_key not in st.session_state:  
                st.session_state[warning_session_key] = set()
            new_missing = set(missing_items) - st.session_state[warning_session_key]
            if new_missing:
                # IMPORTANT: Since this function can run many times, we only warn once per session/material
                # st.warning(f"{warning_prefix}: {', '.join(list(new_missing))}. Value will be 0 for these.", icon="⚠️")
                st.session_state[warning_session_key].update(new_missing)
        
        merged_df[factor_col] = merged_df[factor_col].fillna(0.0)
        return merged_df
    else:
        main_df[factor_col] = 0.0
        return main_df

def pareto_front(df, x_col="cost", y_col="co2"):
    if df.empty: return pd.DataFrame(columns=df.columns)
    sorted_df = df.sort_values(by=[x_col, y_col], ascending=[True, True])
    pareto_points = []
    last_y = float('inf')
    for _, row in sorted_df.iterrows():
        if row[y_col] < last_y:
            pareto_points.append(row)
            last_y = row[y_col]
    if not pareto_points: return pd.DataFrame(columns=df.columns)
    return pd.DataFrame(pareto_points).reset_index(drop=True)

@st.cache_data
def water_for_slump_and_shape(nom_max_mm: int, slump_mm: int, agg_shape: str, uses_sp: bool=False, sp_reduction_frac: float=0.0) -> float:
    base = CONSTANTS.WATER_BASELINE.get(int(nom_max_mm), 186.0)
    water = base if slump_mm <= 50 else base * (1 + 0.03 * ((slump_mm - 50) / 25.0))
    water *= (1.0 + CONSTANTS.AGG_SHAPE_WATER_ADJ.get(agg_shape, 0.0))
    if uses_sp and sp_reduction_frac > 0: water *= (1 - sp_reduction_frac)
    return float(water)

def reasonable_binder_range(grade: str):
    return CONSTANTS.BINDER_RANGES.get(grade, (300, 500))

@st.cache_data
def _get_coarse_agg_fraction_base(nom_max_mm: float, fa_zone: str) -> float:
    """Helper to get the scalar base fraction."""
    return CONSTANTS.COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)

@st.cache_data
def get_coarse_agg_fraction(nom_max_mm: float, fa_zone: str, wb_ratio: float) -> float:
    """Scalar version for baseline calculation."""
    base_fraction = _get_coarse_agg_fraction_base(nom_max_mm, fa_zone)
    correction = ((0.50 - wb_ratio) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return max(0.4, min(0.8, corrected_fraction))

@st.cache_data
def get_coarse_agg_fraction_vectorized(nom_max_mm: float, fa_zone: str, wb_ratio_series: pd.Series) -> pd.Series:
    """Vectorized version for optimization grid."""
    base_fraction = _get_coarse_agg_fraction_base(nom_max_mm, fa_zone)
    correction = ((0.50 - wb_ratio_series) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return corrected_fraction.clip(0.4, 0.8)

@st.cache_data
def run_lab_calibration(lab_df):
    results = []
    std_dev_S = CONSTANTS.QC_STDDEV["Good"]
    for _, row in lab_df.iterrows():
        try:
            grade = str(row['grade']).strip()
            actual_strength = float(row['actual_strength'])
            if grade not in CONSTANTS.GRADE_STRENGTH: continue
            fck = CONSTANTS.GRADE_STRENGTH[grade]
            predicted_strength = fck + 1.65 * std_dev_S
            results.append({
                "Grade": grade, "Exposure": row.get('exposure', 'N/A'),
                "Slump (mm)": row.get('slump', 'N/A'),
                "Lab Strength (MPa)": actual_strength,
                "Predicted Target Strength (MPa)": predicted_strength,
                "Error (MPa)": predicted_strength - actual_strength
            })
        except (KeyError, ValueError, TypeError): pass
    if not results: return None, {}
    results_df = pd.DataFrame(results)
    mae = results_df["Error (MPa)"].abs().mean()
    rmse = np.sqrt((results_df["Error (MPa)"].clip(lower=0) ** 2).mean()) # Cliped lower to 0 for robustness
    bias = results_df["Error (MPa)"].mean()
    metrics = {"Mean Absolute Error (MPa)": mae, "Root Mean Squared Error (MPa)": rmse, "Mean Bias (MPa)": bias}
    return results_df, metrics

@st.cache_data
def simple_parse(text: str) -> dict:
    """Regex-based fallback parser."""
    result = {}
    grade_match = re.search(r"\bM\s*(10|15|20|25|30|35|40|45|50)\b", text, re.IGNORECASE)
    if grade_match: result["grade"] = "M" + grade_match.group(1)
    
    if re.search("Marine", text, re.IGNORECASE):
        result["exposure"] = "Marine"
    else:
        for exp in CONSTANTS.EXPOSURE_WB_LIMITS.keys():
            if exp != "Marine" and re.search(exp, text, re.IGNORECASE):
                result["exposure"] = exp
                break
            
    slump_match = re.search(r"(\d{2,3})\s*mm\s*(?:slump)?", text, re.IGNORECASE)
    if not slump_match:
        slump_match = re.search(r"slump\s*(?:of\s*)?(\d{2,3})\s*mm", text, re.IGNORECASE)
    if slump_match:
        result["target_slump"] = int(slump_match.group(1))
        
    for ctype in CONSTANTS.CEMENT_TYPES:
        if re.search(ctype.replace(" ", r"\s*"), text, re.IGNORECASE):
            result["cement_choice"] = ctype; break
            
    nom_match = re.search(r"(\d{2}(\.5)?)\s*mm\s*(?:agg|aggregate)?", text, re.IGNORECASE)
    if nom_match:
        try:
            val = float(nom_match.group(1))
            if val in [10, 12.5, 20, 40]:
                result["nom_max"] = val
        except: pass
        
    for purp in CONSTANTS.PURPOSE_PROFILES.keys():
        if re.search(purp, text, re.IGNORECASE):
            result["purpose"] = purp; break

    return result

@st.cache_data(show_spinner="🤖 Parsing prompt with LLM...")
def parse_user_prompt_llm(prompt_text: str) -> dict:
    """
    Sends user prompt to LLM and returns structured parameter JSON.
    Must gracefully handle parsing errors or malformed responses.
    """
    if not st.session_state.get("llm_enabled", False) or client is None:
        return simple_parse(prompt_text)

    system_prompt = f"""
    You are an expert civil engineer. Extract concrete mix design parameters from the user's prompt.
    Return ONLY a valid JSON object. Do not include any other text or explanations.
    If a value is not found, omit the key.

    Valid keys and values:
    - "grade": (String) Must be one of {list(CONSTANTS.GRADE_STRENGTH.keys())}
    - "exposure": (String) Must be one of {list(CONSTANTS.EXPOSURE_WB_LIMITS.keys())}. "Marine" takes precedence over "Severe".
    - "cement_type": (String) Must be one of {CONSTANTS.CEMENT_TYPES}
    - "target_slump": (Integer) Slump in mm (e.g., 100, 125).
    - "nom_max": (Float or Integer) Must be one of [10, 12.5, 20, 40]
    - "purpose": (String) Must be one of {list(CONSTANTS.PURPOSE_PROFILES.keys())}
    - "optimize_for": (String) Must be "CO2" or "Cost".
    - "use_superplasticizer": (Boolean)

    User Prompt: "I need M30 for severe marine exposure, 20mm agg, 100 slump, use PPC for a column"
    JSON: {{"grade": "M30", "exposure": "Marine", "nom_max": 20, "target_slump": 100, "cement_type": "PPC", "purpose": "Column"}}
    """
    
    try:
        resp = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        parsed_json = json.loads(content)
        
        cleaned_data = {}
        if parsed_json.get("grade") in CONSTANTS.GRADE_STRENGTH:
            cleaned_data["grade"] = parsed_json["grade"]
        if parsed_json.get("exposure") in CONSTANTS.EXPOSURE_WB_LIMITS:
            cleaned_data["exposure"] = parsed_json["exposure"]
        if parsed_json.get("cement_type") in CONSTANTS.CEMENT_TYPES:
            cleaned_data["cement_choice"] = parsed_json["cement_type"] # Key rename
        if parsed_json.get("nom_max") in [10, 12.5, 20, 40]:
            cleaned_data["nom_max"] = float(parsed_json["nom_max"])
        if isinstance(parsed_json.get("target_slump"), int):
            cleaned_data["target_slump"] = max(25, min(180, parsed_json["target_slump"]))
        if parsed_json.get("purpose") in CONSTANTS.PURPOSE_PROFILES:
            cleaned_data["purpose"] = parsed_json["purpose"]
        if parsed_json.get("optimize_for") in ["CO2", "Cost"]:
            cleaned_data["optimize_for"] = parsed_json["optimize_for"]
        if isinstance(parsed_json.get("use_superplasticizer"), bool):
            cleaned_data["use_sp"] = parsed_json["use_superplasticizer"]
        
        return cleaned_data
    except Exception as e:
        st.error(f"LLM Parser Error: {e}. Falling back to regex.")
        return simple_parse(prompt_text)

# ==============================================================================
# PART 3: CORE MIX GENERATION & EVALUATION
# ==============================================================================

def evaluate_mix(components_dict, emissions_df, costs_df=None):
    comp_items = [(m.strip(), q) for m, q in components_dict.items() if q > 0.01]
    comp_df = pd.DataFrame(comp_items, columns=["Material", "Quantity (kg/m3)"])
    comp_df["Material_norm"] = comp_df["Material"].apply(_normalize_material_value)
    
    # Refactored: Use helper to merge emissions
    df = _merge_and_warn(
        comp_df, emissions_df, "CO2_Factor(kg_CO2_per_kg)",
        "warned_emissions", "No emission factors found for"
    )
    df["CO2_Emissions (kg/m3)"] = df["Quantity (kg/m3)"] * df["CO2_Factor(kg_CO2_per_kg)"]

    # Refactored: Use helper to merge costs
    df = _merge_and_warn(
        df, costs_df, "Cost(₹/kg)",
        "warned_costs", "No cost factors found for"
    )
    df["Cost (₹/m3)"] = df["Quantity (kg/m3)"] * df["Cost(₹/kg)"]
    
    df["Material"] = df["Material"].str.title()
    for col in ["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]:
        if col not in df.columns:
            df[col] = 0.0 if "kg" in col or "m3" in col else ""
            
    return df[["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]]

def aggregate_correction(delta_moisture_pct: float, agg_mass_ssd: float):
    water_delta = (delta_moisture_pct / 100.0) * agg_mass_ssd
    corrected_mass = agg_mass_ssd * (1 + delta_moisture_pct / 100.0)
    return float(water_delta), float(corrected_mass)

def aggregate_correction_vectorized(delta_moisture_pct: float, agg_mass_ssd_series: pd.Series):
    """Vectorized version of aggregate_correction."""
    water_delta_series = (delta_moisture_pct / 100.0) * agg_mass_ssd_series
    corrected_mass_series = agg_mass_ssd_series * (1 + delta_moisture_pct / 100.0)
    return water_delta_series, corrected_mass_series

def compute_aggregates(cementitious, water, sp, coarse_agg_fraction, nom_max_mm, density_fa=2650.0, density_ca=2700.0):
    vol_cem = cementitious / 3150.0
    vol_wat = water / 1000.0
    vol_sp  = sp / 1200.0
    vol_air = CONSTANTS.ENTRAPPED_AIR_VOL.get(int(nom_max_mm), 0.01)
    vol_paste_and_air = vol_cem + vol_wat + vol_sp + vol_air
    vol_agg = 1.0 - vol_paste_and_air
    if vol_agg <= 0: vol_agg = 0.60
    vol_coarse = vol_agg * coarse_agg_fraction
    vol_fine = vol_agg * (1.0 - coarse_agg_fraction)
    mass_fine_ssd = vol_fine * density_fa
    mass_coarse_ssd = vol_coarse * density_ca
    return float(mass_fine_ssd), float(mass_coarse_ssd)

def compute_aggregates_vectorized(binder_series, water_scalar, sp_series, coarse_agg_frac_series, nom_max_mm, density_fa, density_ca):
    """Vectorized version of compute_aggregates."""
    vol_cem = binder_series / 3150.0
    vol_wat = water_scalar / 1000.0
    vol_sp = sp_series / 1200.0
    vol_air = CONSTANTS.ENTRAPPED_AIR_VOL.get(int(nom_max_mm), 0.01)
    
    vol_paste_and_air = vol_cem + vol_wat + vol_sp + vol_air
    vol_agg = (1.0 - vol_paste_and_air).clip(lower=0.60)
    
    vol_coarse = vol_agg * coarse_agg_frac_series
    vol_fine = vol_agg * (1.0 - coarse_agg_frac_series)
    
    mass_fine_ssd = vol_fine * density_fa
    mass_coarse_ssd = vol_coarse * density_ca
    
    return mass_fine_ssd, mass_coarse_ssd

def compliance_checks(mix_df, meta, exposure):
    checks = {}
    try: checks["W/B ≤ exposure limit"] = float(meta["w_b"]) <= CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    except: checks["W/B ≤ exposure limit"] = False
    try: checks["Min cementitious met"] = float(meta["cementitious"]) >= float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    except: checks["Min cementitious met"] = False
    try: checks["SCM ≤ 50%"] = float(meta.get("scm_total_frac", 0.0)) <= 0.50
    except: checks["SCM ≤ 50%"] = False
    try:
        total_mass = float(mix_df["Quantity (kg/m3)"].sum())
        checks["Unit weight 2200–2600 kg/m³"] = 2200.0 <= total_mass <= 2600.0
    except: checks["Unit weight 2200–2600 kg/m³"] = False
    derived = {
        "w/b used": round(float(meta.get("w_b", 0.0)), 3),
        "cementitious (kg/m³)": round(float(meta.get("cementitious", 0.0)), 1),
        "SCM % of cementitious": round(100 * float(meta.get("scm_total_frac", 0.0)), 1),
        "total mass (kg/m³)": round(float(mix_df["Quantity (kg/m3)"].sum()), 1) if "Quantity (kg/m3)" in mix_df.columns else None,
        "water target (kg/m³)": round(float(meta.get("water_target", 0.0)), 1),
        "cement (kg/m³)": round(float(meta.get("cement", 0.0)), 1),
        "fly ash (kg/m³)": round(float(meta.get("flyash", 0.0)), 1),
        "GGBS (kg/m³)": round(float(meta.get("ggbs", 0.0)), 1),
        "fine agg (kg/m³)": round(float(meta.get("fine", 0.0)), 1),
        "coarse agg (kg/m³)": round(float(meta.get("coarse", 0.0)), 1),
        "SP (kg/m³)": round(float(meta.get("sp", 0.0)), 2),
        "fck (MPa)": meta.get("fck"), "fck,target (MPa)": meta.get("fck_target"), "QC (S, MPa)": meta.get("stddev_S"),
    }
    if "purpose" in meta and meta["purpose"] != "General":
        derived.update({
            "purpose": meta["purpose"], "purpose_penalty": meta.get("purpose_penalty"),
            "composite_score": meta.get("composite_score"), "purpose_metrics": meta.get("purpose_metrics")
        })
    return checks, derived

def sanity_check_mix(meta, df):
    warnings = []
    try:
        cement, water, fine = float(meta.get("cement", 0)), float(meta.get("water_target", 0)), float(meta.get("fine", 0))
        coarse, sp = float(meta.get("coarse", 0)), float(meta.get("sp", 0))
        unit_wt = float(df["Quantity (kg/m3)"].sum())
    except Exception: return ["Insufficient data to run sanity checks."]
    if cement > 500: warnings.append(f"High cement content ({cement:.1f} kg/m³). Increases cost, shrinkage, and CO₂.")
    if not 140 <= water <= 220: warnings.append(f"Water content ({water:.1f} kg/m³) is outside the typical range of 140-220 kg/m³.")
    if not 500 <= fine <= 900: warnings.append(f"Fine aggregate quantity ({fine:.1f} kg/m³) is unusual.")
    if not 1000 <= coarse <= 1300: warnings.append(f"Coarse aggregate quantity ({coarse:.1f} kg/m³) is unusual.")
    if sp > 20: warnings.append(f"Superplasticizer dosage ({sp:.1f} kg/m³) is unusually high.")
    return warnings

def check_feasibility(mix_df, meta, exposure):
    checks, derived = compliance_checks(mix_df, meta, exposure)
    warnings = sanity_check_mix(meta, mix_df)
    reasons_fail = [f"IS Code Fail: {k}" for k, v in checks.items() if not v]
    feasible = len(reasons_fail) == 0
    return feasible, reasons_fail, warnings, derived, checks

def get_compliance_reasons(mix_df, meta, exposure):
    reasons = []
    try:
        limit, used = CONSTANTS.EXPOSURE_WB_LIMITS[exposure], float(meta["w_b"])
        if used > limit: reasons.append(f"Failed W/B ratio limit ({used:.3f} > {limit:.2f})")
    except: reasons.append("Failed W/B ratio check (parsing error)")
    try:
        limit, used = float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure]), float(meta["cementitious"])
        if used < limit: reasons.append(f"Cementitious below minimum ({used:.1f} kg/m³ < {limit:.1f} kg/m³)")
    except: reasons.append("Failed min. cementitious check (parsing error)")
    try:
        limit, used = 0.50, float(meta.get("scm_total_frac", 0.0))
        if used > limit: reasons.append(f"SCM fraction exceeds limit ({used*100:.0f}% > {limit*100:.0f}%)")
    except: reasons.append("Failed SCM fraction check (parsing error)")
    try:
        min_limit, max_limit = 2200.0, 2600.0
        total_mass = float(mix_df["Quantity (kg/m3)"].sum())
        if not (min_limit <= total_mass <= max_limit):
            reasons.append(f"Unit weight outside range ({total_mass:.1f} kg/m³ not in {min_limit:.0f}-{max_limit:.0f} kg/m³)")
    except: reasons.append("Failed unit weight check (parsing error)")
    feasible = len(reasons) == 0
    return feasible, "All IS-code checks passed." if feasible else "; ".join(reasons)

def get_compliance_reasons_vectorized(df: pd.DataFrame, exposure: str) -> pd.Series:
    """Vectorized version of get_compliance_reasons for the optimization grid."""
    limit_wb = CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    limit_cem = CONSTANTS.EXPOSURE_MIN_CEMENT[exposure]
    
    reasons = pd.Series("", index=df.index, dtype=str)
    
    reasons += np.where(
        df['w_b'] > limit_wb,
        "Failed W/B ratio (" + df['w_b'].round(3).astype(str) + " > " + str(limit_wb) + "); ",
        ""
    )
    reasons += np.where(
        df['binder'] < limit_cem,
        "Cementitious below minimum (" + df['binder'].round(1).astype(str) + " < " + str(limit_cem) + "); ",
        ""
    )
    reasons += np.where(
        df['scm_total_frac'] > 0.50,
        "SCM fraction exceeds limit (" + (df['scm_total_frac'] * 100).round(0).astype(str) + "% > 50%); ",
        ""
    )
    reasons += np.where(
        ~((df['total_mass'] >= 2200) & (df['total_mass'] <= 2600)),
        "Unit weight outside range (" + df['total_mass'].round(1).astype(str) + " not in 2200-2600); ",
        ""
    )
    
    reasons = reasons.str.strip().str.rstrip(';')
    reasons = np.where(reasons == "", "All IS-code checks passed.", reasons)
    
    return reasons

@st.cache_data
def sieve_check_fa(df: pd.DataFrame, zone: str):
    try:
        limits, ok, msgs = CONSTANTS.FINE_AGG_ZONE_LIMITS[zone], True, []
        for sieve, (lo, hi) in limits.items():
            row = df.loc[df["Sieve_mm"].astype(str) == sieve]
            if row.empty:
                ok = False; msgs.append(f"Missing sieve size: {sieve} mm."); continue
            p = float(row["PercentPassing"].iloc[0])
            if not (lo <= p <= hi): ok = False; msgs.append(f"Sieve {sieve} mm: {p:.1f}% passing is outside {lo}-{hi}%.")
        if ok: msgs = [f"Fine aggregate conforms to IS 383 for {zone}."]
        return ok, msgs
    except: return False, ["Invalid fine aggregate CSV format. Ensure 'Sieve_mm' and 'PercentPassing' columns exist."]

@st.cache_data
def sieve_check_ca(df: pd.DataFrame, nominal_mm: int):
    try:
        limits, ok, msgs = CONSTANTS.COARSE_LIMITS[int(nominal_mm)], True, []
        for sieve, (lo, hi) in limits.items():
            row = df.loc[df["Sieve_mm"].astype(str) == sieve]
            if row.empty:
                ok = False; msgs.append(f"Missing sieve size: {sieve} mm."); continue
            p = float(row["PercentPassing"].iloc[0])
            if not (lo <= p <= hi): ok = False; msgs.append(f"Sieve {sieve} mm: {p:.1f}% passing is outside {lo}-{hi}%.")
        if ok: msgs = [f"Coarse aggregate conforms to IS 383 for {nominal_mm} mm graded aggregate."]
        return ok, msgs
    except: return False, ["Invalid coarse aggregate CSV format. Ensure 'Sieve_mm' and 'PercentPassing' columns exist."]

@st.cache_data
def _get_material_factors(materials_list, emissions_df, costs_df):
    """
    Pre-computes CO2 and Cost factors for a list of materials to avoid
    merging DataFrames inside a loop.
    Returns two dictionaries: co2_factors_dict, cost_factors_dict
    """
    norm_map = {m: _normalize_material_value(m) for m in materials_list}
    norm_materials = list(set(norm_map.values()))

    co2_factors_dict = {}
    if emissions_df is not None and not emissions_df.empty and "CO2_Factor(kg_CO2_per_kg)" in emissions_df.columns:
        emissions_df_norm = emissions_df.copy()
        emissions_df_norm['Material'] = emissions_df_norm['Material'].astype(str)
        emissions_df_norm["Material_norm"] = emissions_df_norm["Material"].apply(_normalize_material_value)
        emissions_df_norm = emissions_df_norm.drop_duplicates(subset=["Material_norm"]).set_index("Material_norm")
        co2_factors_dict = emissions_df_norm["CO2_Factor(kg_CO2_per_kg)"].to_dict()

    cost_factors_dict = {}
    if costs_df is not None and not costs_df.empty and "Cost(₹/kg)" in costs_df.columns:
        costs_df_norm = costs_df.copy()
        costs_df_norm['Material'] = costs_df_norm['Material'].astype(str)
        costs_df_norm["Material_norm"] = costs_df_norm["Material"].apply(_normalize_material_value)
        costs_df_norm = costs_df_norm.drop_duplicates(subset=["Material_norm"]).set_index("Material_norm")
        cost_factors_dict = costs_df_norm["Cost(₹/kg)"].to_dict()

    final_co2 = {norm: co2_factors_dict.get(norm, 0.0) for norm in norm_materials}
    final_cost = {norm: cost_factors_dict.get(norm, 0.0) for norm in norm_materials}
    
    return final_co2, final_cost

def generate_mix(grade, exposure, nom_max, target_slump, agg_shape, 
                 fine_zone, emissions, costs, cement_choice, material_props, 
                 use_sp=True, sp_reduction=0.18, optimize_cost=False, 
                 wb_min=0.35, wb_steps=6, max_flyash_frac=0.3, max_ggbs_frac=0.5, 
                 scm_step=0.1, fine_fraction_override=None,
                 purpose='General', purpose_profile=None, purpose_weights=None,
                 enable_purpose_optimization=False, st_progress=None):

    # --- 1. Setup Parameters ---
    if st_progress: st_progress.progress(0.0, text="Initializing parameters...")
    
    w_b_limit = float(CONSTANTS.EXPOSURE_WB_LIMITS[exposure])
    min_cem_exp = float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    target_water = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = reasonable_binder_range(grade)
    density_fa, density_ca = material_props['sg_fa'] * 1000, material_props['sg_ca'] * 1000
    
    if 'warned_emissions' in st.session_state: st.session_state.warned_emissions.clear()
    if 'warned_costs' in st.session_state: st.session_state.warned_costs.clear()
                        
    if purpose_profile is None: purpose_profile = CONSTANTS.PURPOSE_PROFILES['General']
    if purpose_weights is None: purpose_weights = CONSTANTS.PURPOSE_PROFILES['General']['weights']

    # --- 2. Pre-compute Cost/CO2 Factors (Vectorization Prep) ---
    if st_progress: st_progress.progress(0.05, text="Pre-computing cost/CO2 factors...")
    
    norm_cement_choice = _normalize_material_value(cement_choice)
    materials_to_calc = [
        norm_cement_choice, CONSTANTS.NORM_FLYASH, CONSTANTS.NORM_GGBS,
        CONSTANTS.NORM_WATER, CONSTANTS.NORM_SP, CONSTANTS.NORM_FINE_AGG,
        CONSTANTS.NORM_COARSE_AGG
    ]
    co2_factors, cost_factors = _get_material_factors(materials_to_calc, emissions, costs)

    # --- 3. Create Parameter Grid ---
    if st_progress: st_progress.progress(0.1, text="Creating optimization grid...")
    
    wb_values = np.linspace(float(wb_min), float(w_b_limit), int(wb_steps))
    flyash_options = np.arange(0.0, max_flyash_frac + 1e-9, scm_step)
    ggbs_options = np.arange(0.0, max_ggbs_frac + 1e-9, scm_step)
    
    grid_params = list(product(wb_values, flyash_options, ggbs_options))
    grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac'])
    
    grid_df = grid_df[grid_df['flyash_frac'] + grid_df['ggbs_frac'] <= 0.50].copy()
    if grid_df.empty:
        return None, None, [] # No feasible SCM combinations

    # --- 4. Vectorized Mix Calculations ---
    if st_progress: st_progress.progress(0.2, text="Calculating binder properties...")
    
    grid_df['binder_for_strength'] = target_water / grid_df['wb_input']
    
    # FIX: Broadcast scalars to array shape to prevent ValueError
    grid_df['binder'] = np.maximum(
        np.maximum(grid_df['binder_for_strength'], min_cem_exp),
        min_b_grade
    )
    grid_df['binder'] = np.minimum(grid_df['binder'], max_b_grade)
    grid_df['w_b'] = target_water / grid_df['binder']
    
    grid_df['scm_total_frac'] = grid_df['flyash_frac'] + grid_df['ggbs_frac']
    grid_df['cement'] = grid_df['binder'] * (1 - grid_df['scm_total_frac'])
    grid_df['flyash'] = grid_df['binder'] * grid_df['flyash_frac']
    grid_df['ggbs'] = grid_df['binder'] * grid_df['ggbs_frac']
    grid_df['sp'] = (0.01 * grid_df['binder']) if use_sp else 0.0
    
    if st_progress: st_progress.progress(0.3, text="Calculating aggregate proportions...")
    
    if fine_fraction_override is not None and fine_fraction_override > 0.3:
        grid_df['coarse_agg_fraction'] = 1.0 - fine_fraction_override
    else:
        grid_df['coarse_agg_fraction'] = get_coarse_agg_fraction_vectorized(nom_max, fine_zone, grid_df['w_b'])
    
    grid_df['fine_ssd'], grid_df['coarse_ssd'] = compute_aggregates_vectorized(
        grid_df['binder'], target_water, grid_df['sp'], grid_df['coarse_agg_fraction'],
        nom_max, density_fa, density_ca
    )
    
    water_delta_fa_series, grid_df['fine_wet'] = aggregate_correction_vectorized(
        material_props['moisture_fa'], grid_df['fine_ssd']
    )
    water_delta_ca_series, grid_df['coarse_wet'] = aggregate_correction_vectorized(
        material_props['moisture_ca'], grid_df['coarse_ssd']
    )
    
    grid_df['water_final'] = (target_water - (water_delta_fa_series + water_delta_ca_series)).clip(lower=5.0)

    # --- 5. Vectorized Cost & CO2 Calculations ---
    if st_progress: st_progress.progress(0.5, text="Calculating cost and CO2...")
    
    grid_df['co2_total'] = (
        grid_df['cement'] * co2_factors.get(norm_cement_choice, 0.0) +
        grid_df['flyash'] * co2_factors.get(CONSTANTS.NORM_FLYASH, 0.0) +
        grid_df['ggbs'] * co2_factors.get(CONSTANTS.NORM_GGBS, 0.0) +
        grid_df['water_final'] * co2_factors.get(CONSTANTS.NORM_WATER, 0.0) +
        grid_df['sp'] * co2_factors.get(CONSTANTS.NORM_SP, 0.0) +
        grid_df['fine_wet'] * co2_factors.get(CONSTANTS.NORM_FINE_AGG, 0.0) +
        grid_df['coarse_wet'] * co2_factors.get(CONSTANTS.NORM_COARSE_AGG, 0.0)
    )
    
    grid_df['cost_total'] = (
        grid_df['cement'] * cost_factors.get(norm_cement_choice, 0.0) +
        grid_df['flyash'] * cost_factors.get(CONSTANTS.NORM_FLYASH, 0.0) +
        grid_df['ggbs'] * cost_factors.get(CONSTANTS.NORM_GGBS, 0.0) +
        grid_df['water_final'] * cost_factors.get(CONSTANTS.NORM_WATER, 0.0) +
        grid_df['sp'] * cost_factors.get(CONSTANTS.NORM_SP, 0.0) +
        grid_df['fine_wet'] * cost_factors.get(CONSTANTS.NORM_FINE_AGG, 0.0) +
        grid_df['coarse_wet'] * cost_factors.get(CONSTANTS.NORM_COARSE_AGG, 0.0)
    )

    # --- 6. Vectorized Feasibility & Purpose Scoring ---
    if st_progress: st_progress.progress(0.7, text="Checking compliance and purpose-fit...")
    
    grid_df['total_mass'] = (
        grid_df['cement'] + grid_df['flyash'] + grid_df['ggbs'] + 
        grid_df['water_final'] + grid_df['sp'] + 
        grid_df['fine_wet'] + grid_df['coarse_wet']
    )
    
    grid_df['check_wb'] = grid_df['w_b'] <= w_b_limit
    grid_df['check_min_cem'] = grid_df['binder'] >= min_cem_exp
    grid_df['check_scm'] = grid_df['scm_total_frac'] <= 0.50
    grid_df['check_unit_wt'] = (grid_df['total_mass'] >= 2200.0) & (grid_df['total_mass'] <= 2600.0)
    
    grid_df['feasible'] = (
        grid_df['check_wb'] & grid_df['check_min_cem'] &
        grid_df['check_scm'] & grid_df['check_unit_wt']
    )
    
    grid_df['reasons'] = get_compliance_reasons_vectorized(grid_df, exposure)
    grid_df['purpose_penalty'] = compute_purpose_penalty_vectorized(grid_df, purpose_profile)
    grid_df['purpose'] = purpose

    # --- 7. Candidate Selection ---
    if st_progress: st_progress.progress(0.8, text="Finding best mix design...")
    
    feasible_candidates_df = grid_df[grid_df['feasible']].copy()
    
    if feasible_candidates_df.empty:
        trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
        return None, None, trace_df.to_dict('records')

    # --- 8. Optimization & Selection ---
    if not enable_purpose_optimization or purpose == 'General':
        objective_col = 'cost_total' if optimize_cost else 'co2_total'
        feasible_candidates_df['composite_score'] = np.nan # Not used
        best_idx = feasible_candidates_df[objective_col].idxmin()
    else:
        feasible_candidates_df['norm_co2'] = _minmax_scale(feasible_candidates_df['co2_total'])
        feasible_candidates_df['norm_cost'] = _minmax_scale(feasible_candidates_df['cost_total'])
        feasible_candidates_df['norm_purpose'] = _minmax_scale(feasible_candidates_df['purpose_penalty'])
        
        w_co2 = purpose_weights.get('w_co2', 0.4)
        w_cost = purpose_weights.get('w_cost', 0.4)
        w_purpose = purpose_weights.get('w_purpose', 0.2)
        
        feasible_candidates_df['composite_score'] = (
            w_co2 * feasible_candidates_df['norm_co2'] +
            w_cost * feasible_candidates_df['norm_cost'] +
            w_purpose * feasible_candidates_df['norm_purpose']
        )
        best_idx = feasible_candidates_df['composite_score'].idxmin()

    best_meta_series = feasible_candidates_df.loc[best_idx]

    # --- 9. Re-hydrate Final Mix & Trace ---
    if st_progress: st_progress.progress(0.9, text="Generating final mix report...")
    
    best_mix_dict = {
        cement_choice: best_meta_series['cement'],
        "Fly Ash": best_meta_series['flyash'],
        "GGBS": best_meta_series['ggbs'],
        "Water": best_meta_series['water_final'],
        "PCE Superplasticizer": best_meta_series['sp'],
        "Fine Aggregate": best_meta_series['fine_wet'],
        "Coarse Aggregate": best_meta_series['coarse_wet']
    }
    
    best_df = evaluate_mix(best_mix_dict, emissions, costs)
    
    best_meta = best_meta_series.to_dict()
    best_meta.update({
        "cementitious": best_meta_series['binder'],
        "water_target": target_water,
        "fine": best_meta_series['fine_wet'],
        "coarse": best_meta_series['coarse_wet'],
        "grade": grade, "exposure": exposure, "nom_max": nom_max,
        "slump": target_slump, "binder_range": (min_b_grade, max_b_grade),
        "material_props": material_props,
        "purpose_metrics": evaluate_purpose_specific_metrics(best_meta, purpose)
    })
    
    trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
    
    score_cols = ['composite_score', 'norm_co2', 'norm_cost', 'norm_purpose']
    if all(col in feasible_candidates_df.columns for col in score_cols):
        scores_to_merge = feasible_candidates_df[score_cols]
        trace_df = trace_df.merge(scores_to_merge, left_index=True, right_index=True, how='left')
    
    return best_df, best_meta, trace_df.to_dict('records')

def generate_baseline(grade, exposure, nom_max, target_slump, agg_shape, 
                      fine_zone, emissions, costs, cement_choice, material_props, 
                      use_sp=True, sp_reduction=0.18,
                      purpose='General', purpose_profile=None):
    
    w_b_limit = float(CONSTANTS.EXPOSURE_WB_LIMITS[exposure])
    min_cem_exp = float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    water_target = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = reasonable_binder_range(grade)

    binder_for_wb = water_target / w_b_limit
    cementitious = min(max(binder_for_wb, min_cem_exp, min_b_grade), max_b_grade)
    actual_wb = water_target / cementitious
    sp = 0.01 * cementitious if use_sp else 0.0
    coarse_agg_frac = get_coarse_agg_fraction(nom_max, fine_zone, actual_wb) # Use scalar version
    density_fa, density_ca = material_props['sg_fa'] * 1000, material_props['sg_ca'] * 1000
    
    fine_ssd, coarse_ssd = compute_aggregates(cementitious, water_target, sp, coarse_agg_frac, nom_max, density_fa, density_ca)
    water_delta_fa, fine_wet = aggregate_correction(material_props['moisture_fa'], fine_ssd)
    water_delta_ca, coarse_wet = aggregate_correction(material_props['moisture_ca'], coarse_ssd)
    
    water_final = max(5.0, water_target - (water_delta_fa + water_delta_ca))

    mix = {cement_choice: cementitious,"Fly Ash": 0.0,"GGBS": 0.0,"Water": water_final, "PCE Superplasticizer": sp,"Fine Aggregate": fine_wet,"Coarse Aggregate": coarse_wet}
    df = evaluate_mix(mix, emissions, costs)
    
    meta = {
        "w_b": actual_wb, "cementitious": cementitious, "cement": cementitious, 
        "flyash": 0.0, "ggbs": 0.0, "water_target": water_target, 
        "water_final": water_final, "sp": sp, "fine": fine_wet, 
        "coarse": coarse_wet, "scm_total_frac": 0.0, "grade": grade, 
        "exposure": exposure, "nom_max": nom_max, "slump": target_slump, 
        "co2_total": float(df["CO2_Emissions (kg/m3)"].sum()),
        "cost_total": float(df["Cost (₹/m3)"].sum()),
        "coarse_agg_fraction": coarse_agg_frac, "material_props": material_props,
        "binder_range": (min_b_grade, max_b_grade)
    }
    
    if purpose_profile is None:
        purpose_profile = CONSTANTS.PURPOSE_PROFILES.get(purpose, CONSTANTS.PURPOSE_PROFILES['General'])
        
    meta.update({
        "purpose": purpose,
        "purpose_metrics": evaluate_purpose_specific_metrics(meta, purpose),
        "purpose_penalty": compute_purpose_penalty(meta, purpose_profile),
        "composite_score": np.nan
    })
    return df, meta

def apply_parser(user_text, current_inputs, use_llm_parser=False):
    """Legacy parser for the old (non-chat) text area."""
    if not user_text.strip(): return current_inputs, [], {}
    try:
        parsed = parse_user_prompt_llm(user_text) if use_llm_parser else simple_parse(user_text)
    except Exception as e:
        st.warning(f"Parser error: {e}, falling back to regex")
        parsed = simple_parse(user_text)
    
    messages, updated = [], current_inputs.copy()
    if "grade" in parsed and parsed["grade"] in CONSTANTS.GRADE_STRENGTH:
        updated["grade"] = parsed["grade"]; messages.append(f"✅ Parser set Grade to **{parsed['grade']}**")
    if "exposure" in parsed and parsed["exposure"] in CONSTANTS.EXPOSURE_WB_LIMITS:
        updated["exposure"] = parsed["exposure"]; messages.append(f"✅ Parser set Exposure to **{parsed['exposure']}**")
    if "target_slump" in parsed:
        s = max(25, min(180, int(parsed["target_slump"])))
        updated["target_slump"] = s; messages.append(f"✅ Parser set Target Slump to **{s} mm**")
    if "cement_choice" in parsed and parsed["cement_choice"] in CONSTANTS.CEMENT_TYPES:
        updated["cement_choice"] = parsed["cement_choice"]; messages.append(f"✅ Parser set Cement Type to **{parsed['cement_choice']}**")
    if "nom_max" in parsed and parsed["nom_max"] in [10, 12.5, 20, 40]:
        updated["nom_max"] = parsed["nom_max"]; messages.append(f"✅ Parser set Aggregate Size to **{parsed['nom_max']} mm**")
    if "purpose" in parsed and parsed["purpose"] in CONSTANTS.PURPOSE_PROFILES:
        updated["purpose"] = parsed["purpose"]; messages.append(f"✅ Parser set Purpose to **{parsed['purpose']}**")
    return updated, messages, parsed

# ==============================================================================
# PART 4: UI HELPER FUNCTIONS
# ==============================================================================

def get_clarification_question(field_name: str) -> str:
    """Returns a natural language question for a missing parameter."""
    questions = {
        "grade": "What concrete grade do you need (e.g., M20, M25, M30)?",
        "exposure": f"What is the exposure condition? (e.g., {', '.join(CONSTANTS.EXPOSURE_WB_LIMITS.keys())})",
        "target_slump": "What is the target slump in mm (e.g., 75, 100, 125)?",
        "nom_max": "What is the nominal maximum aggregate size in mm (e.g., 10, 20, 40)?",
        "cement_choice": f"Which cement type would you like to use? (e.g., {', '.join(CONSTANTS.CEMENT_TYPES)})"
    }
    return questions.get(field_name, "I'm missing some information. Can you provide more details?")

def _plot_overview_chart(st_col, title, y_label, base_val, opt_val, colors, fmt_str):
    with st_col:
        st.subheader(title)
        chart_data = pd.DataFrame({'Mix Type': ['Baseline OPC', 'CivilGPT Optimized'], y_label: [base_val, opt_val]})
        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(chart_data['Mix Type'], chart_data[y_label], color=colors)
        ax.set_ylabel(y_label)
        ax.bar_label(bars, fmt=fmt_str)
        st.pyplot(fig)

def display_mix_details(title, df, meta, exposure):
    st.header(title)
    purpose = meta.get("purpose", "General")
    if purpose != "General":
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💧 Water/Binder Ratio", f"{meta['w_b']:.3f}")
        c2.metric("📦 Total Binder (kg/m³)", f"{meta['cementitious']:.1f}")
        c3.metric("🎯 Target Strength (MPa)", f"{meta['fck_target']:.1f}")
        c4.metric("⚖️ Unit Weight (kg/m³)", f"{df['Quantity (kg/m3)'].sum():.1f}")
        c_p1, c_p2, c_p3 = st.columns(3)
        c_p1.metric("🛠️ Design Purpose", purpose)
        c_p2.metric("⚠️ Purpose Penalty", f"{meta.get('purpose_penalty', 0.0):.2f}", help="Penalty for deviation from purpose targets (lower is better).")
        if "composite_score" in meta and not pd.isna(meta["composite_score"]):
            c_p3.metric("🎯 Composite Score", f"{meta.get('composite_score', 0.0):.3f}", help="Normalized score (lower is better).")
    else:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💧 Water/Binder Ratio", f"{meta['w_b']:.3f}")
        c2.metric("📦 Total Binder (kg/m³)", f"{meta['cementitious']:.1f}")
        c3.metric("🎯 Target Strength (MPa)", f"{meta['fck_target']:.1f}")
        c4.metric("⚖️ Unit Weight (kg/m³)", f"{df['Quantity (kg/m3)'].sum():.1f}")

    st.subheader("Mix Proportions (per m³)")
    st.dataframe(df.style.format({
        "Quantity (kg/m3)": "{:.2f}", "CO2_Factor(kg_CO2_per_kg)": "{:.3f}",
        "CO2_Emissions (kg/m3)": "{:.2f}", "Cost(₹/kg)": "₹{:.2f}", "Cost (₹/m3)": "₹{:.2f}"
    }), use_container_width=True)

    st.subheader("Compliance & Sanity Checks (IS 10262 & IS 456)")
    is_feasible, fail_reasons, warnings, derived, checks_dict = check_feasibility(df, meta, exposure)

    if is_feasible:
        st.success("✅ This mix design is compliant with IS code requirements.", icon="👍")
    else:
        st.error(f"❌ This mix fails {len(fail_reasons)} IS code compliance check(s): " + ", ".join(fail_reasons), icon="🚨")
    for warning in warnings:
        st.warning(warning, icon="⚠️")
    if purpose != "General" and "purpose_metrics" in meta:
        with st.expander(f"Show Estimated Purpose-Specific Metrics ({purpose})"):
            st.json(meta["purpose_metrics"])
    with st.expander("Show detailed calculation parameters"):
        if "purpose_metrics" in derived: derived.pop("purpose_metrics", None)
        st.json(derived)

def display_calculation_walkthrough(meta):
    st.header("Step-by-Step Calculation Walkthrough")
    st.markdown(f"""
    This is a summary of how the **Optimized Mix** was designed according to **IS 10262:2019**.

    #### 1. Target Mean Strength
    - **Characteristic Strength (fck):** `{meta['fck']}` MPa (from Grade {meta['grade']})
    - **Assumed Standard Deviation (S):** `{meta['stddev_S']}` MPa (for '{meta.get('qc_level', 'Good')}' quality control)
    - **Target Mean Strength (f'ck):** `fck + 1.65 * S = {meta['fck']} + 1.65 * {meta['stddev_S']} =` **`{meta['fck_target']:.2f}` MPa**

    #### 2. Water Content
    - **Basis:** IS 10262, Table 4, for `{meta['nom_max']}` mm nominal max aggregate size.
    - **Adjustments:** Slump (`{meta['slump']}` mm), aggregate shape ('{meta.get('agg_shape', 'Angular (baseline)')}'), and superplasticizer use.
    - **Final Target Water (SSD basis):** **`{meta['water_target']:.1f}` kg/m³**

    #### 3. Water-Binder (w/b) Ratio
    - **Constraint:** Maximum w/b ratio for `{meta['exposure']}` exposure is `{CONSTANTS.EXPOSURE_WB_LIMITS[meta['exposure']]}`.
    - **Optimizer Selection:** The optimizer selected the lowest w/b ratio that resulted in a feasible, low-carbon mix.
    - **Selected w/b Ratio:** **`{meta['w_b']:.3f}`**

    #### 4. Binder Content
    - **Initial Binder (from w/b):** `{meta['water_target']:.1f} / {meta['w_b']:.3f} = {(meta['water_target']/meta['w_b']):.1f}` kg/m³
    - **Constraints Check:**
              - Min. for `{meta['exposure']}` exposure: `{CONSTANTS.EXPOSURE_MIN_CEMENT[meta['exposure']]}` kg/m³
              - Typical range for `{meta['grade']}`: `{meta['binder_range'][0]}` - `{meta['binder_range'][1]}`
    - **Final Adjusted Binder Content:** **`{meta['cementitious']:.1f}` kg/m³**

    #### 5. SCM & Cement Content
    - **Optimizer Goal:** Minimize CO₂/cost by replacing cement with SCMs (Fly Ash, GGBS).
    - **Selected SCM Fraction:** `{meta['scm_total_frac']*100:.0f}%`
    - **Material Quantities:**
              - **Cement:** `{meta['cement']:.1f}` kg/m³
              - **Fly Ash:** `{meta['flyash']:.1f}` kg/m³
              - **GGBS:** `{meta['ggbs']:.1f}` kg/m³

    #### 6. Aggregate Proportioning (IS 10262, Table 5)
    - **Basis:** Volume of coarse aggregate for `{meta['nom_max']}` mm aggregate and fine aggregate `{meta.get('fine_zone', 'Zone II')}`.
    - **Adjustment:** Corrected for the final w/b ratio of `{meta['w_b']:.3f}`.
    - **Coarse Aggregate Fraction (by volume):** **`{meta['coarse_agg_fraction']:.3f}`**

    #### 7. Final Quantities (with Moisture Correction)
    - **Fine Aggregate (SSD):** `{(meta['fine'] / (1 + meta['material_props']['moisture_fa']/100)):.1f}` kg/m³
    - **Coarse Aggregate (SSD):** `{(meta['coarse'] / (1 + meta['material_props']['moisture_ca']/100)):.1f}` kg/m³
    - **Moisture Correction:** Adjusted for `{meta['material_props']['moisture_fa']}%` free moisture in fine and `{meta['material_props']['moisture_ca']}%` in coarse aggregate.
    - **Final Batch Weights:**
              - **Water:** **`{meta['water_final']:.1f}` kg/m³**
              - **Fine Aggregate:** **`{meta['fine']:.1f}` kg/m³**
              - **Coarse Aggregate:** **`{meta['coarse']:.1f}` kg/m³**
    """)

# ==============================================================================
# PART 5: CORE GENERATION LOGIC (MODULARIZED)
# ==============================================================================

def run_generation_logic(inputs: dict, emissions_df: pd.DataFrame, costs_df: pd.DataFrame, purpose_profiles_data: dict, st_progress=None):
    """
    Modular function to run mix generation.
    It is called by both the chat mode and the manual mode.
    It sets st.session_state.results upon completion.
    """
    try:
     # --- 1. Validate Inputs ---
        min_grade_req = CONSTANTS.EXPOSURE_MIN_GRADE[inputs["exposure"]]
        grade_order = list(CONSTANTS.GRADE_STRENGTH.keys())
        if grade_order.index(inputs["grade"]) < grade_order.index(min_grade_req):
            st.warning(f"For **{inputs['exposure']}** exposure, IS 456 recommends a minimum grade of **{min_grade_req}**. The grade has been automatically updated.", icon="⚠️")
            inputs["grade"] = min_grade_req
            st.session_state.final_inputs["grade"] = min_grade_req # Update state

        # --- 2. Setup Parameters ---
        calibration_kwargs = inputs.get("calibration_kwargs", {})
        
        # --- HPC: apply overrides if HPC mode is enabled ---
        if inputs.get("enable_hpc_mode", False):
            try:
                st.info("Applying HPC overrides: w/b cap, SP forced ON, extended SCM ranges.", icon="⚠️")
            except Exception:
                pass  # in case st isn't available in some callers (keeps function robust)

            # Force use of superplasticizer (this will be passed to generate_mix)
            inputs["use_sp"] = True

            # Merge calibration overrides (do not destroy user overrides—they take precedence)
            hpc_defaults = {
                "wb_min": CONSTANTS.HPC_OVERRIDES.get("wb_min", 0.30),
                "wb_steps": calibration_kwargs.get("wb_steps", 6),
                "max_flyash_frac": max(calibration_kwargs.get("max_flyash_frac", 0.3), CONSTANTS.HPC_OVERRIDES.get("max_flyash_frac", 0.4)),
                "max_ggbs_frac": max(calibration_kwargs.get("max_ggbs_frac", 0.5), CONSTANTS.HPC_OVERRIDES.get("max_ggbs_frac", 0.6)),
                "scm_step": calibration_kwargs.get("scm_step", 0.1),
                "fine_fraction_override": calibration_kwargs.get("fine_fraction_override", None)
            }

            # Ensure wb_min doesn't exceed the exposure limit; exposure limit will still be used later but we'll use a stricter cap at selection time
            calibration_kwargs = {**hpc_defaults, **calibration_kwargs}
            inputs["calibration_kwargs"] = calibration_kwargs

            # If grade is below the lowest HPC grade, warn and optionally auto-upgrade (we will warn only)
            try:
                if inputs.get("grade") not in CONSTANTS.HPC_OVERRIDES["allowed_grades"] and inputs.get("grade") in CONSTANTS.GRADE_STRENGTH and CONSTANTS.GRADE_STRENGTH[inputs.get("grade")] <= 50:
                    # Just warn user — we don't auto-change grade. App user can pick a higher grade manually.
                    try:
                        st.warning("HPC mode is enabled but selected grade is ≤ M50. For full HPC behavior, choose M55 or above.", icon="⚠️")
                    except Exception:
                        pass
            except Exception:
                pass
        
        purpose = inputs.get('purpose', 'General')
        purpose_profile = purpose_profiles_data.get(purpose, purpose_profiles_data['General'])
        enable_purpose_opt = inputs.get('enable_purpose_optimization', False)
        purpose_weights = inputs.get('purpose_weights', purpose_profiles_data['General']['weights'])
        
        if purpose == 'General': enable_purpose_opt = False
        
        if st_progress: # Only show info box in manual mode, not chat (where the text shows in chat history)
            if enable_purpose_opt:
                st.info(f"🚀 Running composite optimization for **{purpose}**.", icon="🛠️")
            else:
                st.info(f"Running single-objective optimization for **{inputs.get('optimize_for', 'CO₂ Emissions')}**.", icon="⚙️")
        
        # --- 3. Run Generation ---
        fck = CONSTANTS.GRADE_STRENGTH[inputs["grade"]]
        S = CONSTANTS.QC_STDDEV[inputs.get("qc_level", "Good")]
        fck_target = fck + 1.65 * S
        
        opt_df, opt_meta, trace = generate_mix(
            inputs["grade"], inputs["exposure"], inputs["nom_max"],
            inputs["target_slump"], inputs["agg_shape"], inputs["fine_zone"],
            emissions_df, costs_df, inputs["cement_choice"],
            material_props=inputs["material_props"],
            use_sp=inputs["use_sp"], optimize_cost=inputs["optimize_cost"],
            purpose=purpose, purpose_profile=purpose_profile,
            purpose_weights=purpose_weights,
            enable_purpose_optimization=enable_purpose_opt,
            st_progress=st_progress,
            **calibration_kwargs
        )
        
        if st_progress: st_progress.progress(0.95, text="Generating baseline comparison...")
        
        base_df, base_meta = generate_baseline(
            inputs["grade"], inputs["exposure"], inputs["nom_max"],
            inputs["target_slump"], inputs["agg_shape"], inputs["fine_zone"],
            emissions_df, costs_df, inputs["cement_choice"],
            material_props=inputs["material_props"],
            use_sp=inputs.get("use_sp", True), purpose=purpose,
            purpose_profile=purpose_profile
        )
        
        if st_progress: st_progress.progress(1.0, text="Optimization complete!")
        if st_progress: st_progress.empty()

        # --- 4. Store Results ---
        if opt_df is None or base_df is None:
            st.error("Could not find a feasible mix design with the given constraints. Try adjusting the parameters, such as a higher grade or less restrictive exposure condition.", icon="❌")
            if trace:
                st.dataframe(pd.DataFrame(trace))
            st.session_state.results = {"success": False, "trace": trace}
        else:
            if not st.session_state.get("chat_mode", False): # Only show success message in manual mode
                st.success(f"Successfully generated mix designs for **{inputs['grade']}** concrete in **{inputs['exposure']}** conditions.", icon="✅")
            
            for m in (opt_meta, base_meta):
                m.update({
                    "fck": fck, "fck_target": round(fck_target, 1), "stddev_S": S,
                    "qc_level": inputs.get("qc_level", "Good"),
                    "agg_shape": inputs.get("agg_shape"), "fine_zone": inputs.get("fine_zone")
                })
            
            st.session_state.results = {
                "success": True,
                "opt_df": opt_df, "opt_meta": opt_meta,
                "base_df": base_df, "base_meta": base_meta,
                "trace": trace, "inputs": inputs,
                "fck_target": fck_target, "fck": fck, "S": S
            }
            
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}", icon="💥")
        st.exception(traceback.format_exc())
        st.session_state.results = {"success": False, "trace": None}


def display_full_mix_report_from_chat():
    """
    Helper function to render the full manual mode report structure when 
    called from chat mode's button callback, ensuring UI consistency.
    This function re-uses the rendering logic from the manual interface's 
    results section (Section 5) but is called in the main loop after a state 
    switch, forcing the correct display.
    """
    # This function is not called directly from the main logic flow in this fixed version.
    # The fix is to ensure state is set correctly, allowing the main logic's
    # `run_manual_interface` or the global logic flow to handle the display 
    # when `st.session_state.chat_mode` is False and `st.session_state.results` exists.
    # The existing implementation of run_manual_interface handles this correctly 
    # via the shared 'DISPLAY RESULTS' block.
    pass


# ==============================================================================
# PART 6: STREAMLIT APP (UI Sub-modules)
# ==============================================================================

def run_chat_interface(purpose_profiles_data: dict):
    """Renders the entire Chat Mode UI."""
    st.title("💬 CivilGPT Chat Mode")
    st.markdown("Welcome to the conversational interface. Describe your concrete mix needs, and I'll ask for clarifications.")
    
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # --- Display generated results summary in chat ---
    # This block triggers the display of the summary and the 'Open Full Report' button
    if "results" in st.session_state and st.session_state.results.get("success") and not st.session_state.get("chat_results_displayed", False):
        results = st.session_state.results
        opt_meta, base_meta = results["opt_meta"], results["base_meta"]
        
        reduction = (base_meta["co2_total"] - opt_meta["co2_total"]) / base_meta["co2_total"] * 100 if base_meta["co2_total"] > 0 else 0.0
        cost_savings = base_meta["cost_total"] - opt_meta["cost_total"]

        summary_msg = f"""
        ✅ CivilGPT has designed an **{opt_meta['grade']}** mix for **{opt_meta['exposure']}** exposure using **{results['inputs']['cement_choice']}**.

        Here's a quick summary:
        - **🌱 CO₂ reduced by {reduction:.1f}%** (vs. standard OPC mix)
        - **💰 Cost saved ₹{cost_savings:,.0f} / m³**
        - **⚖️ Final w/b ratio:** {opt_meta['w_b']:.3f}
        - **📦 Total Binder:** {opt_meta['cementitious']:.1f} kg/m³
        - **♻️ SCM Content:** {opt_meta['scm_total_frac']*100:.0f}%
        """
        st.session_state.chat_history.append({"role": "assistant", "content": summary_msg})
        st.session_state.chat_results_displayed = True
        st.rerun() # Rerun to display the new summary message
    # --- Show "Open Full Report" button if results are ready (SECOND OCCURRENCE) ---
    if st.session_state.get("chat_results_displayed", False):
        st.info("✅ Mix summary generated. Click below to open the full engineering report.")
        if st.button("📘 Open Full Mix Report"):
            st.session_state.chat_mode = False
            st.session_state.show_full_report_from_chat = True
            st.rerun()


# =====================================================================
# PART 6 (continued): MANUAL MODE INTERFACE WITH HPC TOGGLE
# =====================================================================

def run_manual_interface(purpose_profiles_data: dict):
    """Render the full manual mode interface with HPC toggle and optimized mix generation."""
    st.title("🧱 CivilGPT Manual Mode")
    st.markdown("Manually enter design parameters to generate optimized and baseline mix designs.")

    # --- Sidebar Controls ---
    st.sidebar.header("Input Parameters")
    enable_hpc_mode = st.sidebar.toggle(
        "Enable High-Performance Concrete (HPC) Mode",
        value=False,
        help="When enabled, allows grades up to M100 with stricter w/b and extended SCM ranges."
    )
    if enable_hpc_mode:
        st.sidebar.info(
            "HPC Mode Active: Grades M55–M100 available. W/B capped at 0.35, SP forced ON, and SCM ranges extended.",
            icon="⚙️"
        )

    grade_options = (
        [g for g in CONSTANTS.GRADE_STRENGTH.keys() if CONSTANTS.GRADE_STRENGTH[g] <= 50]
        if not enable_hpc_mode
        else list(CONSTANTS.GRADE_STRENGTH.keys())
    )
    grade = st.sidebar.selectbox("Concrete Grade", grade_options, index=grade_options.index("M25"))
    exposure = st.sidebar.selectbox("Exposure Condition", list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()), index=1)
    qc_level = st.sidebar.selectbox("Quality Control", list(CONSTANTS.QC_STDDEV.keys()), index=0)
    purpose = st.sidebar.selectbox("Design Purpose", list(purpose_profiles_data.keys()), index=0)
    cement_choice = st.sidebar.selectbox("Cement Type", CONSTANTS.CEMENT_TYPES, index=2)
    nom_max = st.sidebar.selectbox("Nominal Max Aggregate (mm)", [10, 12.5, 20, 40], index=2)
    fine_zone = st.sidebar.selectbox("Fine Aggregate Zone", list(CONSTANTS.COARSE_AGG_FRAC_BY_ZONE[20].keys()), index=1)
    agg_shape = st.sidebar.selectbox("Aggregate Shape", list(CONSTANTS.AGG_SHAPE_WATER_ADJ.keys()), index=0)
    target_slump = st.sidebar.slider("Target Slump (mm)", 25, 180, 100, step=5)
    optimize_for = st.sidebar.radio("Optimization Target", ["CO2", "Cost"], horizontal=True, index=0)

    use_sp = st.sidebar.checkbox("Use Superplasticizer (SP)", value=True)
    enable_purpose_opt = st.sidebar.checkbox("Enable Purpose-based Optimization", value=False)

    st.sidebar.markdown("---")
    st.sidebar.header("Material Properties")
    sg_fa = st.sidebar.number_input("Specific Gravity (Fine Aggregate)", 2.4, 2.8, 2.65, 0.01)
    sg_ca = st.sidebar.number_input("Specific Gravity (Coarse Aggregate)", 2.5, 2.9, 2.70, 0.01)
    moisture_fa = st.sidebar.number_input("Free Moisture - Fine (%)", 0.0, 5.0, 1.0, 0.1)
    moisture_ca = st.sidebar.number_input("Free Moisture - Coarse (%)", 0.0, 2.0, 0.5, 0.1)

    st.markdown("---")

    if st.button("🚀 Generate Mix Design", type="primary"):
        material_props = {"sg_fa": sg_fa, "sg_ca": sg_ca, "moisture_fa": moisture_fa, "moisture_ca": moisture_ca}

        inputs = {
            "grade": grade,
            "exposure": exposure,
            "qc_level": qc_level,
            "purpose": purpose,
            "cement_choice": cement_choice,
            "nom_max": nom_max,
            "fine_zone": fine_zone,
            "agg_shape": agg_shape,
            "target_slump": target_slump,
            "optimize_cost": optimize_for == "Cost",
            "optimize_for": optimize_for,
            "use_sp": use_sp,
            "enable_purpose_optimization": enable_purpose_opt,
            "material_props": material_props,
            "enable_hpc_mode": enable_hpc_mode,
        }

        st.session_state.final_inputs = inputs
        st_progress = st.progress(0.0, text="Starting optimization...")

        run_generation_logic(inputs, st.session_state.emissions_df, st.session_state.costs_df, purpose_profiles_data, st_progress=st_progress)

        if st.session_state.results.get("success"):
            st.session_state.show_results = True
            st.experimental_rerun()

    # --- Display Results if Available ---
    if st.session_state.get("show_results", False) and "results" in st.session_state and st.session_state.results.get("success"):
        results = st.session_state.results
        opt_df, opt_meta = results["opt_df"], results["opt_meta"]
        base_df, base_meta = results["base_df"], results["base_meta"]

        st.success(f"✅ Mix design generation complete for {opt_meta['grade']} concrete.", icon="🎯")
        tab1, tab2, tab3 = st.tabs(["Optimized Mix", "Baseline Mix", "Comparison"])

        with tab1:
            display_mix_details("Optimized Mix Design", opt_df, opt_meta, opt_meta["exposure"])
        with tab2:
            display_mix_details("Baseline (IS 10262) Mix", base_df, base_meta, base_meta["exposure"])
        with tab3:
            co2_reduction = (base_meta["co2_total"] - opt_meta["co2_total"]) / base_meta["co2_total"] * 100 if base_meta["co2_total"] > 0 else 0
            cost_saving = base_meta["cost_total"] - opt_meta["cost_total"]

            st.metric("🌱 CO₂ Reduction", f"{co2_reduction:.1f}%")
            st.metric("💰 Cost Saving", f"₹{cost_saving:,.0f}/m³")
            _plot_overview_chart(st, "CO₂ Emissions", "CO₂ (kg/m³)", base_meta["co2_total"], opt_meta["co2_total"], ["#ccc", "#4caf50"], "{:.1f}")
            _plot_overview_chart(st, "Cost", "₹/m³", base_meta["cost_total"], opt_meta["cost_total"], ["#ccc", "#2196f3"], "₹{:.0f}")

        st.markdown("---")
        st.subheader("📘 Detailed Report")
        if st.button("Show Calculation Walkthrough"):
            display_calculation_walkthrough(opt_meta)


# =====================================================================
# PART 7: MAIN ENTRY POINT
# =====================================================================

def main():
    """Main application controller."""
    st.set_page_config(page_title="CivilGPT Concrete Mix Designer", layout="wide")
    st.sidebar.title("⚙️ CivilGPT Navigation")

    # --- Initialize persistent session objects ---
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "results" not in st.session_state:
        st.session_state.results = {}
    if "show_results" not in st.session_state:
        st.session_state.show_results = False
    if "chat_mode" not in st.session_state:
        st.session_state.chat_mode = False

    # --- Data loading (global caching) ---
    materials_df, emissions_df, costs_df = load_data()
    st.session_state.emissions_df = emissions_df
    st.session_state.costs_df = costs_df

    purpose_profiles_data = load_purpose_profiles()

    # --- Sidebar navigation ---
    mode = st.sidebar.radio("Select Mode", ["Chat Mode", "Manual Mode"], horizontal=True)

    if mode == "Chat Mode":
        st.session_state.chat_mode = True
        run_chat_interface(purpose_profiles_data)
    else:
        st.session_state.chat_mode = False
        run_manual_interface(purpose_profiles_data)

    # --- Handle chat → manual switch (show report if triggered) ---
    if st.session_state.get("show_full_report_from_chat", False) and "results" in st.session_state:
        st.session_state.show_full_report_from_chat = False
        st.session_state.show_results = True
        st.session_state.chat_mode = False
        st.experimental_rerun()


# =====================================================================
# ENTRY GUARD
# =====================================================================
if __name__ == "__main__":
    main()
