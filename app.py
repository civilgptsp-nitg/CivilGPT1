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
    GRADE_STRENGTH = {"M10": 10, "M15": 15, "M20": 20, "M25": 25, "M30": 30, "M35": 35, "M40": 40, "M45": 45, "M50": 50}
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
        "M40": (380, 500), "M45": (400, 520), "M50": (420, 540)
    }
    COARSE_AGG_FRAC_BY_ZONE = {
        10: {"Zone I": 0.50, "Zone II": 0.48, "Zone III": 0.46, "Zone IV": 0.44},
        12.5: {"Zone I": 0.59, "Zone II": 0.57, "Zone III": 0.55, "Zone IV": 0.53},
        20: {"Zone I": 0.66, "Zone II": 0.64, "Zone III": 0.62, "Zone IV": 0.60},
        40: {"Zone I": 0.71, "Zone II": 0.69, "Zone III": 0.67, "Zone IV": 0.65}
    }
    FINE_AGG_ZONE_LIMITS = {
        "Zone I":     {"10.0": (100,100),"4.75": (90,100),"2.36": (60,95),"1.18": (30,70),"0.600": (15,34),"0.300": (5,20),"0.150": (0,10)},
        "Zone II":    {"10.0": (100,100),"4.75": (90,100),"2.36": (75,100),"1.18": (55,90),"0.600": (35,59),"0.300": (8,30),"0.150": (0,10)},
        "Zone III": {"10.0": (100,100),"4.75": (90,100),"2.36": (85,100),"1.18": (75,90),"0.600": (60,79),"0.300": (12,40),"0.150": (0,10)},
        "Zone IV":    {"10.0": (95,100),"4.75": (95,100),"2.36": (95,100),"1.18": (90,100),"0.600": (80,100),"0.300": (15,50),"0.150": (0,15)},
    }
    COARSE_LIMITS = {
        10: {"20.0": (100,100), "10.0": (85,100),    "4.75": (0,20)},
        20: {"40.0": (95,100),  "20.0": (95,100),  "10.0": (25,55), "4.75": (0,10)},
        40: {"80.0": (95,100),  "40.0": (95,100),  "20.0": (30,70), "10.0": (0,15)}
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
    vol_sp  = sp / 1200.0
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

    # --- Show "Open Report" button if results are ready (SECOND OCCURRENCE) ---
    if st.session_state.get("chat_results_displayed", False):
        st.info("Your full mix report is ready. You can ask for refinements or open the full report.")

        # === START OF FIX (The core bug fix) ===
        # The key issue was a race condition and inconsistent state across reruns.
        # FIX: Ensure all state variables controlling the mode switch AND report rendering
        # (chat_mode, chat_mode_toggle_functional, active_tab_name, manual_tabs) are set 
        # in the *same callback* before rerunning. We DO NOT delete 'results'.
        def switch_to_manual_mode():
            # 1. Update session state for chat mode flag
            st.session_state["chat_mode"] = False
            # 2. Update session state for sidebar toggle widget key
            st.session_state["chat_mode_toggle_functional"] = False
            # 3. Set manual tab selection to Overview for active tab
            #    This ensures the manual UI knows which tab to render immediately.
            st.session_state["active_tab_name"] = "📊 **Overview**"
            # 4. Also set the manual tabs radio control key so selected index matches immediately
            st.session_state["manual_tabs_radio"] = "📊 **Overview**"  # FIX: Use the new radio key
            # 5. Clear the chat-specific display flag (now safe as results is preserved)
            st.session_state["chat_results_displayed"] = False  
            # 6. Call st.rerun() to force immediate UI update
            st.rerun()


        st.button(
            "📊 Open Full Mix Report & Switch to Manual Mode",  
            use_container_width=True,  
            type="primary",
            on_click=switch_to_manual_mode, # Execute state update
            key="switch_to_manual_btn"
        )
        # === END OF FIX ===

    # --- Handle new user prompt ---
    if user_prompt := st.chat_input("Ask CivilGPT anything about your concrete mix..."):
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        
        parsed_params = parse_user_prompt_llm(user_prompt)
        
        if parsed_params:
            st.session_state.chat_inputs.update(parsed_params)
            parsed_summary = ", ".join([f"**{k}**: {v}" for k, v in parsed_params.items()])
            st.session_state.chat_history.append({"role": "assistant", "content": f"Got it. Understood: {parsed_summary}"})

        missing_fields = [f for f in CONSTANTS.CHAT_REQUIRED_FIELDS if st.session_state.chat_inputs.get(f) is None]
        
        if missing_fields:
            field_to_ask = missing_fields[0]
            question = get_clarification_question(field_to_ask)
            st.session_state.chat_history.append({"role": "assistant", "content": question})
        
        else:
            # All fields are present! Trigger generation.
            st.session_state.chat_history.append({"role": "assistant", "content": "✅ Great, I have all your requirements. Generating your sustainable mix design now..."})
            st.session_state.run_chat_generation = True
            st.session_state.chat_results_displayed = False # Reset flag for new results
            if "results" in st.session_state:
                del st.session_state.results # Clear old results
        
        st.rerun()


def run_manual_interface(purpose_profiles_data: dict, materials_df: pd.DataFrame, emissions_df: pd.DataFrame, costs_df: pd.DataFrame):
    """Renders the entire original (Manual) UI."""
    
    st.title("🧱 CivilGPT: Sustainable Concrete Mix Designer")
    st.markdown("##### An AI-powered tool for creating **IS 10262:2019 compliant** concrete mixes, optimized for low carbon footprint.")

    # --- 1. PROMPT INPUT (Original UI) ---
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        user_text = st.text_area(
            "**Describe Your Requirements**",
            height=100,
            placeholder="e.g., Design an M30 grade concrete for severe exposure using OPC 43. Target a slump of 125 mm with 20 mm aggregates.",
            label_visibility="collapsed",
            key="user_text_input"
        )
    with col2:
        st.write("")
        st.write("")
        run_button = st.button("🚀 Generate Mix Design", use_container_width=True, type="primary")

    # --- 2. ADVANCED MANUAL INPUT EXPANDER ---
    with st.expander("⚙️ Advanced Manual Input: Detailed Parameters and Libraries", expanded=False):
        
        # --- 2a. CORE MIX PARAMETERS ---
        st.subheader("Core Mix Requirements")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            grade = st.selectbox("Concrete Grade", list(CONSTANTS.GRADE_STRENGTH.keys()), index=4, help="Target characteristic compressive strength at 28 days.", key="grade")
        with c2:
            exposure = st.selectbox("Exposure Condition", list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()), index=2, help="Determines durability requirements like min. cement content and max. water-binder ratio as per IS 456.", key="exposure")
        with c3:
            target_slump = st.slider("Target Slump (mm)", 25, 180, 100, 5, help="Specifies the desired consistency and workability of the fresh concrete.", key="target_slump")
        with c4:
            cement_choice = st.selectbox(
                "Cement Type",
                CONSTANTS.CEMENT_TYPES, index=1,
                help="Select the type of cement used. Each option has distinct cost and CO₂ emission factors.",
                key="cement_choice"
            )
        
        st.markdown("---")
        st.subheader("Aggregate Properties & Geometry")
        a1, a2, a3 = st.columns(3)
        with a1:
            nom_max = st.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=2, help="Largest practical aggregate size, influences water demand.", key="nom_max")
        with a2:
            agg_shape = st.selectbox("Coarse Aggregate Shape", list(CONSTANTS.AGG_SHAPE_WATER_ADJ.keys()), index=0, help="Shape affects water demand; angular requires more water than rounded.", key="agg_shape")
        with a3:
            fine_zone = st.selectbox("Fine Aggregate Zone (IS 383)", ["Zone I","Zone II","Zone III","Zone IV"], index=1, help="Grading zone as per IS 383. This is crucial for determining aggregate proportions per IS 10262.", key="fine_zone")
        
        st.markdown("---")
        st.subheader("Admixtures & Quality Control")
        d1, d2 = st.columns(2)
        with d1:
            use_sp = st.checkbox("Use Superplasticizer (PCE)", True, help="Chemical admixture to increase workability or reduce water content.", key="use_sp")
        with d2:
            qc_level = st.selectbox("Quality Control Level", list(CONSTANTS.QC_STDDEV.keys()), index=0, help="Assumed site quality control, affecting the target strength calculation (f_target = fck + 1.65 * S).", key="qc_level")

        st.markdown("---")
        st.subheader("Optimization Settings")
        o1, o2 = st.columns(2)
        with o1:
            purpose = st.selectbox(
                "Design Purpose", 
                list(purpose_profiles_data.keys()), index=0, key="purpose_select",
                help=purpose_profiles_data.get(st.session_state.get("purpose_select", "General"), {}).get("description", "Select the structural element.")
            )
        with o2:
            optimize_for = st.selectbox(
                "Single-Objective Priority", ["CO₂ Emissions", "Cost"], index=0,
                help="Choose whether to optimize the mix for cost or CO₂ footprint (used if Composite Optimization is disabled).",
                key="optimize_for_select"
            )
        
        optimize_cost = (optimize_for == "Cost")
        
        enable_purpose_optimization = st.checkbox(
            "Enable Purpose-Based Composite Optimization", value=(purpose != 'General'), key="enable_purpose",
            help="Optimize for a composite score balancing CO₂, Cost, and Purpose-Fit. If unchecked, uses the 'Single-Objective Priority' above."
        )

        purpose_weights = purpose_profiles_data['General']['weights']
        if enable_purpose_optimization and purpose != 'General':
            with st.expander("Adjust Composite Optimization Weights", expanded=True):
                default_weights = purpose_profiles_data.get(purpose, {}).get('weights', purpose_profiles_data['General']['weights'])
                w_co2 = st.slider("🌱 CO₂ Weight", 0.0, 1.0, default_weights['co2'], 0.05, key="w_co2")
                w_cost = st.slider("💰 Cost Weight", 0.0, 1.0, default_weights['cost'], 0.05, key="w_cost")
                w_purpose = st.slider("🛠️ Purpose-Fit Weight", 0.0, 1.0, default_weights['purpose'], 0.05, key="w_purpose")
                
                # Safe calculation for normalized weights
                total_w = w_co2 + w_cost + w_purpose
                if total_w == 0:
                    st.warning("Weights cannot all be zero. Defaulting to balanced weights.")
                    purpose_weights = {"w_co2": 0.33, "w_cost": 0.33, "w_purpose": 0.34}
                else:
                    purpose_weights = {"w_co2": w_co2 / total_w, "w_cost": w_cost / total_w, "w_purpose": w_purpose / total_w}
                    st.caption(f"Normalized: CO₂ {purpose_weights['w_co2']:.1%}, Cost {purpose_weights['w_cost']:.1%}, Purpose {purpose_weights['w_purpose']:.1%}")
        elif enable_purpose_optimization and purpose == 'General':
              st.info("Purpose 'General' uses single-objective optimization (CO₂ or Cost).")
              enable_purpose_optimization = False

        st.markdown("---")
        # --- 2b. MATERIAL PROPERTIES (MOVED FROM SIDEBAR) ---
        st.subheader("Material Properties (Manual Override)")
        
        sg_fa_default, moisture_fa_default = 2.65, 1.0
        sg_ca_default, moisture_ca_default = 2.70, 0.5

        if materials_df is not None and not materials_df.empty:
            try:
                mat_df = materials_df.copy()
                mat_df['Material'] = mat_df['Material'].str.strip().str.lower()
                fa_row = mat_df[mat_df['Material'] == CONSTANTS.NORM_FINE_AGG]
                if not fa_row.empty:
                    if 'SpecificGravity' in fa_row: sg_fa_default = float(fa_row['SpecificGravity'].iloc[0])
                    if 'MoistureContent' in fa_row: moisture_fa_default = float(fa_row['MoistureContent'].iloc[0])
                ca_row = mat_df[mat_df['Material'] == CONSTANTS.NORM_COARSE_AGG]
                if not ca_row.empty:
                    if 'SpecificGravity' in ca_row: sg_ca_default = float(ca_row['SpecificGravity'].iloc[0])
                    if 'MoistureContent' in ca_row: moisture_ca_default = float(ca_row['MoistureContent'].iloc[0])
                st.info("Material properties auto-loaded from the Shared Library.", icon="📚")
            except Exception as e:
                st.error(f"Failed to parse materials library: {e}")

        m1, m2 = st.columns(2)
        with m1:
            st.markdown("###### Fine Aggregate")
            sg_fa = st.number_input("Specific Gravity (FA)", 2.0, 3.0, sg_fa_default, 0.01, key="sg_fa_manual")
            moisture_fa = st.number_input("Free Moisture Content % (FA)", -2.0, 5.0, moisture_fa_default, 0.1, help="Moisture beyond SSD condition. Negative if absorbent.", key="moisture_fa_manual")
        with m2:
            st.markdown("###### Coarse Aggregate")
            sg_ca = st.number_input("Specific Gravity (CA)", 2.0, 3.0, sg_ca_default, 0.01, key="sg_ca_manual")
            moisture_ca = st.number_input("Free Moisture Content % (CA)", -2.0, 5.0, moisture_ca_default, 0.1, help="Moisture beyond SSD condition. Negative if absorbent.", key="moisture_ca_manual")
        
        st.markdown("---")
        st.subheader("File Uploads (Sieve Analysis & Lab Data)")
        st.caption("These files are for analysis and optional calibration, not core mix design input.")
        
        f1, f2, f3 = st.columns(3)
        with f1:
            fine_csv = st.file_uploader("Fine Aggregate Sieve CSV", type=["csv"], key="fine_csv", help="CSV with 'Sieve_mm' and 'PercentPassing' columns.")
        with f2:
            coarse_csv = st.file_uploader("Coarse Aggregate Sieve CSV", type=["csv"], key="coarse_csv", help="CSV with 'Sieve_mm' and 'PercentPassing' columns.")
        with f3:
            lab_csv = st.file_uploader("Lab Calibration Data CSV", type=["csv"], key="lab_csv", help="CSV with `grade`, `exposure`, `slump`, `nom_max`, `cement_choice`, and `actual_strength` (MPa) columns.")

        st.markdown("---")
        # --- 2c. CALIBRATION & TUNING ---
        with st.expander("Calibration & Tuning (Developer)", expanded=False):
            enable_calibration_overrides = st.checkbox("Enable calibration overrides", False, key="enable_calibration_overrides", help="Override default optimizer search parameters with the values below.")
            c1, c2 = st.columns(2)
            with c1:
                calib_wb_min = st.number_input("W/B search minimum (wb_min)", 0.30, 0.45, 0.35, 0.01, key="calib_wb_min", help="Lower bound for the Water/Binder ratio search space.")
                calib_wb_steps = st.slider("W/B search steps (wb_steps)", 3, 15, 6, 1, key="calib_wb_steps", help="Number of W/B ratios to test between min and the exposure limit.")
                calib_fine_fraction = st.slider("Fine Aggregate Fraction (fine_fraction) Override", 0.30, 0.50, 0.40, 0.01, key="calib_fine_fraction", help="Manually overrides the IS 10262 calculation for aggregate proportions (set to 0 to disable).")
            with c2:
                calib_max_flyash_frac = st.slider("Max Fly Ash fraction", 0.0, 0.5, 0.30, 0.05, key="calib_max_flyash_frac", help="Maximum Fly Ash replacement percentage to test.")
                calib_max_ggbs_frac = st.slider("Max GGBS fraction", 0.0, 0.5, 0.50, 0.05, key="calib_max_ggbs_frac", help="Maximum GGBS replacement percentage to test.")
                calib_scm_step = st.slider("SCM fraction step (scm_step)", 0.05, 0.25, 0.10, 0.05, key="calib_scm_step", help="Step size for testing different SCM replacement percentages.")
        
        # Determine overrides based on expander state (will be re-calculated safely below)
    
    # --- 3. INPUT PARSING AND GENERATION LOGIC ---
    
    # Safe lookup for all required parameters from session state, providing defaults if missing.
    # This replaces the unsafe 'else' block from the original code.
    grade = st.session_state.get("grade", "M30")
    exposure = st.session_state.get("exposure", "Severe")
    target_slump = st.session_state.get("target_slump", 125)
    cement_choice = st.session_state.get("cement_choice", "OPC 43")
    nom_max = st.session_state.get("nom_max", 20)
    agg_shape = st.session_state.get("agg_shape", "Angular (baseline)")
    fine_zone = st.session_state.get("fine_zone", "Zone II")
    use_sp = st.session_state.get("use_sp", True)
    qc_level = st.session_state.get("qc_level", "Good")
    purpose = st.session_state.get("purpose_select", "General")
    optimize_for = st.session_state.get("optimize_for_select", "CO₂ Emissions")
    optimize_cost = (optimize_for == "Cost")
    enable_purpose_optimization = st.session_state.get("enable_purpose", False)

    sg_fa = st.session_state.get("sg_fa_manual", 2.65)
    moisture_fa = st.session_state.get("moisture_fa_manual", 1.0)
    sg_ca = st.session_state.get("sg_ca_manual", 2.70)
    moisture_ca = st.session_state.get("moisture_ca_manual", 0.5)

    fine_csv = st.session_state.get("fine_csv", None)
    coarse_csv = st.session_state.get("coarse_csv", None)
    lab_csv = st.session_state.get("lab_csv", None)

    # Calibration parameters also guarded with .get
    enable_calibration_overrides = st.session_state.get("enable_calibration_overrides", False)
    calib_wb_min = st.session_state.get("calib_wb_min", 0.35) if enable_calibration_overrides else 0.35
    calib_wb_steps = st.session_state.get("calib_wb_steps", 6) if enable_calibration_overrides else 6
    calib_max_flyash_frac = st.session_state.get("calib_max_flyash_frac", 0.3) if enable_calibration_overrides else 0.3
    calib_max_ggbs_frac = st.session_state.get("calib_max_ggbs_frac", 0.5) if enable_calibration_overrides else 0.5
    calib_scm_step = st.session_state.get("calib_scm_step", 0.1) if enable_calibration_overrides else 0.1
    calib_fine_fraction = st.session_state.get("calib_fine_fraction", 0.40) if enable_calibration_overrides else None
    if calib_fine_fraction == 0.40 and not enable_calibration_overrides: calib_fine_fraction = None
    
    # Recalculate purpose weights from sliders if needed, using safe .get
    purpose_weights = purpose_profiles_data['General']['weights']
    if enable_purpose_optimization and purpose != 'General':
        w_co2 = st.session_state.get("w_co2", purpose_profiles_data.get(purpose, purpose_profiles_data['General'])['weights']['co2'])
        w_cost = st.session_state.get("w_cost", purpose_profiles_data.get(purpose, purpose_profiles_data['General'])['weights']['cost'])
        w_purpose = st.session_state.get("w_purpose", purpose_profiles_data.get(purpose, purpose_profiles_data['General'])['weights']['purpose'])
        
        total_w = w_co2 + w_cost + w_purpose
        if total_w > 0:
            purpose_weights = {"w_co2": w_co2 / total_w, "w_cost": w_cost / total_w, "w_purpose": w_purpose / total_w}

    if 'user_text_input' not in st.session_state: st.session_state.user_text_input = ""
    if 'clarification_needed' not in st.session_state: st.session_state.clarification_needed = False
    if 'run_generation_manual' not in st.session_state: st.session_state.run_generation_manual = False
    if 'final_inputs' not in st.session_state: st.session_state.final_inputs = {}

    CLARIFICATION_WIDGETS = {
        "grade": lambda v: st.selectbox("Concrete Grade", list(CONSTANTS.GRADE_STRENGTH.keys()), index=list(CONSTANTS.GRADE_STRENGTH.keys()).index(v) if v in CONSTANTS.GRADE_STRENGTH else 4),
        "exposure": lambda v: st.selectbox("Exposure Condition", list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()), index=list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()).index(v) if v in CONSTANTS.EXPOSURE_WB_LIMITS else 2),
        "target_slump": lambda v: st.slider("Target Slump (mm)", 25, 180, v if isinstance(v, int) else 100, 5),
        "cement_choice": lambda v: st.selectbox("Cement Type", CONSTANTS.CEMENT_TYPES, index=CONSTANTS.CEMENT_TYPES.index(v) if v in CONSTANTS.CEMENT_TYPES else 1),
        "nom_max": lambda v: st.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=[10, 12.5, 20, 40].index(v) if v in [10, 12.5, 20, 40] else 2),
    }

    if run_button:
        st.session_state.run_generation_manual = True
        st.session_state.clarification_needed = False
        if 'results' in st.session_state: del st.session_state.results

        material_props = {'sg_fa': sg_fa, 'moisture_fa': moisture_fa, 'sg_ca': sg_ca, 'moisture_ca': moisture_ca}
        
        calibration_kwargs = {}
        if enable_calibration_overrides: # Use the values from the safe lookups above
            calibration_kwargs = {
                "wb_min": calib_wb_min, "wb_steps": calib_wb_steps,
                "max_flyash_frac": calib_max_flyash_frac, "max_ggbs_frac": calib_max_ggbs_frac,
                "scm_step": calib_scm_step, "fine_fraction_override": calib_fine_fraction
            }
            st.info("Developer calibration overrides are enabled.", icon="🛠️")
            
        inputs = { 
            "grade": grade, "exposure": exposure, "cement_choice": cement_choice, 
            "nom_max": nom_max, "agg_shape": agg_shape, "target_slump": target_slump, 
            "use_sp": use_sp, "optimize_cost": optimize_cost, "qc_level": qc_level, 
            "fine_zone": fine_zone, "material_props": material_props,
            "purpose": purpose, "enable_purpose_optimization": enable_purpose_optimization, 
            "purpose_weights": purpose_weights, "optimize_for": optimize_for,
            "calibration_kwargs": calibration_kwargs
        }

        if st.session_state.user_text_input.strip():
            with st.spinner("🤖 Parsing your request..."):
                use_llm_parser = st.session_state.get('use_llm_parser', False)
                inputs, msgs, _ = apply_parser(st.session_state.user_text_input, inputs, use_llm_parser=use_llm_parser)
            if msgs: st.info(" ".join(msgs), icon="💡")
            
            required_fields = ["grade", "exposure", "target_slump", "nom_max", "cement_choice"]
            missing_fields = [f for f in required_fields if inputs.get(f) is None]

            if missing_fields:
                st.session_state.clarification_needed = True
                st.session_state.final_inputs = inputs
                st.session_state.missing_fields = missing_fields
                st.session_state.run_generation_manual = False
            else:
                st.session_state.run_generation_manual = True
                st.session_state.final_inputs = inputs
        
        else:
            st.session_state.run_generation_manual = True
            st.session_state.final_inputs = inputs


    if st.session_state.get('clarification_needed', False):
        st.markdown("---")
        st.warning("Your request is missing some details. Please confirm the following to continue.", icon="🤔")
        st.markdown("Please confirm the missing values below. Once submitted, mix design will start automatically.")
        with st.form("clarification_form"):
            st.subheader("Please Clarify Your Requirements")
            current_inputs = st.session_state.final_inputs
            missing_fields_list = st.session_state.missing_fields

            num_cols = min(len(missing_fields_list), 3)
            cols = st.columns(num_cols)
            for i, field in enumerate(missing_fields_list):
                with cols[i % num_cols]:
                    widget_func = CLARIFICATION_WIDGETS[field]
                    current_value = current_inputs.get(field)
                    new_value = widget_func(current_value)
                    current_inputs[field] = new_value

            submitted = st.form_submit_button("✅ Confirm & Continue", use_container_width=True, type="primary")
            if submitted:
                st.session_state.final_inputs = current_inputs
                st.session_state.clarification_needed = False
                st.session_state.run_generation_manual = True
                if 'results' in st.session_state: del st.session_state.results
                st.rerun()

    # --- 4. MANUAL GENERATION LOGIC ---
    if st.session_state.get('run_generation_manual', False):
        st.markdown("---")
        progress_bar = st.progress(0.0, text="Initializing optimization...")
        run_generation_logic(
            inputs=st.session_state.final_inputs,
            emissions_df=emissions_df,
            costs_df=costs_df,
            purpose_profiles_data=purpose_profiles_data,
            st_progress=progress_bar
        )
        st.session_state.run_generation_manual = False # Consume flag

    # --- 5. DISPLAY RESULTS (Common to both modes) ---
    if 'results' in st.session_state and st.session_state.results["success"]:
        results = st.session_state.results
        opt_df, opt_meta = results["opt_df"], results["opt_meta"]
        base_df, base_meta = results["base_df"], results["base_meta"]
        trace, inputs = results["trace"], results["inputs"]
        
        # --- FIX: Tab Controller Fix ---
        TAB_NAMES = [
            "📊 **Overview**", "🌱 **Optimized Mix**", "🏗️ **Baseline Mix**",
            "⚖️ **Trade-off Explorer**", "📋 **QA/QC & Gradation**",
            "📥 **Downloads & Reports**", "🔬 **Lab Calibration**"
        ]
        
        # Ensure session state active tab is valid, else default
        # The switch_to_manual_mode callback sets 'active_tab_name' and 'manual_tabs_radio'
        if st.session_state.active_tab_name not in TAB_NAMES:
            st.session_state.active_tab_name = TAB_NAMES[0]

        # Get the index for the radio button
        try:
            default_index = TAB_NAMES.index(st.session_state.active_tab_name)
        except ValueError:
            default_index = 0
            st.session_state.active_tab_name = TAB_NAMES[0]

        # Use st.radio for navigation control
        selected_tab = st.radio(
            "Mix Report Navigation",
            options=TAB_NAMES,
            index=default_index,
            horizontal=True,
            label_visibility="collapsed",
            key="manual_tabs_radio" # FIX: Changed key from 'manual_tabs' to 'manual_tabs_radio'
        )
        
        # Update the session state variable for next time
        st.session_state.active_tab_name = selected_tab # FIX: Ensures active_tab_name holds the *current* selection
        # --- END FIX ---

        if selected_tab == "📊 **Overview**":
            co2_opt, cost_opt = opt_meta["co2_total"], opt_meta["cost_total"]
            co2_base, cost_base = base_meta["co2_total"], base_meta["cost_total"]
            reduction = (co2_base - co2_opt) / co2_base * 100 if co2_base > 0 else 0.0
            cost_savings = cost_base - cost_opt

            st.subheader("Performance At a Glance")
            c1, c2, c3 = st.columns(3)
            c1.metric("🌱 CO₂ Reduction", f"{reduction:.1f}%", f"{co2_base - co2_opt:.1f} kg/m³ saved")
            c2.metric("💰 Cost Savings", f"₹{cost_savings:,.0f} / m³", f"{cost_savings/cost_base*100 if cost_base>0 else 0:.1f}% cheaper")
            c3.metric("♻️ SCM Content", f"{opt_meta['scm_total_frac']*100:.0f}%", f"{base_meta['scm_total_frac']*100:.0f}% in baseline", help="Supplementary Cementitious Materials (Fly Ash, GGBS) replace high-carbon cement.")
            
            if opt_meta.get("purpose", "General") != "General":
                st.markdown("---")
                c_p1, c_p2, c_p3 = st.columns(3)
                c_p1.metric("🛠️ Design Purpose", opt_meta['purpose'])
                c_p2.metric("🎯 Composite Score", f"{opt_meta.get('composite_score', 0.0):.3f}", help="Normalized score (lower is better) balancing CO₂, Cost, and Purpose-Fit.")
                c_p3.metric("⚠️ Purpose Penalty", f"{opt_meta.get('purpose_penalty', 0.0):.2f}", help="Penalty for deviation from purpose targets (lower is better).")

            st.markdown("---")
            col1, col2 = st.columns(2)
            _plot_overview_chart(col1, "📊 Embodied Carbon (CO₂e)", "CO₂ (kg/m³)", 
                                 co2_base, co2_opt, ['#D3D3D3', '#4CAF50'], '{:,.1f}')
            _plot_overview_chart(col2, "💵 Material Cost", "Cost (₹/m³)", 
                                 cost_base, cost_opt, ['#D3D3D3', '#2196F3'], '₹{:,.0f}')

        elif selected_tab == "🌱 **Optimized Mix**":
            display_mix_details("🌱 Optimized Low-Carbon Mix Design", opt_df, opt_meta, inputs['exposure'])
            if st.toggle("📖 Show Step-by-Step IS Calculation", key="toggle_walkthrough_tab2"):
                display_calculation_walkthrough(opt_meta)

        elif selected_tab == "🏗️ **Baseline Mix**":
            display_mix_details("🏗️ Standard OPC Baseline Mix Design", base_df, base_meta, inputs['exposure'])

        elif selected_tab == "⚖️ **Trade-off Explorer**":
            st.header("Cost vs. Carbon Trade-off Analysis")
            st.markdown("This chart displays all IS-code compliant mixes found by the optimizer. The blue line represents the **Pareto Front**—the set of most efficient mixes where you can't improve one objective (e.g., lower CO₂) without worsening the other (e.g., increasing cost).")

            if trace:
                trace_df = pd.DataFrame(trace)
                feasible_mixes = trace_df[trace_df['feasible']].copy()

                if not feasible_mixes.empty:
                    pareto_df = pareto_front(feasible_mixes, x_col="cost", y_col="co2")
                    
                    # Ensure safe default for slider
                    current_alpha = st.session_state.get("pareto_slider_alpha", 0.5)
                    
                    if not pareto_df.empty:
                        alpha = st.slider(
                            "Prioritize Sustainability (CO₂) ↔ Cost",
                            min_value=0.0, max_value=1.0, value=current_alpha, step=0.05,
                            help="Slide towards Sustainability to prioritize low CO₂, or towards Cost to prioritize low price. The green diamond will show the best compromise on the Pareto Front for your chosen preference.",
                            key="pareto_slider_alpha"
                        )
                        pareto_df_norm = pareto_df.copy()
                        cost_min, cost_max = pareto_df_norm['cost'].min(), pareto_df_norm['cost'].max()
                        co2_min, co2_max = pareto_df_norm['co2'].min(), pareto_df_norm['co2'].max()
                        pareto_df_norm['norm_cost'] = 0.0 if (cost_max - cost_min) == 0 else (pareto_df_norm['cost'] - cost_min) / (cost_max - cost_min)
                        pareto_df_norm['norm_co2'] = 0.0 if (co2_max - co2_min) == 0 else (pareto_df_norm['co2'] - co2_min) / (co2_max - co2_min)
                        pareto_df_norm['score'] = alpha * pareto_df_norm['norm_co2'] + (1 - alpha) * pareto_df_norm['norm_cost']
                        best_compromise_mix = pareto_df_norm.loc[pareto_df_norm['score'].idxmin()]

                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.scatter(feasible_mixes["cost"], feasible_mixes["co2"], color='grey', alpha=0.5, label='All Feasible Mixes', zorder=1)
                        pareto_df_sorted = pareto_df.sort_values(by="cost")
                        ax.plot(pareto_df_sorted["cost"], pareto_df_sorted["co2"], '-o', color='blue', label='Pareto Front (Efficient Mixes)', linewidth=2, zorder=2)
                        
                        optimize_for_label = f"Composite Score ({inputs['purpose']})" if inputs.get('enable_purpose_optimization', False) and inputs.get('purpose', 'General') != 'General' else inputs.get('optimize_for', 'CO₂ Emissions')
                        
                        ax.plot(opt_meta['cost_total'], opt_meta['co2_total'], '*', markersize=15, color='red', label=f'Chosen Mix ({optimize_for_label})', zorder=3)
                        ax.plot(best_compromise_mix['cost'], best_compromise_mix['co2'], 'D', markersize=10, color='green', label='Best Compromise (from slider)', zorder=3)
                        ax.set_xlabel("Material Cost (₹/m³)"); ax.set_ylabel("Embodied Carbon (kg CO₂e / m³)")
                        ax.set_title("Pareto Front of Feasible Concrete Mixes"); ax.grid(True, linestyle='--', alpha=0.6); ax.legend()
                        st.pyplot(fig)

                        st.markdown("---")
                        st.subheader("Details of Selected 'Best Compromise' Mix")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("💰 Cost", f"₹{best_compromise_mix['cost']:.0f} / m³")
                        c2.metric("🌱 CO₂", f"{best_compromise_mix['co2']:.1f} kg / m³")
                        c3.metric("💧 Water/Binder Ratio", f"{best_compromise_mix['wb']:.3f}")
                        
                        full_compromise_mix = trace_df[
                            (trace_df['cost'] == best_compromise_mix['cost']) &
                            (trace_df['co2'] == best_compromise_mix['co2'])
                        ].iloc[0]

                        if 'composite_score' in full_compromise_mix and not pd.isna(full_compromise_mix['composite_score']):
                            c4, c5 = st.columns(2)
                            c4.metric("⚠️ Purpose Penalty", f"{full_compromise_mix['purpose_penalty']:.2f}")
                            c5.metric("🎯 Composite Score", f"{full_compromise_mix['composite_score']:.3f}")
                        
                    else:
                        st.info("No Pareto front could be determined from the feasible mixes.", icon="ℹ️")
                else:
                    st.warning("No feasible mixes were found by the optimizer, so no trade-off plot can be generated.", icon="⚠️")
            else:
                st.error("Optimizer trace data is missing.", icon="❌")

        elif selected_tab == "📋 **QA/QC & Gradation**":
            st.header("Quality Assurance & Sieve Analysis")
            sample_fa_data = "Sieve_mm,PercentPassing\n4.75,95\n2.36,80\n1.18,60\n0.600,40\n0.300,15\n0.150,5"
            sample_ca_data = "Sieve_mm,PercentPassing\n40.0,100\n20.0,98\n10.0,40\n4.75,5"
            
            fine_csv_to_use = st.session_state.get('fine_csv')
            coarse_csv_to_use = st.session_state.get('coarse_csv')

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fine Aggregate Gradation")
                if fine_csv_to_use is not None:
                    try:
                        fine_csv_to_use.seek(0); df_fine = pd.read_csv(fine_csv_to_use)
                        ok_fa, msgs_fa = sieve_check_fa(df_fine, inputs.get("fine_zone", "Zone II"))
                        if ok_fa: st.success(msgs_fa[0], icon="✅")
                        else:
                            for m in msgs_fa: st.error(m, icon="❌")
                        st.dataframe(df_fine, use_container_width=True)
                    except Exception as e: st.error(f"Error processing Fine Aggregate CSV: {e}")
                else:
                    st.info("Upload a Fine Aggregate CSV in the advanced input area to perform a gradation check against IS 383.", icon="ℹ️")
                    st.download_button("Download Sample Fine Agg. CSV", sample_fa_data, "sample_fine_aggregate.csv", "text/csv")
            with col2:
                st.subheader("Coarse Aggregate Gradation")
                if coarse_csv_to_use is not None:
                    try:
                        coarse_csv_to_use.seek(0); df_coarse = pd.read_csv(coarse_csv_to_use)
                        ok_ca, msgs_ca = sieve_check_ca(df_coarse, inputs["nom_max"])
                        if ok_ca: st.success(msgs_ca[0], icon="✅")
                        else:
                            for m in msgs_ca: st.error(m, icon="❌")
                        st.dataframe(df_coarse, use_container_width=True)
                    except Exception as e: st.error(f"Error processing Coarse Aggregate CSV: {e}")
                else:
                    st.info("Upload a Coarse Aggregate CSV in the advanced input area to perform a gradation check against IS 383.", icon="ℹ️")
                    st.download_button("Download Sample Coarse Agg. CSV", sample_ca_data, "sample_coarse_aggregate.csv", "text/csv")

            st.markdown("---")
            with st.expander("📖 View Step-by-Step Calculation Walkthrough"):
                display_calculation_walkthrough(opt_meta)
            with st.expander("🔬 View Optimizer Trace (Advanced)"):
                if trace:
                    trace_df = pd.DataFrame(trace)
                    st.markdown("The table below shows every mix combination attempted by the optimizer. 'Feasible' mixes met all IS-code checks.")
                    def style_feasible_cell(v):
                        return 'background-color: #e8f5e9; color: #155724; text-align: center;' if v else 'background-color: #ffebee; color: #721c24; text-align: center;'
                    
                    st.dataframe(
                        trace_df.style
                            .apply(lambda s: [style_feasible_cell(v) for v in s], subset=['feasible'])
                            .format({
                                "feasible": lambda v: "✅" if v else "❌", "wb": "{:.3f}", "flyash_frac": "{:.2f}", 
                                "ggbs_frac": "{:.2f}", "co2": "{:.1f}", "cost": "{:.1f}",
                                "purpose_penalty": "{:.2f}", "composite_score": "{:.4f}",
                                "norm_co2": "{:.3f}", "norm_cost": "{:.3f}", "norm_purpose": "{:.3f}",
                            }),
                        use_container_width=True
                    )
                    
                    st.markdown("#### CO₂ vs. Cost of All Candidate Mixes")
                    fig, ax = plt.subplots()
                    scatter_colors = ["#4CAF50" if f else "#F44336" for f in trace_df["feasible"]]
                    ax.scatter(trace_df["cost"], trace_df["co2"], c=scatter_colors, alpha=0.6)
                    ax.set_xlabel("Material Cost (₹/m³)"); ax.set_ylabel("Embodied Carbon (kg CO₂e/m³)")
                    ax.grid(True, linestyle='--', alpha=0.6); st.pyplot(fig)
                else:
                    st.info("Trace not available.")

        elif selected_tab == "📥 **Downloads & Reports**":
            st.header("Download Reports")
            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                opt_df.to_excel(writer, sheet_name="Optimized_Mix", index=False)
                base_df.to_excel(writer, sheet_name="Baseline_Mix", index=False)
                pd.DataFrame([opt_meta]).T.to_excel(writer, sheet_name="Optimized_Meta")
                pd.DataFrame([base_meta]).T.to_excel(writer, sheet_name="Baseline_Meta")
                if trace: pd.DataFrame(trace).to_excel(writer, sheet_name="Optimizer_Trace", index=False)
            excel_buffer.seek(0)

            pdf_buffer = BytesIO()
            doc = SimpleDocTemplate(pdf_buffer, pagesize=(8.5*inch, 11*inch))
            styles = getSampleStyleSheet()
            story = [Paragraph("CivilGPT Sustainable Mix Report", styles['h1']), Spacer(1, 0.2*inch)]
            summary_data = [
                ["Metric", "Optimized Mix", "Baseline Mix"],
                ["CO₂ (kg/m³)", f"{opt_meta['co2_total']:.1f}", f"{base_meta['co2_total']:.1f}"],
                ["Cost (₹/m³)", f"₹{opt_meta['cost_total']:,.2f}", f"₹{base_meta['cost_total']:,.2f}"],
                ["w/b Ratio", f"{opt_meta['w_b']:.3f}", f"{base_meta['w_b']:.3f}"],
                ["Binder (kg/m³)", f"{opt_meta['cementitious']:.1f}", f"{base_meta['cementitious']:.1f}"],
                ["Purpose", f"{opt_meta.get('purpose', 'N/A')}", f"{base_meta.get('purpose', 'N/A')}"],
                ["Composite Score", f"{opt_meta.get('composite_score', 'N/A'):.3f}" if 'composite_score' in opt_meta and not pd.isna(opt_meta['composite_score']) else "N/A", "N/A"],
            ]
            summary_table = Table(summary_data, hAlign='LEFT', colWidths=[2*inch, 1.5*inch, 1.5*inch])
            summary_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            story.extend([Paragraph(f"Design for <b>{inputs['grade']} / {inputs['exposure']} Exposure</b>", styles['h2']), summary_table, Spacer(1, 0.2*inch)])
            opt_data_pdf = [opt_df.columns.values.tolist()] + opt_df.applymap(lambda x: f'{x:.2f}' if isinstance(x, float) else x).values.tolist()
            opt_table = Table(opt_data_pdf, hAlign='LEFT')
            opt_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.palegreen)]))
            story.extend([Paragraph("Optimized Mix Proportions (kg/m³)", styles['h2']), opt_table])
            doc.build(story); pdf_buffer.seek(0)

            d1, d2 = st.columns(2)
            with d1:
                st.download_button("📄 Download PDF Report", data=pdf_buffer.getvalue(), file_name="CivilGPT_Report.pdf", mime="application/pdf", use_container_width=True)
                st.download_button("📈 Download Excel Report", data=excel_buffer.getvalue(), file_name="CivilGPT_Mix_Designs.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            with d2:
                st.download_button("✔️ Optimized Mix (CSV)", data=opt_df.to_csv(index=False).encode("utf-8"), file_name="optimized_mix.csv", mime="text/csv", use_container_width=True)
                st.download_button("✖️ Baseline Mix (CSV)", data=base_df.to_csv(index=False).encode("utf-8"), file_name="baseline_mix.csv", mime="text/csv", use_container_width=True)

        elif selected_tab == "🔬 **Lab Calibration**":
            st.header("🔬 Lab Calibration Analysis")
            lab_csv_to_use = st.session_state.get('lab_csv')
            
            if lab_csv_to_use is not None:
                try:
                    lab_csv_to_use.seek(0); lab_results_df = pd.read_csv(lab_csv_to_use)
                    comparison_df, error_metrics = run_lab_calibration(lab_results_df)

                    if comparison_df is not None and not comparison_df.empty:
                        st.subheader("Error Metrics")
                        st.markdown("Comparing lab-tested 28-day strength against the IS code's required target strength (`f_target = fck + 1.65 * S`).")
                        m1, m2, m3 = st.columns(3)
                        m1.metric(label="Mean Absolute Error (MAE)", value=f"{error_metrics['Mean Absolute Error (MPa)']:.2f} MPa")
                        m2.metric(label="Root Mean Squared Error (RMSE)", value=f"{error_metrics['Root Mean Squared Error (MPa)']:.2f} MPa")
                        m3.metric(label="Mean Bias (Over/Under-prediction)", value=f"{error_metrics['Mean Bias (MPa)']:.2f} MPa")
                        st.markdown("---")

                        st.subheader("Comparison: Lab vs. Predicted Target Strength")
                        st.dataframe(comparison_df.style.format({
                            "Lab Strength (MPa)": "{:.2f}",
                            "Predicted Target Strength (MPa)": "{:.2f}",
                            "Error (MPa)": "{:+.2f}"
                        }), use_container_width=True)

                        st.subheader("Prediction Accuracy Scatter Plot")
                        fig, ax = plt.subplots()
                        ax.scatter(comparison_df["Lab Strength (MPa)"], comparison_df["Predicted Target Strength (MPa)"], alpha=0.7, label="Data Points")
                        lims = [np.min([ax.get_xlim(), ax.get_ylim()]), np.max([ax.get_xlim(), ax.get_ylim()])]
                        ax.plot(lims, lims, 'r--', alpha=0.75, zorder=0, label="Perfect Prediction (y=x)")
                        ax.set_xlabel("Actual Lab Strength (MPa)"); ax.set_ylabel("Predicted Target Strength (MPa)")
                        ax.set_title("Lab Strength vs. Predicted Target Strength"); ax.legend(); ax.grid(True)
                        st.pyplot(fig)
                    else:
                        st.warning("Could not process the uploaded lab data CSV. Please check the file format, column names, and ensure it contains valid data.", icon="⚠️")
                except Exception as e:
                    st.error(f"Failed to read or process the lab data CSV file: {e}", icon="💥")
            else:
                st.info("Upload a lab data CSV in the **Advanced Manual Input** section to automatically compare CivilGPT's target strength calculations against your real-world results.", icon="ℹ️")
        
    elif 'results' in st.session_state and not st.session_state.results["success"]:
        pass # Error message was already shown
    elif not st.session_state.get('clarification_needed'):
        st.info("Enter your concrete requirements in the prompt box above, or expand the **Advanced Manual Input** section to specify parameters.", icon="👆")
        st.markdown("---")
        st.subheader("How It Works")
        st.markdown("""
        1.  **Input Requirements**: Describe your project needs (e.g., "M25 concrete for moderate exposure") or use the manual inputs for detailed control.
        2.  **Select Purpose**: Choose your design purpose (e.g., 'Slab', 'Column') to enable purpose-specific optimization.
        3.  **IS Code Compliance**: The app generates dozens of candidate mixes, ensuring each one adheres to the durability and strength requirements of Indian Standards **IS 10262** and **IS 456**.
        4.  **Sustainability Optimization**: It then calculates the embodied carbon (CO₂e), cost, and 'Purpose-Fit' for every compliant mix.
        5.  **Best Mix Selection**: Finally, it presents the mix with the best **composite score** (or lowest CO₂/cost) alongside a standard OPC baseline for comparison.
        """)

# ==============================================================================
# PART 7: MAIN APP CONTROLLER
# ==============================================================================

def main():
    st.set_page_config(
        page_title="CivilGPT - Sustainable Concrete Mix Designer",
        page_icon="🧱",
        layout="wide"
    )

    # Custom CSS for dark theme and switch card
    st.markdown("""
    <style>
        .main .block-container {
            padding-top: 2rem; padding-bottom: 2rem;
            padding-left: 5rem; padding-right: 5rem;
        }
        .st-emotion-cache-1y4p8pa { max-width: 100%; }
        .stTextArea [data-baseweb=base-input] {
            border-color: #4A90E2; box-shadow: 0 0 5px #4A90E2;
        }
        [data-testid="chat-message-container"] {
            border-radius: 8px;
            padding: 0.75rem;
            margin-bottom: 0.5rem;
        }
        [data-testid="chat-message-container"] [data-testid="stMarkdown"] p {
            line-height: 1.6;
        }
        /* Style for the Mode Switch Card */
        .mode-card {
            background-color: #1E1E1E; /* Dark background */
            border-radius: 8px;
            padding: 15px;
            margin-bottom: 10px;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.5);
            border: 1px solid #333333;
            transition: all 0.3s;
        }
        .mode-card:hover {
            box-shadow: 0 6px 12px rgba(0, 0, 0, 0.7);
            border-color: #4A90E2;
        }
        .mode-card h4 {
            color: #FFFFFF; /* White text */
            margin-top: 0;
            margin-bottom: 5px;
        }
        .mode-card p {
            color: #CCCCCC; /* Light gray text */
            font-size: 0.85em;
            margin-bottom: 10px;
        }
        /* Custom spacing for sidebar */
        [data-testid="stSidebarContent"] > div:first-child {
            padding-bottom: 0rem;
        }
    </style>
    """, unsafe_allow_html=True)

    # --- 1. STATE INITIALIZATION ---
    if "chat_mode" not in st.session_state:
        st.session_state.chat_mode = False
    
    if "active_tab_name" not in st.session_state:
        st.session_state.active_tab_name = "📊 **Overview**"
        
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_inputs" not in st.session_state:
        st.session_state.chat_inputs = {}
    if "chat_results_displayed" not in st.session_state:
        st.session_state.chat_results_displayed = False
    if "run_chat_generation" not in st.session_state:
        st.session_state.run_chat_generation = False
    # Ensure manual_tabs_radio key is initialized for the manual report UI element
    if "manual_tabs_radio" not in st.session_state:
        st.session_state.manual_tabs_radio = "📊 **Overview**"
        
    purpose_profiles_data = load_purpose_profiles()

    # --- 2. SIDEBAR SETUP (COMMON ELEMENTS) ---
    st.sidebar.title("Mode Selection")

    if "llm_init_message" in st.session_state:
        msg_type, msg_content = st.session_state.pop("llm_init_message")
        if msg_type == "success": st.sidebar.success(msg_content, icon="🤖")
        elif msg_type == "info": st.sidebar.info(msg_content, icon="ℹ️")
        elif msg_type == "warning": st.sidebar.warning(msg_content, icon="⚠️")

    llm_is_ready = st.session_state.get("llm_enabled", False)
    
    # NEW: Redesigned Chat Mode Switch Card
    with st.sidebar:
        
        # Determine the current mode and helper text
        if st.session_state.chat_mode:
            card_title = "🤖 CivilGPT Chat Mode"
            card_desc = "Converse with the AI to define mix requirements."
            card_icon = "💬"
            is_chat_mode = True
        else:
            card_title = "⚙️ Manual/Prompt Mode"
            card_desc = "Use the detailed input sections to define your mix."
            card_icon = "📝"
            is_chat_mode = False

        # Build the card with toggle
        st.markdown(f"""
        <div class="mode-card">
            <h4 style='display: flex; align-items: center;'>
                <span style='font-size: 1.2em; margin-right: 10px;'>{card_icon}</span>
                {card_title}
            </h4>
            <p>{card_desc}</p>
        </div>
        """, unsafe_allow_html=True)
        
        # The actual Streamlit toggle for functionality
        # The toggle must read from the session state key "chat_mode" and use the key "chat_mode_toggle_functional"
        chat_mode = st.toggle(
            f"Switch to {'Manual' if is_chat_mode else 'Chat'} Mode",
            value=st.session_state.get("chat_mode") if llm_is_ready else False, # Ensure we read from the core state variable
            key="chat_mode_toggle_functional",
            help="Toggle to switch between conversational and manual input interfaces." if llm_is_ready else "Chat Mode requires a valid GROQ_API_KEY.",
            disabled=not llm_is_ready,
            label_visibility="collapsed" # Hide the label as the card provides context
        )
        st.session_state.chat_mode = chat_mode
        
        # Move the LLM parser toggle into the sidebar if we're in manual mode, for easy access
        if not chat_mode and llm_is_ready:
              st.markdown("---")
              st.checkbox(
                  "Use Groq LLM Parser for Text Prompt", 
                  value=False, key="use_llm_parser",
                  help="Use the LLM to automatically extract parameters from the text area above."
              )


    if chat_mode:
        if st.sidebar.button("🧹 Clear Chat History", use_container_width=True):
            st.session_state.chat_history = []
            st.session_state.chat_inputs = {}
            st.session_state.chat_results_displayed = False
            if "results" in st.session_state:
                del st.session_state.results
            st.rerun()
        st.sidebar.markdown("---")

    # The file uploaders are now inside the Advanced Manual Input expander in run_manual_interface.
    # We must call load_data here (before either interface is run) to ensure the DFs are available.
    materials_df, emissions_df, costs_df = load_data(
        st.session_state.get("materials_csv"), 
        st.session_state.get("emissions_csv"), 
        st.session_state.get("cost_csv")
    )


    # --- 3. CHAT-TRIGGERED GENERATION (RUNS BEFORE UI) ---
    if st.session_state.get('run_chat_generation', False):
        st.session_state.run_chat_generation = False # Consume flag
        
        chat_inputs = st.session_state.chat_inputs
        default_material_props = {'sg_fa': 2.65, 'moisture_fa': 1.0, 'sg_ca': 2.70, 'moisture_ca': 0.5}
        
        inputs = {
            "grade": "M30", "exposure": "Severe", "cement_choice": "OPC 43",
            "nom_max": 20, "agg_shape": "Angular (baseline)", "target_slump": 125,
            "use_sp": True, "optimize_cost": False, "qc_level": "Good",
            "fine_zone": "Zone II", "material_props": default_material_props,
            "purpose": "General", "enable_purpose_optimization": False,
            "purpose_weights": purpose_profiles_data['General']['weights'],
            "optimize_for": "CO₂ Emissions",
            "calibration_kwargs": {}, # No calibration in chat mode
            **chat_inputs # Override defaults with chat values
        }
        
        inputs["optimize_cost"] = (inputs.get("optimize_for") == "Cost")
        inputs["enable_purpose_optimization"] = (inputs.get("purpose") != 'General')
        if inputs["enable_purpose_optimization"]:
            inputs["purpose_weights"] = purpose_profiles_data.get(inputs["purpose"], {}).get('weights', purpose_profiles_data['General']['weights'])

        st.session_state.final_inputs = inputs
        
        with st.spinner("⚙️ Running IS-code calculations and optimizing..."):
            run_generation_logic(
                inputs=inputs,
                emissions_df=emissions_df,
                costs_df=costs_df,
                purpose_profiles_data=purpose_profiles_data,
                st_progress=None # No progress bar in chat
            )

    # --- 4. RENDER UI (Chat or Manual) ---
    if chat_mode:
        run_chat_interface(purpose_profiles_data)
    else:
        run_manual_interface(purpose_profiles_data, materials_df, emissions_df, costs_df)


if __name__ == "__main__":
    main()
