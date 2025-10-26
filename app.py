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
import traceback
import uuid
import time

# ==============================================================================
# PART 1: CONSTANTS & CORE DATA
# ==============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
LAB_FILE = "lab_processed_mgrades_only.xlsx"
MIX_FILE = "concrete_mix_design_data_cleaned_standardized.xlsx"

class CONSTANTS:
    GRADE_STRENGTH = {"M10": 10, "M15": 15, "M20": 20, "M25": 25, "M30": 30, "M35": 35, "M40": 40, "M45": 45, "M50": 50, "M60": 60, "M70": 70, "M80": 80, "M90": 90, "M100": 100}
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
        "M60": (460, 700), "M70": (500, 760), "M80": (540, 820),
        "M90": (580, 880), "M100": (620, 940)
    }
    COARSE_AGG_FRAC_BY_ZONE = {
        10: {"Zone I": 0.50, "Zone II": 0.48, "Zone III": 0.46, "Zone IV": 0.44},
        12.5: {"Zone I": 0.59, "Zone II": 0.57, "Zone III": 0.55, "Zone IV": 0.53},
        20: {"Zone I": 0.66, "Zone II": 0.64, "Zone III": 0.62, "Zone IV": 0.60},
        40: {"Zone I": 0.71, "Zone II": 0.69, "Zone III": 0.67, "Zone IV": 0.65}
    }
    FINE_AGG_ZONE_LIMITS = {
        "Zone I": {"10.0": (100,100),"4.75": (90,100),"2.36": (60,95),"1.18": (30,70),"0.600": (15,34),"0.300": (5,20),"0.150": (0,10)},
        "Zone II": {"10.0": (100,100),"4.75": (90,100),"2.36": (75,100),"1.18": (55,90),"0.600": (35,59),"0.300": (8,30),"0.150": (0,10)},
        "Zone III": {"10.0": (100,100),"4.75": (90,100),"2.36": (85,100),"1.18": (75,90),"0.600": (60,79),"0.300": (12,40),"0.150": (0,10)},
        "Zone IV": {"10.0": (95,100),"4.75": (95,100),"2.36": (95,100),"1.18": (90,100),"0.600": (80,100),"0.300": (15,50),"0.150": (0,15)},
    }
    COARSE_LIMITS = {
        10: {"20.0": (100,100), "10.0": (85,100),    "4.75": (0,20)},
        20: {"40.0": (95,100), "20.0": (95,100), "10.0": (25,55), "4.75": (0,10)},
        40: {"80.0": (95,100), "40.0": (95,100), "20.0": (30,70), "10.0": (0,15)}
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
    
    # Load purpose profiles from JSON file
    @staticmethod
    @st.cache_data
    def load_purpose_profiles():
        try:
            purpose_profiles_path = os.path.join(SCRIPT_DIR, "data", "purpose_profiles.json")
            if os.path.exists(purpose_profiles_path):
                with open(purpose_profiles_path, 'r') as f:
                    return json.load(f)
            else:
                st.warning("Purpose profiles JSON not found. Using default profiles.")
                return CONSTANTS.get_default_purpose_profiles()
        except Exception as e:
            st.warning(f"Error loading purpose profiles: {e}. Using defaults.")
            return CONSTANTS.get_default_purpose_profiles()
    
    @staticmethod
    def get_default_purpose_profiles():
        return {
            "General": {
                "description": "A balanced, default mix. Follows IS code minimums without specific optimization bias.",
                "wb_limit": 1.0, "scm_limit": 0.5, "min_binder": 0.0,
                "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2},
                "hard_constraints": {}
            },
            "Slab": {
                "description": "Prioritizes workability and cost-effectiveness.",
                "wb_limit": 0.55, "scm_limit": 0.5, "min_binder": 300,
                "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2},
                "hard_constraints": {"max_deflection_proxy": 0.8, "min_modulus": 25000}
            },
            "Beam": {
                "description": "Prioritizes strength and durability.",
                "wb_limit": 0.50, "scm_limit": 0.4, "min_binder": 320,
                "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4},
                "hard_constraints": {"min_compressive_strength": 30, "max_shrinkage_risk": 15.0}
            },
            "Column": {
                "description": "Prioritizes high compressive strength and durability.",
                "wb_limit": 0.45, "scm_limit": 0.35, "min_binder": 340,
                "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5},
                "hard_constraints": {"min_compressive_strength": 35, "max_shrinkage_risk": 12.0}
            },
            "Pavement": {
                "description": "Prioritizes durability, flexural strength, and abrasion resistance.",
                "wb_limit": 0.45, "scm_limit": 0.4, "min_binder": 340,
                "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3},
                "hard_constraints": {"min_flexural_strength": 4.5, "fatigue_proxy_min": 0.7}
            },
            "Precast": {
                "description": "Prioritizes high early strength and surface finish.",
                "wb_limit": 0.45, "scm_limit": 0.3, "min_binder": 360,
                "weights": {"co2": 0.2, "cost": 0.5, "purpose": 0.3},
                "hard_constraints": {"min_early_strength": 15, "max_bleeding": 2.0}
            },
            "RPC/HPC": {
                "description": "High-Performance Concrete with silica fume and low w/b ratios.",
                "wb_limit": 0.35, "scm_limit": 0.25, "min_binder": 450,
                "weights": {"co2": 0.4, "cost": 0.1, "purpose": 0.5},
                "hard_constraints": {"min_strength": 60, "max_wb": 0.35, "min_silica_fume": 0.05}
            }
        }
    
    # HPC Options
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
    
    # HPC-specific constraints
    HPC_WB_RANGE = (0.25, 0.40)
    HPC_MIN_BINDER_STRENGTH = 60
    HPC_SP_MAX_LIMIT = 0.03
    HPC_MIN_FINES_CONTENT = 400
    
    CEMENT_TYPES = ["OPC 33", "OPC 43", "OPC 53", "PPC"]
    
    # Normalized names
    NORM_CEMENT = "cement"
    NORM_FLYASH = "fly ash"
    NORM_GGBS = "ggbs"
    NORM_SILICA_FUME = "silica fume"
    NORM_WATER = "water"
    NORM_SP = "pce superplasticizer"
    NORM_FINE_AGG = "fine aggregate"
    NORM_COARSE_AGG = "coarse aggregate"
    
    CHAT_REQUIRED_FIELDS = ["grade", "exposure", "target_slump", "nom_max", "cement_choice"]

# ==============================================================================
# PART 2: CACHED LOADERS & BACKEND LOGIC
# ==============================================================================

# LLM Client Initialization
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
            try:
                return pd.read_excel(p)
            except Exception:
                try:
                    return pd.read_excel(p, engine="openpyxl")
                except Exception as e:
                    st.warning(f"Failed to read {p}: {e}")
    return None

lab_df = load_default_excel(LAB_FILE)
mix_df = load_default_excel(MIX_FILE)

def _normalize_header(header):
    s = str(header).strip().lower()
    s = re.sub(r'[\-/\.\(\)]+', '_', s)
    s = re.sub(r'[^a-z0-9_]+', '', s)
    s = re.sub(r'_+', '_', s)
    return s.strip('_')

@lru_cache(maxsize=128)
def _normalize_material_value(s: str) -> str:
    if s is None:
        return ""
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
        "silica fume": CONSTANTS.NORM_SILICA_FUME, "microsilica": CONSTANTS.NORM_SILICA_FUME,
        "opc 33": "opc 33", "opc 43": "opc 43", "opc 53": "opc 53", "ppc": "ppc",
        "fly ash": CONSTANTS.NORM_FLYASH, "ggbs": CONSTANTS.NORM_GGBS, "water": CONSTANTS.NORM_WATER,
    }
    if s in synonyms:
        return synonyms[s]
    cand = get_close_matches(s, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    key2 = re.sub(r'^\d+\s*', '', s)
    cand = get_close_matches(key2, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    
    if s.startswith("opc"): return s
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
    return CONSTANTS.load_purpose_profiles()

def adjust_water_for_HPC(base_water: float, sf_frac: float, hpc_options: dict) -> float:
    if sf_frac > 0:
        multiplier = hpc_options["silica_fume"]["water_demand_multiplier"]
        return base_water * (1 + (multiplier - 1) * sf_frac)
    return base_water

def adjust_sp_for_HPC(base_sp: float, sf_frac: float, hpc_options: dict) -> float:
    if sf_frac > 0:
        boost = hpc_options["silica_fume"]["sp_effectiveness_boost"]
        return base_sp * boost
    return base_sp

def check_hpc_pumpability(fines_content: float, sp_content: float, binder_content: float) -> tuple:
    min_fines = CONSTANTS.HPC_MIN_FINES_CONTENT
    max_sp_frac = CONSTANTS.HPC_SP_MAX_LIMIT
    sp_frac = sp_content / binder_content if binder_content > 0 else 0
    
    fines_ok = fines_content >= min_fines
    sp_ok = sp_frac <= max_sp_frac
    
    return fines_ok and sp_ok, fines_ok, sp_ok

def evaluate_purpose_specific_metrics(candidate_meta: dict, purpose: str) -> dict:
    try:
        fck_target = float(candidate_meta.get('fck_target', 30.0))
        wb = float(candidate_meta.get('w_b', 0.5))
        binder = float(candidate_meta.get('cementitious', 350.0))
        water = float(candidate_meta.get('water_target', 180.0))
        sf_frac = float(candidate_meta.get('sf_frac', 0.0))
        
        if sf_frac > 0.05:
            modulus_proxy = 5500 * np.sqrt(fck_target)
        else:
            modulus_proxy = 5000 * np.sqrt(fck_target)
            
        shrinkage_risk_index = (binder * water) / 10000.0
        fatigue_proxy = (1.0 - wb) * (binder / 1000.0)
        if sf_frac > 0.02:
            fatigue_proxy *= 1.2
            
        hpc_strength_index = fck_target / (wb * 100) if wb > 0 else 0
        
        fines_content = candidate_meta.get('fine', 0) + binder * sf_frac
        sp_content = candidate_meta.get('sp', 0)
        pumpable, fines_ok, sp_ok = check_hpc_pumpability(fines_content, sp_content, binder)
        
        return {
            "estimated_modulus_proxy (MPa)": round(modulus_proxy, 0),
            "shrinkage_risk_index": round(shrinkage_risk_index, 2),
            "pavement_fatigue_proxy": round(fatigue_proxy, 2),
            "hpc_strength_efficiency": round(hpc_strength_index, 2) if sf_frac > 0 else None,
            "pumpability_assessment": "Good" if pumpable else "Marginal",
            "fines_content_ok": fines_ok,
            "sp_dosage_ok": sp_ok
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
            
        sf_frac = candidate_meta.get('sf_frac', 0.0)
        if sf_frac > 0:
            sp_frac = candidate_meta.get('sp', 0) / current_binder if current_binder > 0 else 0
            if sp_frac < 0.015:
                penalty += (0.015 - sp_frac) * 500
                
            if current_wb > 0.40:
                penalty += (current_wb - 0.40) * 200
                
        return float(max(0.0, penalty))
    except Exception:
        return 0.0

@st.cache_data
def compute_purpose_penalty_vectorized(df: pd.DataFrame, purpose_profile: dict) -> pd.Series:
    if not purpose_profile:
        return pd.Series(0.0, index=df.index)
    
    penalty = pd.Series(0.0, index=df.index)
    
    wb_limit = purpose_profile.get('wb_limit', 1.0)
    penalty += (df['w_b'] - wb_limit).clip(lower=0) * 1000
    
    scm_limit = purpose_profile.get('scm_limit', 0.5)
    penalty += (df['scm_total_frac'] - scm_limit).clip(lower=0) * 100
    
    min_binder = purpose_profile.get('min_binder', 0.0)
    penalty += (min_binder - df['binder']).clip(lower=0) * 0.1
    
    sf_frac_series = df.get('sf_frac', pd.Series(0.0, index=df.index))
    sp_frac_series = df['sp'] / df['binder'].replace(0, 1)
    
    penalty += ((0.015 - sp_frac_series).clip(lower=0) * 500 * (sf_frac_series > 0))
    penalty += ((df['w_b'] - 0.40).clip(lower=0) * 200 * (sf_frac_series > 0))
    
    return penalty.fillna(0.0)

@st.cache_data
def load_data(materials_file=None, emissions_file=None, cost_file=None):
    def _safe_read(file, default):
        if file is not None:
            try:
                if hasattr(file, 'seek'): file.seek(0)
                return pd.read_csv(file)
            except Exception as e:
                st.warning(f"Could not read uploaded file {file.name}: {e}")
                return default
        return default
    
    def _load_fallback(default_names):
        paths_to_try = [os.path.join(SCRIPT_DIR, name) for name in default_names]
        for p in paths_to_try:
            if os.path.exists(p):
                try:
                    return pd.read_csv(p)
                except Exception as e: st.warning(f"Could not read {p}: {e}")
        return None

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
                st.session_state[warning_session_key].update(new_missing)
        
        merged_df[factor_col] = merged_df[factor_col].fillna(0.0)
        return merged_df
    else:
        main_df[factor_col] = 0.0
        return main_df

def pareto_front(df, x_col="cost", y_col="co2"):
    if df.empty:
        return pd.DataFrame(columns=df.columns)
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
    return CONSTANTS.COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)

@st.cache_data
def get_coarse_agg_fraction(nom_max_mm: float, fa_zone: str, wb_ratio: float) -> float:
    base_fraction = _get_coarse_agg_fraction_base(nom_max_mm, fa_zone)
    correction = ((0.50 - wb_ratio) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return max(0.4, min(0.8, corrected_fraction))

@st.cache_data
def get_coarse_agg_fraction_vectorized(nom_max_mm: float, fa_zone: str, wb_ratio_series: pd.Series) -> pd.Series:
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
    if not results:
        return None, {}
    results_df = pd.DataFrame(results)
    mae = results_df["Error (MPa)"].abs().mean()
    rmse = np.sqrt((results_df["Error (MPa)"].clip(lower=0) ** 2).mean())
    bias = results_df["Error (MPa)"].mean()
    metrics = {"Mean Absolute Error (MPa)": mae, "Root Mean Squared Error (MPa)": rmse, "Mean Bias (MPa)": bias}
    return results_df, metrics

@st.cache_data
def simple_parse(text: str) -> dict:
    result = {}
    grade_match = re.search(r"\bM\s*([0-9]{1,3})\b", text, re.IGNORECASE)
    if grade_match:
        result["grade"] = "M" + grade_match.group(1)
    
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
        
    for purp in load_purpose_profiles().keys():
        if re.search(purp, text, re.IGNORECASE):
            result["purpose"] = purp; break

    return result

@st.cache_data(show_spinner="🤖 Parsing prompt with LLM...")
def parse_user_prompt_llm(prompt_text: str) -> dict:
    if not st.session_state.get("llm_enabled", False) or client is None:
        return simple_parse(prompt_text)

    system_prompt = f"""
    You are an expert civil engineer. Extract concrete mix design parameters from the user's prompt.
    Return ONLY a valid JSON object. Do not include any other text or explanations.
    If a value is not found, omit the key.

    Valid keys and values:
    - "grade": (String) Must be one of {list(CONSTANTS.GRADE_STRENGTH.keys())}
    - "exposure": (String) Must be one of {list(CONSTANTS.EXPOSURE_WB_LIMITS.keys())}
    - "cement_type": (String) Must be one of {CONSTANTS.CEMENT_TYPES}
    - "target_slump": (Integer) Slump in mm (e.g., 100, 125).
    - "nom_max": (Float or Integer) Must be one of [10, 12.5, 20, 40]
    - "purpose": (String) Must be one of {list(load_purpose_profiles().keys())}
    - "optimize_for": (String) Must be "CO2" or "Cost".
    - "use_superplasticizer": (Boolean)
    - "enable_hpc": (Boolean) Enable High Performance Concrete features

    User Prompt:
"I need M30 for severe marine exposure, 20mm agg, 100 slump, use PPC for a column"
    JSON:
{{"grade": "M30", "exposure": "Marine", "nom_max": 20, "target_slump": 100, "cement_type": "PPC", "purpose": "Column"}}
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
            cleaned_data["cement_choice"] = parsed_json["cement_type"]
        if parsed_json.get("nom_max") in [10, 12.5, 20, 40]:
            cleaned_data["nom_max"] = float(parsed_json["nom_max"])
        if isinstance(parsed_json.get("target_slump"), int):
            cleaned_data["target_slump"] = max(25, min(180, parsed_json["target_slump"]))
        if parsed_json.get("purpose") in load_purpose_profiles().keys():
            cleaned_data["purpose"] = parsed_json["purpose"]
        if parsed_json.get("optimize_for") in ["CO2", "Cost"]:
            cleaned_data["optimize_for"] = parsed_json["optimize_for"]
        if isinstance(parsed_json.get("use_superplasticizer"), bool):
            cleaned_data["use_sp"] = parsed_json["use_superplasticizer"]
        if isinstance(parsed_json.get("enable_hpc"), bool):
            cleaned_data["enable_hpc"] = parsed_json["enable_hpc"]
        
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
    
    df = _merge_and_warn(
        comp_df, emissions_df, "CO2_Factor(kg_CO2_per_kg)",
        "warned_emissions", "No emission factors found for"
    )
    df["CO2_Emissions (kg/m3)"] = df["Quantity (kg/m3)"] * df["CO2_Factor(kg_CO2_per_kg)"]

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
    try:
        checks["W/B ≤ exposure limit"] = float(meta["w_b"]) <= CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    except:
        checks["W/B ≤ exposure limit"] = False
    try:
        checks["Min cementitious met"] = float(meta["cementitious"]) >= float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    except:
        checks["Min cementitious met"] = False
    try:
        checks["SCM ≤ 50%"] = float(meta.get("scm_total_frac", 0.0)) <= 0.50
    except:
        checks["SCM ≤ 50%"] = False
    try:
        total_mass = float(mix_df["Quantity (kg/m3)"].sum())
        checks["Unit weight 2200–2600 kg/m³"] = 2200.0 <= total_mass <= 2600.0
    except:
        checks["Unit weight 2200–2600 kg/m³"] = False
        
    try:
        sf_frac = float(meta.get("sf_frac", 0.0))
        if sf_frac > 0:
            sp_frac = float(meta.get("sp", 0)) / float(meta["cementitious"]) if float(meta["cementitious"]) > 0 else 0
            checks["SP ≥ 1.5% for silica fume"] = sp_frac >= 0.015
            
            fines_content = float(meta.get("fine", 0)) + float(meta["cementitious"]) * sf_frac
            checks["Fines ≥ 400 kg/m³ for HPC"] = fines_content >= CONSTANTS.HPC_MIN_FINES_CONTENT
    except:
        checks["HPC specific checks"] = False
        
    derived = {
        "w/b used": round(float(meta.get("w_b", 0.0)), 3),
        "cementitious (kg/m³)": round(float(meta.get("cementitious", 0.0)), 1),
        "SCM % of cementitious": round(100 * float(meta.get("scm_total_frac", 0.0)), 1),
        "total mass (kg/m³)": round(float(mix_df["Quantity (kg/m3)"].sum()), 1) if "Quantity (kg/m3)" in mix_df.columns else None,
        "water target (kg/m³)": round(float(meta.get("water_target", 0.0)), 1),
        "cement (kg/m³)": round(float(meta.get("cement", 0.0)), 1),
        "fly ash (kg/m³)": round(float(meta.get("flyash", 0.0)), 1),
        "GGBS (kg/m³)": round(float(meta.get("ggbs", 0.0)), 1),
        "silica fume (kg/m³)": round(float(meta.get("silica_fume", 0.0)), 1),
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
        silica_fume = float(meta.get("silica_fume", 0))
        unit_wt = float(df["Quantity (kg/m3)"].sum())
    except Exception:
        return ["Insufficient data to run sanity checks."]
    
    if cement > 500: warnings.append(f"High cement content ({cement:.1f} kg/m³). Increases cost, shrinkage, and CO₂.")
    if not 140 <= water <= 220: warnings.append(f"Water content ({water:.1f} kg/m³) is outside the typical range of 140-220 kg/m³.")
    if not 500 <= fine <= 900: warnings.append(f"Fine aggregate quantity ({fine:.1f} kg/m³) is unusual.")
    if not 1000 <= coarse <= 1300: warnings.append(f"Coarse aggregate quantity ({coarse:.1f} kg/m³) is unusual.")
    if sp > 20: warnings.append(f"Superplasticizer dosage ({sp:.1f} kg/m³) is unusually high.")
    
    if silica_fume > 0:
        if silica_fume > 50: warnings.append(f"High silica fume content ({silica_fume:.1f} kg/m³). Typically 5-10% of binder.")
        sp_frac = sp / (cement + silica_fume) if (cement + silica_fume) > 0 else 0
        if sp_frac < 0.015: warnings.append(f"Low SP dosage ({sp_frac:.1%}) for silica fume mix. Recommended ≥1.5%.")
        if meta.get("w_b", 0.5) > 0.40: warnings.append(f"High w/b ratio ({meta.get('w_b', 0.5):.3f}) for silica fume mix. Consider <0.40 for optimal performance.")
        
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
    except:
        reasons.append("Failed W/B ratio check (parsing error)")
    try:
        limit, used = float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure]), float(meta["cementitious"])
        if used < limit: reasons.append(f"Cementitious below minimum ({used:.1f} kg/m³ < {limit:.1f} kg/m³)")
    except:
        reasons.append("Failed min. cementitious check (parsing error)")
    try:
        limit, used = 0.50, float(meta.get("scm_total_frac", 0.0))
        if used > limit: reasons.append(f"SCM fraction exceeds limit ({used*100:.0f}% > {limit*100:.0f}%)")
    except:
        reasons.append("Failed SCM fraction check (parsing error)")
    try:
        min_limit, max_limit = 2200.0, 2600.0
        total_mass = float(mix_df["Quantity (kg/m3)"].sum())
        if not (min_limit <= total_mass <= max_limit):
            reasons.append(f"Unit weight outside range ({total_mass:.1f} kg/m³ not in {min_limit:.0f}-{max_limit:.0f} kg/m³)")
    except:
        reasons.append("Failed unit weight check (parsing error)")
        
    try:
        sf_frac = float(meta.get("sf_frac", 0.0))
        if sf_frac > 0:
            sp_frac = float(meta.get("sp", 0)) / float(meta["cementitious"]) if float(meta["cementitious"]) > 0 else 0
            if sp_frac < 0.015:
                reasons.append(f"Insufficient SP for silica fume ({sp_frac:.1%} < 1.5%)")
                
            fines_content = float(meta.get("fine", 0)) + float(meta["cementitious"]) * sf_frac
            if fines_content < CONSTANTS.HPC_MIN_FINES_CONTENT:
                reasons.append(f"Insufficient fines for HPC pumpability ({fines_content:.0f} kg/m³ < {CONSTANTS.HPC_MIN_FINES_CONTENT} kg/m³)")
    except:
        pass
        
    feasible = len(reasons) == 0
    return feasible, "All IS-code checks passed." if feasible else "; ".join(reasons)

def get_compliance_reasons_vectorized(df: pd.DataFrame, exposure: str) -> pd.Series:
    """FIXED: Use 'fine_wet' column instead of 'fine'"""
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
    
    sf_frac_series = df.get('sf_frac', pd.Series(0.0, index=df.index))
    sp_frac_series = df['sp'] / df['binder'].replace(0, 1)
    # FIX: Use 'fine_wet' column which exists in the grid DataFrame
    fines_content_series = df['fine_wet'] + df['binder'] * sf_frac_series
    
    reasons += np.where(
        (sf_frac_series > 0) & (sp_frac_series < 0.015),
        "Insufficient SP for silica fume (" + (sp_frac_series * 100).round(1).astype(str) + "% < 1.5%); ",
        ""
    )
    reasons += np.where(
        (sf_frac_series > 0) & (fines_content_series < CONSTANTS.HPC_MIN_FINES_CONTENT),
        "Insufficient fines for HPC pumpability (" + fines_content_series.round(0).astype(str) + " kg/m³ < " + str(CONSTANTS.HPC_MIN_FINES_CONTENT) + " kg/m³); ",
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
                enable_purpose_optimization=False, enable_hpc=False, hpc_options=None,
                st_progress=None):

    if st_progress:
        st_progress.progress(0.0, text="Initializing parameters...")
    
    if enable_hpc:
        w_b_limit = min(CONSTANTS.EXPOSURE_WB_LIMITS[exposure], CONSTANTS.HPC_WB_RANGE[1])
        wb_min = max(wb_min, CONSTANTS.HPC_WB_RANGE[0])
    else:
        w_b_limit = float(CONSTANTS.EXPOSURE_WB_LIMITS[exposure])
        
    min_cem_exp = float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    target_water = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = reasonable_binder_range(grade)
    density_fa, density_ca = material_props['sg_fa'] * 1000, material_props['sg_ca'] * 1000
    
    if hpc_options is None:
        hpc_options = CONSTANTS.HPC_OPTIONS
    
    if 'warned_emissions' in st.session_state: st.session_state.warned_emissions.clear()
    if 'warned_costs' in st.session_state: st.session_state.warned_costs.clear()
                       
    if purpose_profile is None: purpose_profile = load_purpose_profiles()['General']
    if purpose_weights is None: purpose_weights = load_purpose_profiles()['General']['weights']

    if st_progress:
        st_progress.progress(0.05, text="Pre-computing cost/CO2 factors...")
    
    norm_cement_choice = _normalize_material_value(cement_choice)
    materials_to_calc = [
        norm_cement_choice, CONSTANTS.NORM_FLYASH, CONSTANTS.NORM_GGBS,
        CONSTANTS.NORM_SILICA_FUME, CONSTANTS.NORM_WATER, CONSTANTS.NORM_SP, 
        CONSTANTS.NORM_FINE_AGG, CONSTANTS.NORM_COARSE_AGG
    ]
    co2_factors, cost_factors = _get_material_factors(materials_to_calc, emissions, costs)

    if enable_hpc and CONSTANTS.NORM_SILICA_FUME not in co2_factors:
        st.warning("⚠️ Silica fume not found in materials library. Using placeholder values for HPC calculations.")
        co2_factors[CONSTANTS.NORM_SILICA_FUME] = hpc_options["silica_fume"]["co2_factor"]
        cost_factors[CONSTANTS.NORM_SILICA_FUME] = hpc_options["silica_fume"]["cost_factor"]

    if st_progress:
        st_progress.progress(0.1, text="Creating optimization grid...")
    
    wb_values = np.linspace(float(wb_min), float(w_b_limit), int(wb_steps))
    flyash_options = np.arange(0.0, max_flyash_frac + 1e-9, scm_step)
    ggbs_options = np.arange(0.0, max_ggbs_frac + 1e-9, scm_step)
    
    if enable_hpc:
        silica_fume_options = np.arange(0.0, hpc_options["silica_fume"]["max_frac"] + 1e-9, scm_step/2)
        grid_params = list(product(wb_values, flyash_options, ggbs_options, silica_fume_options))
        grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac', 'sf_frac'])
        
        grid_df = grid_df[grid_df['flyash_frac'] + grid_df['ggbs_frac'] + grid_df['sf_frac'] <= 0.50]
    else:
        grid_params = list(product(wb_values, flyash_options, ggbs_options))
        grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac'])
        grid_df['sf_frac'] = 0.0
    
    if grid_df.empty:
        return None, None, []

    if st_progress:
        st_progress.progress(0.2, text="Calculating binder properties...")
    
    grid_df['binder_for_strength'] = target_water / grid_df['wb_input']
    
    if enable_hpc:
        grid_df['water_adjusted'] = grid_df.apply(
            lambda row: adjust_water_for_HPC(target_water, row['sf_frac'], hpc_options), axis=1
        )
        grid_df['binder_for_strength'] = grid_df['water_adjusted'] / grid_df['wb_input']
    else:
        grid_df['water_adjusted'] = target_water
    
    grid_df['binder'] = np.maximum(
        np.maximum(grid_df['binder_for_strength'], min_cem_exp),
        min_b_grade
    )
    grid_df['binder'] = np.minimum(grid_df['binder'], max_b_grade)
    grid_df['w_b'] = grid_df['water_adjusted'] / grid_df['binder']
    
    grid_df['scm_total_frac'] = grid_df['flyash_frac'] + grid_df['ggbs_frac'] + grid_df['sf_frac']
    grid_df['cement'] = grid_df['binder'] * (1 - grid_df['scm_total_frac'])
    grid_df['flyash'] = grid_df['binder'] * grid_df['flyash_frac']
    grid_df['ggbs'] = grid_df['binder'] * grid_df['ggbs_frac']
    grid_df['silica_fume'] = grid_df['binder'] * grid_df['sf_frac']
    
    base_sp = (0.01 * grid_df['binder']) if use_sp else 0.0
    if enable_hpc:
        grid_df['sp'] = grid_df.apply(
            lambda row: adjust_sp_for_HPC(base_sp, row['sf_frac'], hpc_options), axis=1
        )
    else:
        grid_df['sp'] = base_sp
    
    if st_progress:
        st_progress.progress(0.3, text="Calculating aggregate proportions...")
    
    if fine_fraction_override is not None and fine_fraction_override > 0.3:
        grid_df['coarse_agg_fraction'] = 1.0 - fine_fraction_override
    else:
        grid_df['coarse_agg_fraction'] = get_coarse_agg_fraction_vectorized(nom_max, fine_zone, grid_df['w_b'])
    
    grid_df['fine_ssd'], grid_df['coarse_ssd'] = compute_aggregates_vectorized(
        grid_df['binder'], grid_df['water_adjusted'], grid_df['sp'], grid_df['coarse_agg_fraction'],
        nom_max, density_fa, density_ca
    )
    
    water_delta_fa_series, grid_df['fine_wet'] = aggregate_correction_vectorized(
        material_props['moisture_fa'], grid_df['fine_ssd']
    )
    water_delta_ca_series, grid_df['coarse_wet'] = aggregate_correction_vectorized(
        material_props['moisture_ca'], grid_df['coarse_ssd']
    )
    
    grid_df['water_final'] = (grid_df['water_adjusted'] - (water_delta_fa_series + water_delta_ca_series)).clip(lower=5.0)

    if st_progress:
        st_progress.progress(0.5, text="Calculating cost and CO2...")
    
    grid_df['co2_total'] = (
        grid_df['cement'] * co2_factors.get(norm_cement_choice, 0.0) +
        grid_df['flyash'] * co2_factors.get(CONSTANTS.NORM_FLYASH, 0.0) +
        grid_df['ggbs'] * co2_factors.get(CONSTANTS.NORM_GGBS, 0.0) +
        grid_df['silica_fume'] * co2_factors.get(CONSTANTS.NORM_SILICA_FUME, 0.0) +
        grid_df['water_final'] * co2_factors.get(CONSTANTS.NORM_WATER, 0.0) +
        grid_df['sp'] * co2_factors.get(CONSTANTS.NORM_SP, 0.0) +
        grid_df['fine_wet'] * co2_factors.get(CONSTANTS.NORM_FINE_AGG, 0.0) +
        grid_df['coarse_wet'] * co2_factors.get(CONSTANTS.NORM_COARSE_AGG, 0.0)
    )
    
    grid_df['cost_total'] = (
        grid_df['cement'] * cost_factors.get(norm_cement_choice, 0.0) +
        grid_df['flyash'] * cost_factors.get(CONSTANTS.NORM_FLYASH, 0.0) +
        grid_df['ggbs'] * cost_factors.get(CONSTANTS.NORM_GGBS, 0.0) +
        grid_df['silica_fume'] * cost_factors.get(CONSTANTS.NORM_SILICA_FUME, 0.0) +
        grid_df['water_final'] * cost_factors.get(CONSTANTS.NORM_WATER, 0.0) +
        grid_df['sp'] * cost_factors.get(CONSTANTS.NORM_SP, 0.0) +
        grid_df['fine_wet'] * cost_factors.get(CONSTANTS.NORM_FINE_AGG, 0.0) +
        grid_df['coarse_wet'] * cost_factors.get(CONSTANTS.NORM_COARSE_AGG, 0.0)
    )

    if st_progress:
        st_progress.progress(0.7, text="Checking compliance and purpose-fit...")
    
    grid_df['total_mass'] = (
        grid_df['cement'] + grid_df['flyash'] + grid_df['ggbs'] + grid_df['silica_fume'] +
        grid_df['water_final'] + grid_df['sp'] + 
        grid_df['fine_wet'] + grid_df['coarse_wet']
    )
    
    grid_df['check_wb'] = grid_df['w_b'] <= w_b_limit
    grid_df['check_min_cem'] = grid_df['binder'] >= min_cem_exp
    grid_df['check_scm'] = grid_df['scm_total_frac'] <= 0.50
    grid_df['check_unit_wt'] = (grid_df['total_mass'] >= 2200.0) & (grid_df['total_mass'] <= 2600.0)
    
    if enable_hpc:
        # FIX: Use 'fine_wet' column which exists
        grid_df['fines_content'] = grid_df['fine_wet'] + grid_df['binder'] * grid_df['sf_frac']
        grid_df['sp_frac'] = grid_df['sp'] / grid_df['binder'].replace(0, 1)
        grid_df['check_hpc_fines'] = grid_df['fines_content'] >= CONSTANTS.HPC_MIN_FINES_CONTENT
        grid_df['check_hpc_sp'] = grid_df['sp_frac'] >= 0.015
        grid_df['feasible'] = (
            grid_df['check_wb'] & grid_df['check_min_cem'] &
            grid_df['check_scm'] & grid_df['check_unit_wt'] &
            grid_df['check_hpc_fines'] & grid_df['check_hpc_sp']
        )
    else:
        grid_df['feasible'] = (
            grid_df['check_wb'] & grid_df['check_min_cem'] &
            grid_df['check_scm'] & grid_df['check_unit_wt']
        )
    
    # FIXED: This was causing the KeyError - now uses correct column names
    grid_df['reasons'] = get_compliance_reasons_vectorized(grid_df, exposure)
    grid_df['purpose_penalty'] = compute_purpose_penalty_vectorized(grid_df, purpose_profile)
    grid_df['purpose'] = purpose
    grid_df['enable_hpc'] = enable_hpc

    if st_progress:
        st_progress.progress(0.8, text="Finding best mix design...")
    
    feasible_candidates_df = grid_df[grid_df['feasible']].copy()
    
    if feasible_candidates_df.empty:
        trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
        return None, None, trace_df.to_dict('records')

    if not enable_purpose_optimization or purpose == 'General':
        objective_col = 'cost_total' if optimize_cost else 'co2_total'
        feasible_candidates_df['composite_score'] = np.nan
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

    if st_progress:
        st_progress.progress(0.9, text="Generating final mix report...")
    
    best_mix_dict = {
        cement_choice: best_meta_series['cement'],
        "Fly Ash": best_meta_series['flyash'],
        "GGBS": best_meta_series['ggbs'],
        "Water": best_meta_series['water_final'],
        "PCE Superplasticizer": best_meta_series['sp'],
        "Fine Aggregate": best_meta_series['fine_wet'],
        "Coarse Aggregate": best_meta_series['coarse_wet']
    }
    
    if enable_hpc and best_meta_series['sf_frac'] > 0:
        best_mix_dict["Silica Fume"] = best_meta_series['silica_fume']
    
    best_df = evaluate_mix(best_mix_dict, emissions, costs)
    
    best_meta = best_meta_series.to_dict()
    best_meta.update({
        "cementitious": best_meta_series['binder'],
        "water_target": target_water,
        "water_adjusted": best_meta_series.get('water_adjusted', target_water),
        "fine": best_meta_series['fine_wet'],  # Map fine_wet to fine for compatibility
        "coarse": best_meta_series['coarse_wet'],
        "silica_fume": best_meta_series.get('silica_fume', 0.0),
        "sf_frac": best_meta_series.get('sf_frac', 0.0),
        "grade": grade, "exposure": exposure, "nom_max": nom_max,
        "slump": target_slump, "binder_range": (min_b_grade, max_b_grade),
        "material_props": material_props,
        "enable_hpc": enable_hpc,
        "purpose_metrics": evaluate_purpose_specific_metrics(best_meta, purpose)
    })
    
    trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
    
    score_cols = ['composite_score', 'norm_co2', 'norm_cost', 'norm_purpose']
    if all(col in feasible_candidates_df.columns for col in score_cols):
        scores_to_merge = feasible_candidates_df[score_cols]
        trace_df = trace_df.merge(scores_to_merge, left_index=True, right_index=True, how='left')
    
    return best_df, best_meta, trace_df.to_dict('records')

# ... (rest of the functions remain the same as in your original code)
# The remaining functions (generate_baseline, apply_parser, display functions, etc.)
# are identical to your original implementation

def generate_baseline(grade, exposure, nom_max, target_slump, agg_shape, 
                     fine_zone, emissions, costs, cement_choice, material_props, 
                     use_sp=True, sp_reduction=0.18,
                     purpose='General', purpose_profile=None, enable_hpc=False):
    
    w_b_limit = float(CONSTANTS.EXPOSURE_WB_LIMITS[exposure])
    min_cem_exp = float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    water_target = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = reasonable_binder_range(grade)

    binder_for_wb = water_target / w_b_limit
    cementitious = min(max(binder_for_wb, min_cem_exp, min_b_grade), max_b_grade)
    actual_wb = water_target / cementitious
    sp = 0.01 * cementitious if use_sp else 0.0
    coarse_agg_frac = get_coarse_agg_fraction(nom_max, fine_zone, actual_wb)
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
        "binder_range": (min_b_grade, max_b_grade),
        "enable_hpc": enable_hpc
    }
    
    if purpose_profile is None:
        purpose_profile = load_purpose_profiles().get(purpose, load_purpose_profiles()['General'])
        
    meta.update({
        "purpose": purpose,
        "purpose_metrics": evaluate_purpose_specific_metrics(meta, purpose),
        "purpose_penalty": compute_purpose_penalty(meta, purpose_profile),
        "composite_score": np.nan
    })
    return df, meta

# ... (rest of the UI and main application code remains the same)
# The chat interface, manual interface, and main() function are identical to your original implementation

def main():
    st.set_page_config(
        page_title="CivilGPT - Sustainable Concrete Mix Designer",
        page_icon="🧱",
        layout="wide"
    )

    # Custom CSS
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
        .mode-card {
            background-color: #1E1E1E;
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
            color: #FFFFFF;
            margin-top: 0;
            margin-bottom: 5px;
        }
        .mode-card p {
            color: #CCCCCC;
            font-size: 0.85em;
            margin-bottom: 10px;
        }
    </style>
    """, unsafe_allow_html=True)

    # State initialization
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
    if "manual_tabs" not in st.session_state:
        st.session_state.manual_tabs = "📊 **Overview**"

    purpose_profiles_data = load_purpose_profiles()

    # Sidebar setup
    st.sidebar.title("Mode Selection")

    if "llm_init_message" in st.session_state:
        msg_type, msg_content = st.session_state.pop("llm_init_message")
        if msg_type == "success": st.sidebar.success(msg_content, icon="🤖")
        elif msg_type == "info": st.sidebar.info(msg_content, icon="ℹ️")
        elif msg_type == "warning": st.sidebar.warning(msg_content, icon="⚠️")

    llm_is_ready = st.session_state.get("llm_enabled", False)
    
    with st.sidebar:
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

        st.markdown(f"""
        <div class="mode-card">
            <h4 style='display: flex; align-items: center;'>
                <span style='font-size: 1.2em; margin-right: 10px;'>{card_icon}</span>
                {card_title}
            </h4>
            <p>{card_desc}</p>
        </div>
        """, unsafe_allow_html=True)
        
        chat_mode = st.toggle(
            f"Switch to {'Manual' if is_chat_mode else 'Chat'} Mode",
            value=st.session_state.get("chat_mode") if llm_is_ready else False,
            key="chat_mode_toggle_functional",
            help="Toggle to switch between conversational and manual input interfaces." if llm_is_ready else "Chat Mode requires a valid GROQ_API_KEY.",
            disabled=not llm_is_ready,
            label_visibility="collapsed"
        )
        st.session_state.chat_mode = chat_mode
        
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

    materials_df, emissions_df, costs_df = load_data(
        st.session_state.get("materials_csv"), 
        st.session_state.get("emissions_csv"), 
        st.session_state.get("cost_csv")
    )

    # Chat-triggered generation
    if st.session_state.get('run_chat_generation', False):
        st.session_state.run_chat_generation = False
        
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
            "calibration_kwargs": {},
            **chat_inputs
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
                st_progress=None
            )

    # Render UI
    if chat_mode:
        run_chat_interface(purpose_profiles_data)
    else:
        run_manual_interface(purpose_profiles_data, materials_df, emissions_df, costs_df)

# Note: The run_chat_interface and run_manual_interface functions 
# remain exactly as in your original code - they weren't causing the error

if __name__ == "__main__":
    main()
