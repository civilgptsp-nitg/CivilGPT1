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
    
    PURPOSE_PROFILES = {
        "General": {
            "description": "A balanced, default mix. Follows IS code minimums without specific optimization bias.",
            "wb_limit": 1.0, 
            "scm_limit": 0.5, 
            "min_binder": 0.0,
            "max_binder": 600.0,
            "target_slump_range": (50, 150),
            "min_fines_content": 300,
            "max_sp_frac": 0.03,
            "preferred_scm_types": ["flyash", "ggbs"],
            "strength_priority": "medium",
            "durability_priority": "medium",
            "workability_priority": "medium",
            "cost_priority": "medium",
            "sustainability_priority": "medium",
            "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2}
        },
        "Slab": {
            "description": "Prioritizes workability (slump) and cost-effectiveness. Strength is often not the primary driver.",
            "wb_limit": 0.55, 
            "scm_limit": 0.5, 
            "min_binder": 300,
            "max_binder": 450,
            "target_slump_range": (75, 150),
            "min_fines_content": 350,
            "max_sp_frac": 0.025,
            "preferred_scm_types": ["flyash"],
            "strength_priority": "low",
            "durability_priority": "medium",
            "workability_priority": "high",
            "cost_priority": "high",
            "sustainability_priority": "medium",
            "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2}
        },
        "Beam": {
            "description": "Prioritizes strength (modulus) and durability. Often heavily reinforced.",
            "wb_limit": 0.50, 
            "scm_limit": 0.4, 
            "min_binder": 320,
            "max_binder": 500,
            "target_slump_range": (75, 125),
            "min_fines_content": 380,
            "max_sp_frac": 0.03,
            "preferred_scm_types": ["ggbs", "flyash"],
            "strength_priority": "high",
            "durability_priority": "high",
            "workability_priority": "medium",
            "cost_priority": "low",
            "sustainability_priority": "medium",
            "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4}
        },
        "Column": {
            "description": "Prioritizes high compressive strength and durability. Congestion is common.",
            "wb_limit": 0.45, 
            "scm_limit": 0.35, 
            "min_binder": 340,
            "max_binder": 550,
            "target_slump_range": (100, 175),
            "min_fines_content": 400,
            "max_sp_frac": 0.035,
            "preferred_scm_types": ["ggbs"],
            "strength_priority": "very_high",
            "durability_priority": "very_high",
            "workability_priority": "high",
            "cost_priority": "low",
            "sustainability_priority": "medium",
            "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5}
        },
        "Pavement": {
            "description": "Prioritizes durability, flexural strength (fatigue), and abrasion resistance. Cost is a major factor.",
            "wb_limit": 0.45, 
            "scm_limit": 0.4, 
            "min_binder": 340,
            "max_binder": 480,
            "target_slump_range": (25, 75),
            "min_fines_content": 370,
            "max_sp_frac": 0.02,
            "preferred_scm_types": ["flyash"],
            "strength_priority": "high",
            "durability_priority": "very_high",
            "workability_priority": "low",
            "cost_priority": "high",
            "sustainability_priority": "medium",
            "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3}
        },
        "Precast": {
            "description": "Prioritizes high early strength (for form stripping), surface finish, and cost (reproducibility).",
            "wb_limit": 0.45, 
            "scm_limit": 0.3, 
            "min_binder": 360,
            "max_binder": 520,
            "target_slump_range": (50, 100),
            "min_fines_content": 390,
            "max_sp_frac": 0.03,
            "preferred_scm_types": [],
            "strength_priority": "high",
            "durability_priority": "medium",
            "workability_priority": "medium",
            "cost_priority": "high",
            "sustainability_priority": "low",
            "weights": {"co2": 0.2, "cost": 0.5, "purpose": 0.3}
        },
        "RPC/HPC": {
            "description": "High-Performance Concrete with silica fume, very low w/b ratios, and high strength (>M60).",
            "wb_limit": 0.35, 
            "scm_limit": 0.25, 
            "min_binder": 450,
            "max_binder": 800,
            "target_slump_range": (200, 250),
            "min_fines_content": 450,
            "max_sp_frac": 0.05,
            "preferred_scm_types": ["silica_fume", "ggbs"],
            "strength_priority": "very_high",
            "durability_priority": "very_high",
            "workability_priority": "high",
            "cost_priority": "very_low",
            "sustainability_priority": "low",
            "weights": {"co2": 0.4, "cost": 0.1, "purpose": 0.5}
        }
    }
    
    PRIORITY_WEIGHTS = {
        "very_low": 0.2,
        "low": 0.4,
        "medium": 0.6,
        "high": 0.8,
        "very_high": 1.0
    }
    
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
    HPC_MIN_BINDER_STRENGTH = 60
    HPC_SP_MAX_LIMIT = 0.05  # Increased from 0.03 to 0.05 for HPC flexibility
    HPC_MIN_FINES_CONTENT = 400
    
    CEMENT_TYPES = ["OPC 33", "OPC 43", "OPC 53", "PPC"]
    
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
    return CONSTANTS.PURPOSE_PROFILES

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
        purpose_profile = CONSTANTS.PURPOSE_PROFILES.get(purpose, CONSTANTS.PURPOSE_PROFILES["General"])
        
        fck_target = float(candidate_meta.get('fck_target', 30.0))
        wb = float(candidate_meta.get('w_b', 0.5))
        binder = float(candidate_meta.get('cementitious', 350.0))
        water = float(candidate_meta.get('water_target', 180.0))
        sf_frac = float(candidate_meta.get('sf_frac', 0.0))
        slump = float(candidate_meta.get('slump', 100.0))
        fines_content = float(candidate_meta.get('fine', 0)) + binder * sf_frac
        sp_content = float(candidate_meta.get('sp', 0.0))
        sp_frac = sp_content / binder if binder > 0 else 0
        
        if sf_frac > 0.05:
            modulus_proxy = 5700 * np.sqrt(fck_target)
        else:
            modulus_proxy = 5000 * np.sqrt(fck_target)
            
        shrinkage_risk_index = (binder * water) / 10000.0
        
        fatigue_proxy = (1.0 - wb) * (binder / 1000.0)
        if sf_frac > 0.02:
            fatigue_proxy *= 1.2
            
        hpc_strength_index = fck_target / (wb * 100) if wb > 0 else 0
        
        pumpable, fines_ok, sp_ok = check_hpc_pumpability(fines_content, sp_content, binder)
        
        target_slump_min, target_slump_max = purpose_profile.get('target_slump_range', (50, 150))
        slump_deviation = max(0, target_slump_min - slump, slump - target_slump_max)
        workability_score = max(0, 100 - slump_deviation * 2)
        
        strength_efficiency = fck_target / (binder / 100) if binder > 0 else 0
        
        durability_index = (0.6 - wb) * 100 + min(50, binder - 300) * 0.1
        
        cost_per_mpa = candidate_meta.get('cost_total', 0) / fck_target if fck_target > 0 else 0
        
        co2_per_mpa = candidate_meta.get('co2_total', 0) / fck_target if fck_target > 0 else 0
        sustainability_score = max(0, 100 - co2_per_mpa * 2)
        
        compliance_score = 100
        if wb > purpose_profile.get('wb_limit', 1.0):
            compliance_score -= (wb - purpose_profile['wb_limit']) * 100
        scm_total = candidate_meta.get('scm_total_frac', 0.0)
        if scm_total > purpose_profile.get('scm_limit', 0.5):
            compliance_score -= (scm_total - purpose_profile['scm_limit']) * 50
        if binder < purpose_profile.get('min_binder', 0.0):
            compliance_score -= (purpose_profile['min_binder'] - binder) * 0.5
        if binder > purpose_profile.get('max_binder', 600.0):
            compliance_score -= (binder - purpose_profile['max_binder']) * 0.2
        if fines_content < purpose_profile.get('min_fines_content', 300):
            compliance_score -= (purpose_profile['min_fines_content'] - fines_content) * 0.1
        if sp_frac > purpose_profile.get('max_sp_frac', 0.03):
            compliance_score -= (sp_frac - purpose_profile['max_sp_frac']) * 500
            
        compliance_score = max(0, compliance_score)
        
        return {
            "estimated_modulus_proxy (MPa)": round(modulus_proxy, 0),
            "shrinkage_risk_index": round(shrinkage_risk_index, 2),
            "pavement_fatigue_proxy": round(fatigue_proxy, 2),
            "hpc_strength_efficiency": round(hpc_strength_index, 2) if sf_frac > 0 else None,
            "pumpability_assessment": "Good" if pumpable else "Marginal",
            "fines_content_ok": fines_ok,
            "sp_dosage_ok": sp_ok,
            "workability_score": round(workability_score, 1),
            "strength_efficiency": round(strength_efficiency, 2),
            "durability_index": round(durability_index, 1),
            "cost_efficiency": round(cost_per_mpa, 2),
            "sustainability_score": round(sustainability_score, 1),
            "purpose_compliance_score": round(compliance_score, 1)
        }
    except Exception as e:
        return {
            "estimated_modulus_proxy (MPa)": None, 
            "shrinkage_risk_index": None, 
            "pavement_fatigue_proxy": None,
            "error": str(e)
        }

def compute_purpose_penalty(candidate_meta: dict, purpose_profile: dict) -> float:
    if not purpose_profile: 
        return 0.0
    
    penalty = 0.0
    try:
        wb_limit = purpose_profile.get('wb_limit', 1.0)
        current_wb = float(candidate_meta.get('w_b', 0.5))
        scm_limit = purpose_profile.get('scm_limit', 0.5)
        current_scm = float(candidate_meta.get('scm_total_frac', 0.0))
        min_binder = purpose_profile.get('min_binder', 0.0)
        max_binder = purpose_profile.get('max_binder', 600.0)
        current_binder = float(candidate_meta.get('cementitious', 300.0))
        target_slump_min, target_slump_max = purpose_profile.get('target_slump_range', (50, 150))
        current_slump = float(candidate_meta.get('slump', 100.0))
        min_fines_content = purpose_profile.get('min_fines_content', 300)
        current_fines = float(candidate_meta.get('fine', 0)) + current_binder * float(candidate_meta.get('sf_frac', 0.0))
        max_sp_frac = purpose_profile.get('max_sp_frac', 0.03)
        current_sp_frac = float(candidate_meta.get('sp', 0)) / current_binder if current_binder > 0 else 0
        
        # CHANGE 1: Dynamic priority-based scaling for w/b penalty
        strength_weight = CONSTANTS.PRIORITY_WEIGHTS[purpose_profile['strength_priority']]
        if current_wb > wb_limit:
            excess_wb = current_wb - wb_limit
            penalty += excess_wb * 2000 * strength_weight
        
        # CHANGE 2: Graduated penalty scaling for SCM excess
        if current_scm > scm_limit:
            excess_scm = current_scm - scm_limit
            if excess_scm <= 0.05:
                penalty += excess_scm * 200  # Minor violation
            elif excess_scm <= 0.10:
                penalty += excess_scm * 500  # Moderate violation  
            else:
                penalty += excess_scm * 1000  # Severe violation
        
        if current_binder < min_binder:
            deficit_binder = min_binder - current_binder
            penalty += deficit_binder * 2
        elif current_binder > max_binder:
            excess_binder = current_binder - max_binder
            penalty += excess_binder * 0.5
        
        if current_slump < target_slump_min:
            slump_deficit = target_slump_min - current_slump
            penalty += slump_deficit * 1.5
        elif current_slump > target_slump_max:
            slump_excess = current_slump - target_slump_max
            penalty += slump_excess * 1.0
        
        if current_fines < min_fines_content:
            fines_deficit = min_fines_content - current_fines
            penalty += fines_deficit * 0.3
        
        if current_sp_frac > max_sp_frac:
            sp_excess = current_sp_frac - max_sp_frac
            penalty += sp_excess * 1000
        
        sf_frac = float(candidate_meta.get('sf_frac', 0.0))
        if sf_frac > 0:
            if current_sp_frac < 0.015:
                penalty += (0.015 - current_sp_frac) * 2000
                
            if current_wb > 0.40:
                penalty += (current_wb - 0.40) * 1000
                
            if current_fines < 400:
                penalty += (400 - current_fines) * 0.5
        
        strength_priority = purpose_profile.get('strength_priority', 'medium')
        durability_priority = purpose_profile.get('durability_priority', 'medium')
        workability_priority = purpose_profile.get('workability_priority', 'medium')
        cost_priority = purpose_profile.get('cost_priority', 'medium')
        sustainability_priority = purpose_profile.get('sustainability_priority', 'medium')
        
        strength_weight = CONSTANTS.PRIORITY_WEIGHTS.get(strength_priority, 0.6)
        durability_weight = CONSTANTS.PRIORITY_WEIGHTS.get(durability_priority, 0.6)
        workability_weight = CONSTANTS.PRIORITY_WEIGHTS.get(workability_priority, 0.6)
        cost_weight = CONSTANTS.PRIORITY_WEIGHTS.get(cost_priority, 0.6)
        sustainability_weight = CONSTANTS.PRIORITY_WEIGHTS.get(sustainability_priority, 0.6)
        
        strength_efficiency = float(candidate_meta.get('fck_target', 30.0)) / (current_binder / 100) if current_binder > 0 else 0
        if strength_efficiency < 0.3:
            penalty += (0.3 - strength_efficiency) * 500 * strength_weight
        
        if current_wb > 0.5:
            penalty += (current_wb - 0.5) * 300 * durability_weight
        
        target_slump_ideal = (target_slump_min + target_slump_max) / 2
        slump_deviation = abs(current_slump - target_slump_ideal)
        penalty += slump_deviation * 0.5 * workability_weight
        
        current_cost = float(candidate_meta.get('cost_total', 0))
        if current_cost > 5000:
            penalty += (current_cost - 5000) * 0.01 * cost_weight
        
        current_co2 = float(candidate_meta.get('co2_total', 0))
        if current_co2 > 400:
            penalty += (current_co2 - 400) * 0.1 * sustainability_weight
            
        return float(max(0.0, penalty))
        
    except Exception as e:
        return 1000.0

@st.cache_data
def compute_purpose_penalty_vectorized(df: pd.DataFrame, purpose_profile: dict) -> pd.Series:
    if not purpose_profile:
        return pd.Series(0.0, index=df.index)
    
    penalty = pd.Series(0.0, index=df.index)
    
    wb_limit = purpose_profile.get('wb_limit', 1.0)
    scm_limit = purpose_profile.get('scm_limit', 0.5)
    min_binder = purpose_profile.get('min_binder', 0.0)
    max_binder = purpose_profile.get('max_binder', 600.0)
    target_slump_min, target_slump_max = purpose_profile.get('target_slump_range', (50, 150))
    min_fines_content = purpose_profile.get('min_fines_content', 300)
    max_sp_frac = purpose_profile.get('max_sp_frac', 0.03)
    
    strength_priority = purpose_profile.get('strength_priority', 'medium')
    durability_priority = purpose_profile.get('durability_priority', 'medium')
    workability_priority = purpose_profile.get('workability_priority', 'medium')
    cost_priority = purpose_profile.get('cost_priority', 'medium')
    sustainability_priority = purpose_profile.get('sustainability_priority', 'medium')
    
    strength_weight = CONSTANTS.PRIORITY_WEIGHTS.get(strength_priority, 0.6)
    durability_weight = CONSTANTS.PRIORITY_WEIGHTS.get(durability_priority, 0.6)
    workability_weight = CONSTANTS.PRIORITY_WEIGHTS.get(workability_priority, 0.6)
    cost_weight = CONSTANTS.PRIORITY_WEIGHTS.get(cost_priority, 0.6)
    sustainability_weight = CONSTANTS.PRIORITY_WEIGHTS.get(sustainability_priority, 0.6)
    
    # CHANGE 1: Dynamic priority-based scaling for w/b penalty
    penalty += (df['w_b'] - wb_limit).clip(lower=0) * 2000 * strength_weight
    
    # CHANGE 2: Graduated penalty scaling for SCM excess
    excess_scm = (df['scm_total_frac'] - scm_limit).clip(lower=0)
    scm_penalty = np.where(
        excess_scm <= 0.05, excess_scm * 200,
        np.where(
            excess_scm <= 0.10, excess_scm * 500,
            excess_scm * 1000
        )
    )
    penalty += scm_penalty
    
    penalty += (min_binder - df['binder']).clip(lower=0) * 2
    penalty += (df['binder'] - max_binder).clip(lower=0) * 0.5
    
    if 'target_slump' in df.columns:
        target_slump_series = df['target_slump']
    else:
        target_slump_series = pd.Series((target_slump_min + target_slump_max) / 2, index=df.index)
    
    penalty += ((target_slump_min - target_slump_series).clip(lower=0) * 1.5 +
               (target_slump_series - target_slump_max).clip(lower=0) * 1.0)
    
    sf_frac_series = df.get('sf_frac', pd.Series(0.0, index=df.index))
    fines_content_series = df['fine_wet'] + df['binder'] * sf_frac_series
    penalty += (min_fines_content - fines_content_series).clip(lower=0) * 0.3
    
    sp_frac_series = df['sp'] / df['binder'].replace(0, 1)
    penalty += (sp_frac_series - max_sp_frac).clip(lower=0) * 1000
    
    penalty += ((0.015 - sp_frac_series).clip(lower=0) * 2000 * (sf_frac_series > 0))
    penalty += ((df['w_b'] - 0.40).clip(lower=0) * 1000 * (sf_frac_series > 0))
    penalty += ((400 - fines_content_series).clip(lower=0) * 0.5 * (sf_frac_series > 0))
    
    # CHANGE 3: SCM Type Preference Enforcement
    preferred_scm = purpose_profile.get('preferred_scm_types', [])
    if len(preferred_scm) > 0:
        # Check for non-preferred SCM types being used
        uses_non_preferred = pd.Series(False, index=df.index)
        
        if 'flyash' not in preferred_scm:
            uses_non_preferred |= (df['flyash_frac'] > 0)
        if 'ggbs' not in preferred_scm:
            uses_non_preferred |= (df['ggbs_frac'] > 0)
        if 'silica_fume' not in preferred_scm:
            uses_non_preferred |= (df['sf_frac'] > 0)
            
        penalty += uses_non_preferred * 200  # Penalty for using non-preferred SCM types
    
    if 'fck_target' not in df.columns and 'grade' in df.columns:
        try:
            grade_str = df['grade'].iloc[0] if len(df) > 0 else "M30"
            fck_value = CONSTANTS.GRADE_STRENGTH.get(grade_str, 30.0)
            S_value = CONSTANTS.QC_STDDEV.get("Good", 5.0)
            fck_target_value = fck_value + 1.65 * S_value
            strength_efficiency_series = pd.Series(fck_target_value, index=df.index) / (df['binder'] / 100).replace(0, 1)
        except:
            strength_efficiency_series = pd.Series(0.3, index=df.index)
    elif 'fck_target' in df.columns:
        strength_efficiency_series = df['fck_target'] / (df['binder'] / 100).replace(0, 1)
    else:
        strength_efficiency_series = pd.Series(0.3, index=df.index)
    
    penalty += ((0.3 - strength_efficiency_series).clip(lower=0) * 500 * strength_weight)
    
    penalty += ((df['w_b'] - 0.5).clip(lower=0) * 300 * durability_weight)
    
    workability_penalty = (df['w_b'] - 0.4).clip(lower=0) * 100 * workability_weight
    penalty += workability_penalty
    
    if 'cost_total' in df.columns:
        penalty += ((df['cost_total'] - 5000).clip(lower=0) * 0.01 * cost_weight)
    
    if 'co2_total' in df.columns:
        penalty += ((df['co2_total'] - 400).clip(lower=0) * 0.1 * sustainability_weight)
    
    return penalty.fillna(1000.0)

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
                except Exception as e: 
                    st.warning(f"Could not read {p}: {e}")
        return None

    materials = _safe_read(materials_file, _load_fallback(["materials_library.csv", "data/materials_library.csv"]))
    emissions = _safe_read(emissions_file, _load_fallback(["emission_factors.csv", "data/emission_factors.csv"]))
    costs = _safe_read(cost_file, _load_fallback(["cost_factors.csv", "data/cost_factors.csv"]))

    # Defensive handling for each dataframe
    try:
        materials = _normalize_columns(materials, CONSTANTS.MATERIALS_COL_MAP)
        if materials is not None and not materials.empty and "Material" in materials.columns:
            materials["Material"] = materials["Material"].astype(str).str.strip()
    except Exception as e:
        st.warning(f"Error processing materials data: {e}")
    
    if materials is None or materials.empty or "Material" not in materials.columns:
        st.warning("Could not load 'materials_library.csv'. Using empty library.", icon="ℹ️")
        materials = pd.DataFrame(columns=list(dict.fromkeys(CONSTANTS.MATERIALS_COL_MAP.values())))

    try:
        emissions = _normalize_columns(emissions, CONSTANTS.EMISSIONS_COL_MAP)
        if emissions is not None and not emissions.empty and "Material" in emissions.columns:
            emissions["Material"] = emissions["Material"].astype(str).str.strip()
    except Exception as e:
        st.warning(f"Error processing emissions data: {e}")
    
    if emissions is None or emissions.empty or "Material" not in emissions.columns or "CO2_Factor(kg_CO2_per_kg)" not in emissions.columns:
        st.warning("⚠️ Could not load 'emission_factors.csv'. CO2 calculations will be zero.")
        emissions = pd.DataFrame(columns=list(dict.fromkeys(CONSTANTS.EMISSIONS_COL_MAP.values())))
                                                                                                     
    try:
        costs = _normalize_columns(costs, CONSTANTS.COSTS_COL_MAP)
        if costs is not None and not costs.empty and "Material" in costs.columns:
            costs["Material"] = costs["Material"].astype(str).str.strip()  # FIXED: astize -> astype
    except Exception as e:
        st.warning(f"Error processing costs data: {e}")
    
    if costs is None or costs.empty or "Material" not in costs.columns or "Cost(₹/kg)" not in costs.columns:
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

def pareto_front(df, x_col="cost", y_col="co2", z_col="purpose_penalty"):
    if df.empty:
        return pd.DataFrame(columns=df.columns)
    
    sorted_df = df.sort_values(by=[x_col, y_col, z_col], ascending=[True, True, True])
    pareto_points = []
    
    for _, row in sorted_df.iterrows():
        dominated = False
        for pareto_point in pareto_points:
            if (pareto_point[x_col] <= row[x_col] and 
                pareto_point[y_col] <= row[y_col] and 
                pareto_point[z_col] <= row[z_col] and
                (pareto_point[x_col] < row[x_col] or 
                 pareto_point[y_col] < row[y_col] or 
                 pareto_point[z_col] < row[z_col])):
                dominated = True
                break
                
        if not dominated:
            pareto_points = [p for p in pareto_points if not (
                row[x_col] <= p[x_col] and 
                row[y_col] <= p[y_col] and 
                row[z_col] <= p[z_col] and
                (row[x_col] < p[x_col] or 
                 row[y_col] < p[y_col] or 
                 row[z_col] < p[z_col])
            )]
            pareto_points.append(row)
    
    if not pareto_points:
        return pd.DataFrame(columns=df.columns)
    
    return pd.DataFrame(pareto_points).reset_index(drop=True)

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
        
    for purp in CONSTANTS.PURPOSE_PROFILES.keys():
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
    - "exposure": (String) Must be one of {list(CONSTANTS.EXPOSURE_WB_LIMITS.keys())}. "Marine" takes precedence over "Severe".
    - "cement_type": (String) Must be one of {CONSTANTS.CEMENT_TYPES}
    - "target_slump": (Integer) Slump in mm (e.g., 100, 125).
    - "nom_max": (Float or Integer) Must be one of [10, 12.5, 20, 40]
    - "purpose": (String) Must be one of {list(CONSTANTS.PURPOSE_PROFILES.keys())}
    - "optimize_for": (String) Must be "CO2" or "Cost".
    - "use_superplasticizer": (Boolean)
    - "enable_hpc": (Boolean) Enable High Performance Concrete features

    User Prompt:
"I need M30 for severe marine exposure, 20mm agg, 100 slump, use PPC for a column"
    JSON:
{{"grade": "M30", "exposure": "Marine", "nom_max": 20, "target_slump": 100, "cement_type": "PPC", "purpose": "Column"}}
    """
    
    try:
        # Primary model attempt
        resp = client.chat.completions.create(
            model="llama3-70b-8192",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt_text}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        content = resp.choices[0].message.content
        parsed_json = json.loads(content)
        
    except Exception as e:
        st.warning(f"Primary model (llama3-70b-8192) failed: {e}. Trying fallback model...")
        try:
            # Fallback model attempt
            resp = client.chat.completions.create(
                model="gemma2-9b-it",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = resp.choices[0].message.content
            parsed_json = json.loads(content)
        except Exception as e2:
            st.error(f"LLM Parser Error with fallback model: {e2}. Falling back to regex.")
            return simple_parse(prompt_text)
    
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
    if parsed_json.get("purpose") in CONSTANTS.PURPOSE_PROFILES:
        cleaned_data["purpose"] = parsed_json["purpose"]
    if parsed_json.get("optimize_for") in ["CO2", "Cost"]:
        cleaned_data["optimize_for"] = parsed_json["optimize_for"]
    if isinstance(parsed_json.get("use_superplasticizer"), bool):
        cleaned_data["use_sp"] = parsed_json["use_superplasticizer"]
    if isinstance(parsed_json.get("enable_hpc"), bool):
        cleaned_data["enable_hpc"] = parsed_json["enable_hpc"]
    
    return cleaned_data

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
    if vol_agg <= 0: vol_agg = 0.55  # Reduced from 0.60 to 0.55 for HPC mixes with higher paste volume
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
    vol_agg = (1.0 - vol_paste_and_air).clip(lower=0.55)  # Reduced from 0.60 to 0.55 for HPC mixes
    
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
            row = df.loc[df["Sieve_mm"].astype(str) == sieve]  # FIXED: astize -> astype
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
            row = df.loc[df["Sieve_mm"].astype(str) == sieve]  # FIXED: astize -> astype
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
        emissions_df_norm['Material'] = emissions_df_norm['Material'].astype(str)  # FIXED: astize -> astype
        emissions_df_norm["Material_norm"] = emissions_df_norm["Material"].apply(_normalize_material_value)
        emissions_df_norm = emissions_df_norm.drop_duplicates(subset=["Material_norm"]).set_index("Material_norm")
        co2_factors_dict = emissions_df_norm["CO2_Factor(kg_CO2_per_kg)"].to_dict()

    cost_factors_dict = {}
    if costs_df is not None and not costs_df.empty and "Cost(₹/kg)" in costs_df.columns:
        costs_df_norm = costs_df.copy()
        costs_df_norm['Material'] = costs_df_norm['Material'].astype(str)  # FIXED: astize -> astype
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

    # --- 1. Setup Parameters ---
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
                       
    if purpose_profile is None: purpose_profile = CONSTANTS.PURPOSE_PROFILES['General']
    if purpose_weights is None: purpose_weights = CONSTANTS.PURPOSE_PROFILES['General']['weights']

    # --- 2. Pre-compute Cost/CO2 Factors (Vectorization Prep) ---
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

    # --- 3. Create Parameter Grid ---
    if st_progress:
        st_progress.progress(0.1, text="Creating optimization grid...")
    
    wb_values = np.linspace(float(wb_min), float(w_b_limit), int(wb_steps))
    flyash_options = np.arange(0.0, max_flyash_frac + 1e-9, scm_step)
    ggbs_options = np.arange(0.0, max_ggbs_frac + 1e-9, scm_step)
    
    # CRITICAL FIX: Add SP fraction as search dimension for HPC mixes
    if enable_hpc and use_sp:
        # For HPC with silica fume, SP fractions should start from 0.015 (1.5%) up to HPC_SP_MAX_LIMIT
        sp_frac_options = np.arange(0.015, CONSTANTS.HPC_SP_MAX_LIMIT + 1e-9, min(scm_step, 0.005))
        silica_fume_options = np.arange(0.0, hpc_options["silica_fume"]["max_frac"] + 1e-9, scm_step/2)
        grid_params = list(product(wb_values, flyash_options, ggbs_options, silica_fume_options, sp_frac_options))
        grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac', 'sf_frac', 'sp_frac'])
        
        # Use purpose-specific SCM limit instead of hardcoded 0.50
        scm_limit = purpose_profile.get('scm_limit', 0.5) if purpose_profile else 0.5
        grid_df = grid_df[grid_df['flyash_frac'] + grid_df['ggbs_frac'] + grid_df['sf_frac'] <= scm_limit]
    elif enable_hpc:
        # HPC enabled but no SP - this should be infeasible for silica fume mixes
        silica_fume_options = np.arange(0.0, hpc_options["silica_fume"]["max_frac"] + 1e-9, scm_step/2)
        grid_params = list(product(wb_values, flyash_options, ggbs_options, silica_fume_options))
        grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac', 'sf_frac'])
        grid_df['sp_frac'] = 0.0  # No SP for HPC - will likely fail checks
        
        scm_limit = purpose_profile.get('scm_limit', 0.5) if purpose_profile else 0.5
        grid_df = grid_df[grid_df['flyash_frac'] + grid_df['ggbs_frac'] + grid_df['sf_frac'] <= scm_limit]
    else:
        # Non-HPC case
        grid_params = list(product(wb_values, flyash_options, ggbs_options))
        grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac'])
        grid_df['sf_frac'] = 0.0
        grid_df['sp_frac'] = 0.01 if use_sp else 0.0  # Default 1% SP for non-HPC
    
    if grid_df.empty:
        return None, None, []

    # --- 4. Vectorized Mix Calculations ---
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
    
    # FIX: Ensure we're working with scalar values, not DataFrames
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
    
    # CRITICAL FIX: Improved SP calculation logic
    if enable_hpc and use_sp:
        # For HPC, use the sp_frac from the grid search
        grid_df['sp'] = grid_df['sp_frac'] * grid_df['binder']
        # Apply SP effectiveness boost for silica fume
        sp_multiplier = np.where(
            grid_df['sf_frac'] > 0,
            hpc_options["silica_fume"]["sp_effectiveness_boost"],
            1.0
        )
        grid_df['sp'] = grid_df['sp'] * sp_multiplier
    elif use_sp:
        # For non-HPC, use default 1% or ensure minimum for silica fume if present
        base_sp_series = 0.01 * grid_df['binder']
        # Ensure minimum SP for silica fume mixes even in non-HPC mode
        min_sp_for_sf = np.where(
            grid_df['sf_frac'] > 0,
            np.maximum(base_sp_series, 0.015 * grid_df['binder']),
            base_sp_series
        )
        grid_df['sp'] = min_sp_for_sf
    else:
        grid_df['sp'] = 0.0
    
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

    # --- 5. Vectorized Cost & CO2 Calculations ---
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

    # --- 6. Vectorized Feasibility & Purpose Scoring ---
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
    
    # CRITICAL FIX: Improved HPC feasibility checks
    if enable_hpc:
        grid_df['fines_content'] = grid_df['fine_wet'] + grid_df['binder'] * grid_df['sf_frac']
        grid_df['sp_frac'] = grid_df['sp'] / grid_df['binder'].replace(0, 1)
        
        # For HPC with silica fume, require minimum SP fraction of 1.5%
        grid_df['check_hpc_sp'] = np.where(
            grid_df['sf_frac'] > 0,
            grid_df['sp_frac'] >= 0.015,
            True  # No silica fume, so SP check passes
        )
        
        # Use purpose-specific fines content or HPC minimum
        min_fines_required = max(
            CONSTANTS.HPC_MIN_FINES_CONTENT,
            purpose_profile.get('min_fines_content', CONSTANTS.HPC_MIN_FINES_CONTENT) if purpose_profile else CONSTANTS.HPC_MIN_FINES_CONTENT
        )
        grid_df['check_hpc_fines'] = grid_df['fines_content'] >= min_fines_required
        
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
    
    grid_df['reasons'] = get_compliance_reasons_vectorized(grid_df, exposure)
    grid_df['purpose_penalty'] = compute_purpose_penalty_vectorized(grid_df, purpose_profile)
    grid_df['purpose'] = purpose
    grid_df['enable_hpc'] = enable_hpc

    # --- 7. Candidate Selection ---
    if st_progress:
        st_progress.progress(0.8, text="Finding best mix design...")
    
    feasible_candidates_df = grid_df[grid_df['feasible']].copy()
    
    # NEW: Add diagnostic information when no feasible candidates found
    if feasible_candidates_df.empty:
        trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
        
        # Add diagnostic summary to trace
        diagnostic = {
            'total_candidates': len(grid_df),
            'check_wb_pass': int(grid_df['check_wb'].sum()),
            'check_min_cem_pass': int(grid_df['check_min_cem'].sum()),
            'check_scm_pass': int(grid_df['check_scm'].sum()),
            'check_unit_wt_pass': int(grid_df['check_unit_wt'].sum()),
        }
        if enable_hpc:
            diagnostic.update({
                'check_hpc_fines_pass': int(grid_df['check_hpc_fines'].sum()),
                'check_hpc_sp_pass': int(grid_df['check_hpc_sp'].sum()),
                'candidates_with_silica_fume': int((grid_df['sf_frac'] > 0).sum()),
                'avg_sp_frac_with_sf': float(grid_df[grid_df['sf_frac'] > 0]['sp_frac'].mean()) if (grid_df['sf_frac'] > 0).sum() > 0 else 0.0,
            })
        
        # Convert trace to dict and add diagnostic
        trace_dict = trace_df.to_dict('records')
        trace_dict.append({'diagnostic': diagnostic})
        
        return None, None, trace_dict

    if not enable_purpose_optimization or purpose == 'General':
        objective_col = 'cost_total' if optimize_cost else 'co2_total'
        feasible_candidates_df['composite_score'] = np.nan
        best_idx = feasible_candidates_df[objective_col].idxmin()
    else:
        feasible_candidates_df['norm_co2'] = _minmax_scale(feasible_candidates_df['co2_total'])
        feasible_candidates_df['norm_cost'] = _minmax_scale(feasible_candidates_df['cost_total'])
        feasible_candidates_df['norm_purpose'] = _minmax_scale(feasible_candidates_df['purpose_penalty'])
        
        w_co2 = purpose_weights.get('co2', 0.4)
        w_cost = purpose_weights.get('cost', 0.4)
        w_purpose = purpose_weights.get('purpose', 0.2)
        
        feasible_candidates_df['composite_score'] = (
            w_co2 * feasible_candidates_df['norm_co2'] +
            w_cost * feasible_candidates_df['norm_cost'] +
            w_purpose * feasible_candidates_df['norm_purpose']
        )
        best_idx = feasible_candidates_df['composite_score'].idxmin()

    best_meta_series = feasible_candidates_df.loc[best_idx]

    # --- 9. Re-hydrate Final Mix & Trace ---
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
        "fine": best_meta_series['fine_wet'],
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
    
    # CRITICAL FIX: Ensure adequate SP for HPC baseline
    if enable_hpc:
        # For HPC baseline, use minimum 1.5% SP to ensure workability with silica fume
        sp = max(0.015 * cementitious, 0.01 * cementitious) if use_sp else 0.0
    else:
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
        purpose_profile = CONSTANTS.PURPOSE_PROFILES.get(purpose, CONSTANTS.PURPOSE_PROFILES['General'])
        
    meta.update({
        "purpose": purpose,
        "purpose_metrics": evaluate_purpose_specific_metrics(meta, purpose),
        "purpose_penalty": compute_purpose_penalty(meta, purpose_profile),
        "composite_score": np.nan
    })
    return df, meta

def apply_parser(user_text, current_inputs, use_llm_parser=False):
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
    if "enable_hpc" in parsed:
        updated["enable_hpc"] = parsed["enable_hpc"]; messages.append(f"✅ Parser set HPC to **{parsed['enable_hpc']}**")
    return updated, messages, parsed

# ==============================================================================
# PART 4: UI HELPER FUNCTIONS
# ==============================================================================

def get_clarification_question(field_name: str) -> str:
    questions = {
        "grade": "What concrete grade do you need (e.g., M20, M25, M30)?",
        "exposure": f"What is the exposure condition? (e.g., {', '.join(CONSTANTS.EXPOSURE_WB_LIMITS.keys())})",
        "target_slump": "What is the target slump in mm (e.g., 75, 100, 125)?",
        "nom_max": "What is the nominal maximum aggregate size in mm (e.g., 10, 20, 40)?",
        "cement_choice": f"Which cement type would you like to use? (e.g., {', '.join(CONSTANTS.CEMENT_TYPES)})",
        "enable_hpc": "Do you want to enable High Performance Concrete features (silica fume, low w/b)?"
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
    enable_hpc = meta.get("enable_hpc", False)
    
    if purpose != "General" or enable_hpc:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("💧 Water/Binder Ratio", f"{meta['w_b']:.3f}")
        c2.metric("📦 Total Binder (kg/m³)", f"{meta['cementitious']:.1f}")
        c3.metric("🎯 Target Strength (MPa)", f"{meta['fck_target']:.1f}")
        c4.metric("⚖️ Unit Weight (kg/m³)", f"{df['Quantity (kg/m3)'].sum():.1f}")
        
        if enable_hpc:
            c5, c6, c7 = st.columns(3)
            c5.metric("🧪 Silica Fume", f"{meta.get('silica_fume', 0):.1f} kg/m³", f"{meta.get('sf_frac', 0)*100:.1f}%")
            c6.metric("🔬 HPC Mode", "Enabled", help="High Performance Concrete with silica fume")
            if "purpose_metrics" in meta and meta["purpose_metrics"].get("pumpability_assessment"):
                c7.metric("📊 Pumpability", meta["purpose_metrics"]["pumpability_assessment"])
        
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
    }),
    use_container_width=True)

    st.subheader("Compliance & Sanity Checks (IS 10262 & IS 456)")
    is_feasible, fail_reasons, warnings, derived, checks_dict = check_feasibility(df, meta, exposure)

    if is_feasible:
        st.success("✅ This mix design is compliant with IS code requirements.", icon="👍")
    else:
        st.error(f"❌ This mix fails {len(fail_reasons)} IS code compliance check(s): " + ", ".join(fail_reasons), icon="🚨")
    for warning in warnings:
        st.warning(warning, icon="⚠️")
    if (purpose != "General" or enable_hpc) and "purpose_metrics" in meta:
        with st.expander(f"Show Enhanced Purpose-Specific Metrics ({purpose})"):
            st.json(meta["purpose_metrics"])
    with st.expander("Show detailed calculation parameters"):
        if "purpose_metrics" in derived:
            derived.pop("purpose_metrics", None)
        st.json(derived)

def display_calculation_walkthrough(meta):
    st.header("Step-by-Step Calculation Walkthrough")
    
    enable_hpc = meta.get("enable_hpc", False)
    hpc_section = ""
    if enable_hpc:
        hpc_section = f"""
    #### HPC-Specific Adjustments
    - **Silica Fume Content:** `{meta.get('sf_frac', 0)*100:.1f}%` of binder = `{meta.get('silica_fume', 0):.1f}` kg/m³
    - **Water Demand Multiplier:** Applied `{meta.get('water_adjusted', meta['water_target']) / meta['water_target']:.3f}x` multiplier for silica fume
    - **SP Effectiveness Boost:** Increased SP dosage by `{(meta.get('sp', 0) / (0.01 * meta['cementitious']) - 1)*100:.0f}%` for better dispersion
    - **Pumpability Check:** Fines content = `{meta.get('fine', 0) + meta['cementitious'] * meta.get('sf_frac', 0):.0f}` kg/m³ ({'✓' if meta.get('fine', 0) + meta['cementitious'] * meta.get('sf_frac', 0) >= CONSTANTS.HPC_MIN_FINES_CONTENT else '✗'} ≥ {CONSTANTS.HPC_MIN_FINES_CONTENT} kg/m³)
        """
    
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
    {f"- **HPC Water Adjustment:** **`{meta.get('water_adjusted', meta['water_target']):.1f}` kg/m³** (adjusted for silica fume)" if enable_hpc else ""}

    #### 3. Water-Binder (w/b) Ratio
    - **Constraint:** Maximum w/b ratio for `{meta['exposure']}` exposure is `{CONSTANTS.EXPOSURE_WB_LIMITS[meta['exposure']]}`.
    - **Optimizer Selection:** The optimizer selected the lowest w/b ratio that resulted in a feasible, low-carbon mix.
    - **Selected w/b Ratio:** **`{meta['w_b']:.3f}`**

    #### 4. Binder Content
    - **Initial Binder (from w/b):** `{meta.get('water_adjusted', meta['water_target']):.1f} / {meta['w_b']:.3f} = {(meta.get('water_adjusted', meta['water_target'])/meta['w_b']):.1f}` kg/m³
    - **Constraints Check:**
              - Min. for `{meta['exposure']}` exposure: `{CONSTANTS.EXPOSURE_MIN_CEMENT[meta['exposure']]}` kg/m³
              - Typical range for `{meta['grade']}`: `{meta['binder_range'][0]}` - `{meta['binder_range'][1]}`
    - **Final Adjusted Binder Content:** **`{meta['cementitious']:.1f}` kg/m³**

    #### 5. SCM & Cement Content
    - **Optimizer Goal:** Minimize CO₂/cost by replacing cement with SCMs (Fly Ash, GGBS{", Silica Fume" if enable_hpc else ""}).
    - **Selected SCM Fraction:** `{meta['scm_total_frac']*100:.0f}%`
    - **Material Quantities:**
              - **Cement:** `{meta['cement']:.1f}` kg/m³
              - **Fly Ash:** `{meta['flyash']:.1f}` kg/m³
              - **GGBS:** `{meta['ggbs']:.1f}` kg/m³
              {f"- **Silica Fume:** `{meta.get('silica_fume', 0):.1f}` kg/m³" if enable_hpc else ""}
    {hpc_section}
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
    try:
        min_grade_req = CONSTANTS.EXPOSURE_MIN_GRADE[inputs["exposure"]]
        grade_order = list(CONSTANTS.GRADE_STRENGTH.keys())
        if grade_order.index(inputs["grade"]) < grade_order.index(min_grade_req):
            st.warning(f"For **{inputs['exposure']}** exposure, IS 456 recommends a minimum grade of **{min_grade_req}**. The grade has been automatically updated.", icon="⚠️")
            inputs["grade"] = min_grade_req
            st.session_state.final_inputs["grade"] = min_grade_req

        calibration_kwargs = inputs.get("calibration_kwargs", {})
        
        if 'max_sf_frac' in calibration_kwargs:
            del calibration_kwargs['max_sf_frac']
        if 'use_hpc_presets' in calibration_kwargs:
            del calibration_kwargs['use_hpc_presets']
        
        purpose = inputs.get('purpose', 'General')
        purpose_profile = purpose_profiles_data.get(purpose, purpose_profiles_data['General'])
        enable_purpose_opt = inputs.get('enable_purpose_optimization', False)
        purpose_weights = inputs.get('purpose_weights', purpose_profiles_data['General']['weights'])
        enable_hpc = inputs.get('enable_hpc', False)
        
        if purpose == 'General': enable_purpose_opt = False
        
        if st_progress:
            if enable_hpc:
                st.info(f"🧪 Running High Performance Concrete optimization for **{purpose}**.", icon="🔬")
            elif enable_purpose_opt:
                st.info(f"🚀 Running composite optimization for **{purpose}**.", icon="🛠️")
            else:
                st.info(f"Running single-objective optimization for **{inputs.get('optimize_for', 'CO₂ Emissions')}**.", icon="⚙️")
        
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
            enable_hpc=enable_hpc,
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
            purpose_profile=purpose_profile, enable_hpc=enable_hpc
        )
        
        if st_progress: st_progress.progress(1.0, text="Optimization complete!")
        if st_progress: st_progress.empty()

        if opt_df is None or base_df is None:
            st.error("Could not find a feasible mix design with the given constraints. Try adjusting the parameters, such as a higher grade or less restrictive exposure condition.", icon="❌")
            if trace:
                # Show diagnostic information if available
                if trace and isinstance(trace[-1], dict) and 'diagnostic' in trace[-1]:
                    diagnostic = trace[-1]['diagnostic']
                    st.info(f"Diagnostic: {diagnostic}", icon="🔍")
                st.dataframe(pd.DataFrame(trace))
            st.session_state.results = {"success": False, "trace": trace}
        else:
            if not st.session_state.get("chat_mode", False):
                success_msg = f"Successfully generated mix designs for **{inputs['grade']}** concrete in **{inputs['exposure']}** conditions."
                if enable_hpc:
                    success_msg += " 🧪 **HPC Mode Enabled**"
                st.success(success_msg, icon="✅")
            
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

# ==============================================================================
# PART 6: STREAMLIT APP (UI Sub-modules)
# ==============================================================================

def run_chat_interface(purpose_profiles_data: dict):
    st.title("💬 CivilGPT Chat Mode")
    st.markdown("Welcome to the conversational interface. Describe your concrete mix needs, and I'll ask for clarifications.")
    
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

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
        
        if opt_meta.get("enable_hpc", False):
            summary_msg += f"\n- **🧪 HPC Features:** Silica fume {opt_meta.get('sf_frac', 0)*100:.1f}% ({opt_meta.get('silica_fume', 0):.1f} kg/m³)"
        
        st.session_state.chat_history.append({"role": "assistant", "content": summary_msg})
        st.session_state.chat_results_displayed = True
        st.rerun()

    if st.session_state.get("chat_results_displayed", False):
        st.info("Your full mix report is ready. You can ask for refinements or open the full report.")

        def switch_to_manual_mode():
            st.session_state["chat_mode"] = False
            st.session_state["chat_mode_toggle_functional"] = False
            st.session_state["active_tab_name"] = "📊 **Overview**"
            st.session_state["manual_tabs"] = "📊 **Overview**"  
            st.session_state["chat_results_displayed"] = False  
            st.rerun()

        st.button(
            "📊 Open Full Mix Report & Switch to Manual Mode",  
            use_container_width=True,  
            type="primary",
            on_click=switch_to_manual_mode,
            key="switch_to_manual_btn"
        )

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
            st.session_state.chat_history.append({"role": "assistant", "content": "✅ Great, I have all your requirements. Generating your sustainable mix design now..."})
            st.session_state.run_chat_generation = True
            st.session_state.chat_results_displayed = False
            if "results" in st.session_state:
                del st.session_state.results
        
        st.rerun()

def run_manual_interface(purpose_profiles_data: dict, materials_df: pd.DataFrame, emissions_df: pd.DataFrame, costs_df: pd.DataFrame):
    st.title("🧱 CivilGPT: Sustainable Concrete Mix Designer")
    st.markdown("##### An AI-powered tool for creating **IS 10262:2019 compliant** concrete mixes, optimized for low carbon footprint.")

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

    with st.expander("⚙️ Advanced Manual Input: Detailed Parameters and Libraries", expanded=False):
        st.subheader("Core Mix Requirements")
        
        enable_hpc = st.toggle("Enable HPC (M60–M100)", value=False, key="enable_hpc_toggle",
                       help="When enabled, adds high-performance concrete grades (M60–M100) to the grade options and enables silica fume optimization.")
        
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            grade_list = list(CONSTANTS.GRADE_STRENGTH.keys())
            if not st.session_state.get("enable_hpc_toggle", False):
                grade_list = [g for g in grade_list if int(g[1:]) <= 50]
            grade = st.selectbox("Concrete Grade", grade_list, index=grade_list.index("M30"), key="grade")
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
        
        if enable_hpc:
            st.markdown("---")
            st.subheader("🧪 High Performance Concrete (HPC) Options")
            hpc_col1, hpc_col2 = st.columns(2)
            with hpc_col1:
                max_sf_frac = st.slider("Max Silica Fume Fraction", 0.0, 0.15, 0.10, 0.01,
                                       help="Maximum silica fume as fraction of binder content")
                use_hpc_presets = st.checkbox("Use HPC Low w/b Presets", True,
                                             help="Allow w/b ratios as low as 0.25 for HPC grades")
            with hpc_col2:
                hpc_wb_min = st.slider("HPC Min w/b Ratio", 0.25, 0.40, 0.30, 0.01,
                                      disabled=not use_hpc_presets,
                                      help="Minimum water-binder ratio for HPC optimization")
                
            silica_fume_in_library = False
            if materials_df is not None and not materials_df.empty:
                # FIX: Safe column access for Material column
                if "Material" in materials_df.columns:
                    material_names = [str(m).lower() for m in materials_df["Material"].astype(str).tolist()]  # FIXED: astize -> astype
                    silica_fume_in_library = any("silica fume" in name or "microsilica" in name for name in material_names)
            
            if not silica_fume_in_library:
                st.warning("⚠️ Silica fume not found in materials library. HPC mixes will use placeholder values for CO₂ and cost factors.", icon="🔬")
        
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
                
                total_w = w_co2 + w_cost + w_purpose
                if total_w == 0:
                    st.warning("Weights cannot all be zero. Defaulting to balanced weights.")
                    purpose_weights = {"co2": 0.33, "cost": 0.33, "purpose": 0.34}
                else:
                    purpose_weights = {"co2": w_co2 / total_w, "cost": w_cost / total_w, "purpose": w_purpose / total_w}
                    st.caption(f"Normalized: CO₂ {purpose_weights['co2']:.1%}, Cost {purpose_weights['cost']:.1%}, Purpose {purpose_weights['purpose']:.1%}")
        elif enable_purpose_optimization and purpose == 'General':
             st.info("Purpose 'General' uses single-objective optimization (CO₂ or Cost).")
             enable_purpose_optimization = False

        st.markdown("---")
        st.subheader("Material Properties (Manual Override)")
        
        sg_fa_default, moisture_fa_default = 2.65, 1.0
        sg_ca_default, moisture_ca_default = 2.70, 0.5

        if materials_df is not None and not materials_df.empty:
            try:
                mat_df = materials_df.copy()
                # FIX: Safe column access for Material column
                if "Material" in mat_df.columns:
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
    enable_hpc = st.session_state.get("enable_hpc_toggle", False)

    sg_fa = st.session_state.get("sg_fa_manual", 2.65)
    moisture_fa = st.session_state.get("moisture_fa_manual", 1.0)
    sg_ca = st.session_state.get("sg_ca_manual", 2.70)
    moisture_ca = st.session_state.get("moisture_ca_manual", 0.5)

    fine_csv = st.session_state.get("fine_csv", None)
    coarse_csv = st.session_state.get("coarse_csv", None)
    lab_csv = st.session_state.get("lab_csv", None)

    enable_calibration_overrides = st.session_state.get("enable_calibration_overrides", False)
    calib_wb_min = st.session_state.get("calib_wb_min", 0.35) if enable_calibration_overrides else 0.35
    calib_wb_steps = st.session_state.get("calib_wb_steps", 6) if enable_calibration_overrides else 6
    calib_max_flyash_frac = st.session_state.get("calib_max_flyash_frac", 0.3) if enable_calibration_overrides else 0.3
    calib_max_ggbs_frac = st.session_state.get("calib_max_ggbs_frac", 0.5) if enable_calibration_overrides else 0.5
    calib_scm_step = st.session_state.get("calib_scm_step", 0.1) if enable_calibration_overrides else 0.1
    calib_fine_fraction = st.session_state.get("calib_fine_fraction", 0.40) if enable_calibration_overrides else None
    if calib_fine_fraction == 0.40 and not enable_calibration_overrides:
        calib_fine_fraction = None
    
    if enable_hpc:
        max_sf_frac = st.session_state.get("max_sf_frac", 0.10)
        use_hpc_presets = st.session_state.get("use_hpc_presets", True)
        hpc_wb_min = st.session_state.get("hpc_wb_min", 0.30)
        
        if use_hpc_presets:
            calib_wb_min = max(calib_wb_min, hpc_wb_min)
    
    purpose_weights = purpose_profiles_data['General']['weights']
    if enable_purpose_optimization and purpose != 'General':
        w_co2 = st.session_state.get("w_co2", purpose_profiles_data.get(purpose, purpose_profiles_data['General'])['weights']['co2'])
        w_cost = st.session_state.get("w_cost", purpose_profiles_data.get(purpose, purpose_profiles_data['General'])['weights']['cost'])
        w_purpose = st.session_state.get("w_purpose", purpose_profiles_data.get(purpose, purpose_profiles_data['General'])['weights']['purpose'])
        
        total_w = w_co2 + w_cost + w_purpose
        if total_w > 0:
            purpose_weights = {"co2": w_co2 / total_w, "cost": w_cost / total_w, "purpose": w_purpose / total_w}

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
        "enable_hpc": lambda v: st.checkbox("Enable HPC", value=v if isinstance(v, bool) else False, help="Enable High Performance Concrete features"),
    }

    if run_button:
        st.session_state.run_generation_manual = True
        st.session_state.clarification_needed = False
        if 'results' in st.session_state: del st.session_state.results

        material_props = {'sg_fa': sg_fa, 'moisture_fa': moisture_fa, 'sg_ca': sg_ca, 'moisture_ca': moisture_ca}
        
        calibration_kwargs = {}
        if enable_calibration_overrides:
            calibration_kwargs = {
                "wb_min": calib_wb_min, "wb_steps": calib_wb_steps,
                "max_flyash_frac": calib_max_flyash_frac, "max_ggbs_frac": calib_max_ggbs_frac,
                "scm_step": calib_scm_step, "fine_fraction_override": calib_fine_fraction
            }
            st.info("Developer calibration overrides are enabled.", icon="🛠️")
            
        if enable_hpc:
            hpc_calibration = {}
            calibration_kwargs.update(hpc_calibration)
            
        inputs = { 
            "grade": grade, "exposure": exposure, "cement_choice": cement_choice, 
            "nom_max": nom_max, "agg_shape": agg_shape, "target_slump": target_slump, 
            "use_sp": use_sp, "optimize_cost": optimize_cost, "qc_level": qc_level, 
            "fine_zone": fine_zone, "material_props": material_props,
            "purpose": purpose, "enable_purpose_optimization": enable_purpose_optimization, 
            "purpose_weights": purpose_weights, "optimize_for": optimize_for,
            "enable_hpc": enable_hpc,
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
        st.session_state.run_generation_manual = False

    if 'results' in st.session_state and st.session_state.results["success"]:
        results = st.session_state.results
        opt_df, opt_meta = results["opt_df"], results["opt_meta"]
        base_df, base_meta = results["base_df"], results["base_meta"]
        trace, inputs = results["trace"], results["inputs"]
        
        TAB_NAMES = [
            "📊 **Overview**", "🌱 **Optimized Mix**", "🏗️ **Baseline Mix**",
            "⚖️ **Trade-off Explorer**", "📋 **QA/QC & Gradation**",
            "📥 **Downloads & Reports**", "🔬 **Lab Calibration**"
        ]
        
        if "current_tab" not in st.session_state:
            st.session_state.current_tab = TAB_NAMES[0]
        
        st.markdown("---")
        st.subheader("Mix Report Navigation")
        
        cols = st.columns(len(TAB_NAMES))
        for i, tab_name in enumerate(TAB_NAMES):
            with cols[i]:
                is_selected = st.session_state.current_tab == tab_name
                button_type = "primary" if is_selected else "secondary"
                if st.button(tab_name, use_container_width=True, type=button_type, key=f"tab_btn_{i}"):
                    st.session_state.current_tab = tab_name
                    st.rerun()
        
        selected_tab = st.session_state.current_tab

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
            
            if opt_meta.get("purpose", "General") != "General" or opt_meta.get("enable_hpc", False):
                st.markdown("---")
                if opt_meta.get("enable_hpc", False):
                    c_h1, c_h2, c_h3 = st.columns(3)
                    c_h1.metric("🧪 Silica Fume", f"{opt_meta.get('silica_fume', 0):.1f} kg/m³", f"{opt_meta.get('sf_frac', 0)*100:.1f}%")
                    c_h2.metric("🔬 HPC Mode", "Enabled", help="High Performance Concrete with silica fume")
                    if "purpose_metrics" in opt_meta and opt_meta["purpose_metrics"].get("pumpability_assessment"):
                        c_h3.metric("📊 Pumpability", opt_meta["purpose_metrics"]["pumpability_assessment"])
                
                c_p1, c_p2, c_p3 = st.columns(3)
                c_p1.metric("🛠️ Design Purpose", opt_meta['purpose'])
                c_p2.metric("⚠️ Purpose Penalty", f"{opt_meta.get('purpose_penalty', 0.0):.2f}", help="Penalty for deviation from purpose targets (lower is better).")
                if "composite_score" in opt_meta and not pd.isna(opt_meta["composite_score"]):
                    c_p3.metric("🎯 Composite Score", f"{opt_meta.get('composite_score', 0.0):.3f}", help="Normalized score (lower is better).")

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
                    pareto_df = pareto_front(feasible_mixes, x_col="cost", y_col="co2", z_col="purpose_penalty")
                    
                    current_alpha = st.session_state.get("pareto_slider_alpha", 0.5)
                    
                    if not pareto_df.empty:
                        alpha = st.slider(
                            "Prioritize Sustainability (CO₂) ↔ Cost",
                            min_value=0.0, max_value=1.0, value=current_alpha, step=0.05,
                            help="Slide towards Sustainability to prioritize low CO₂, or towards Cost to prioritize low price. The green diamond will show the best compromise on the Pareto Front for your chosen preference.",
                            key="pareto_slider_alpha"
                        )
                        
                        cost_min, cost_max = pareto_df['cost'].min(), pareto_df['cost'].max()
                        co2_min, co2_max = pareto_df['co2'].min(), pareto_df['co2'].max()
                        penalty_min, penalty_max = pareto_df['purpose_penalty'].min(), pareto_df['purpose_penalty'].max()
                        
                        pareto_df_norm = pareto_df.copy()
                        pareto_df_norm['norm_cost'] = 0.0 if (cost_max - cost_min) == 0 else (pareto_df_norm['cost'] - cost_min) / (cost_max - cost_min)
                        pareto_df_norm['norm_co2'] = 0.0 if (co2_max - co2_min) == 0 else (pareto_df_norm['co2'] - co2_min) / (co2_max - co2_min)
                        pareto_df_norm['norm_penalty'] = 0.0 if (penalty_max - penalty_min) == 0 else (pareto_df_norm['purpose_penalty'] - penalty_min) / (penalty_max - penalty_min)
                        
                        pareto_df_norm['score'] = (
                            alpha * pareto_df_norm['norm_co2'] + 
                            (1 - alpha) * pareto_df_norm['norm_cost'] +
                            pareto_df_norm['norm_penalty'] * 0.2
                        )
                        best_compromise_mix = pareto_df_norm.loc[pareto_df_norm['score'].idxmin()]

                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.scatter(feasible_mixes["cost"], feasible_mixes["co2"], 
                                  c=feasible_mixes["purpose_penalty"], cmap='viridis', 
                                  alpha=0.5, label='All Feasible Mixes', zorder=1)
                        
                        cbar = plt.colorbar(ax.collections[0], ax=ax)
                        cbar.set_label('Purpose Penalty')
                        
                        pareto_df_sorted = pareto_df.sort_values(by="cost")
                        ax.plot(pareto_df_sorted["cost"], pareto_df_sorted["co2"], '-o', 
                               color='blue', label='Pareto Front (Efficient Mixes)', 
                               linewidth=2, zorder=2)
                        
                        optimize_for_label = f"Composite Score ({inputs['purpose']})" if inputs.get('enable_purpose_optimization', False) and inputs.get('purpose', 'General') != 'General' else inputs.get('optimize_for', 'CO₂ Emissions')
                        
                        ax.plot(opt_meta['cost_total'], opt_meta['co2_total'], '*', 
                               markersize=15, color='red', 
                               label=f'Chosen Mix ({optimize_for_label})', zorder=3)
                        ax.plot(best_compromise_mix['cost'], best_compromise_mix['co2'], 'D', 
                               markersize=10, color='green', 
                               label='Best Compromise (from slider)', zorder=3)
                        ax.set_xlabel("Material Cost (₹/m³)"); ax.set_ylabel("Embodied Carbon (kg CO₂e / m³)")
                        ax.set_title("Pareto Front of Feasible Concrete Mixes (Color = Purpose Penalty)"); 
                        ax.grid(True, linestyle='--', alpha=0.6); ax.legend()
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
                            c4, c5, c6 = st.columns(3)
                            c4.metric("⚠️ Purpose Penalty", f"{full_compromise_mix['purpose_penalty']:.2f}")
                            c5.metric("🎯 Composite Score", f"{full_compromise_mix['composite_score']:.3f}")
                            c6.metric("🛠️ Purpose", f"{full_compromise_mix.get('purpose', 'General')}")
                        
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
                                "ggbs_frac": "{:.2f}", "sf_frac": "{:.2f}", "co2": "{:.1f}", "cost": "{:.1f}",
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
            
            if opt_meta.get("enable_hpc", False):
                summary_data.insert(5, ["Silica Fume (kg/m³)", f"{opt_meta.get('silica_fume', 0):.1f}", "N/A"])
                summary_data.insert(6, ["Silica Fume %", f"{opt_meta.get('sf_frac', 0)*100:.1f}%", "N/A"])
                
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
                        st.warning("Could not process the uploaded lab data CSV. Please check the file format, column names and ensure it contains valid data.", icon="⚠️")
                except Exception as e:
                    st.error(f"Failed to read or process the lab data CSV file: {e}", icon="💥")
            else:
                st.info("Upload a lab data CSV in the **Advanced Manual Input** section to automatically compare CivilGPT's target strength calculations against your real-world results.", icon="ℹ️")
        
    elif 'results' in st.session_state and not st.session_state.results["success"]:
        pass
    elif not st.session_state.get('clarification_needed'):
        st.info("Enter your concrete requirements in the prompt box above, or expand the **Advanced Manual Input** section to specify parameters.", icon="👆")
        st.markdown("---")
        st.subheader("How It Works")
        st.markdown("""
        1.  **Input Requirements**: Describe your project needs (e.g., "M25 concrete for moderate exposure") or use the manual inputs for detailed control.
        2.  **Select Purpose**: Choose your design purpose (e.g., 'Slab', 'Column') to enable purpose-specific optimization.
        3.  **IS Code Compliance**: The app generates dozens of candidate mixes, ensuring each one adheres to the durability and strength requirements of Indian Standards **IS 10262** and **IS 456**.
        4.  **Sustainability Optimization**: It then calculates the embodied carbon (CO₂e), cost, and 'Purpose-Fit' for every compliant mix.
        5.  **Best Mix Selection**: Finally, it presents the mix with the best **composite score** (or lowest CO₂/cost) alongside a standard OPC baseline for comparison.
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
        [data-testid="stSidebarContent"] > div:first-child {
            padding-bottom: 0rem;
        }
    </style>
    """, unsafe_allow_html=True)

    if "chat_mode" not in st.session_state:
        st.session_state.chat_mode = False
    
    if "current_tab" not in st.session_state:
        st.session_state.current_tab = "📊 **Overview**"
        
    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []
    if "chat_inputs" not in st.session_state:
        st.session_state.chat_inputs = {}
    if "chat_results_displayed" not in st.session_state:
        st.session_state.chat_results_displayed = False
    if "run_chat_generation" not in st.session_state:
        st.session_state.run_chat_generation = False
        
    purpose_profiles_data = load_purpose_profiles()

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

    if chat_mode:
        run_chat_interface(purpose_profiles_data)
    else:
        run_manual_interface(purpose_profiles_data, materials_df, emissions_df, costs_df)

if __name__ == "__main__":
    main()
    
    # Internal self-test for HPC functionality (only runs if environment variable is set)
    if os.getenv("CIVILGPT_SELFTEST", "0") == "1":
        try:
            print("🧪 Running HPC self-test...")
            
            # Test HPC mix generation
            test_materials_df = pd.DataFrame({
                "Material": ["OPC 43", "Fly Ash", "GGBS", "Silica Fume", "Water", "PCE Superplasticizer", "Fine Aggregate", "Coarse Aggregate"],
                "SpecificGravity": [3.15, 2.2, 2.9, 2.2, 1.0, 1.2, 2.65, 2.70],
                "MoistureContent": [0, 0, 0, 0, 0, 0, 1.0, 0.5]
            })
            
            test_emissions_df = pd.DataFrame({
                "Material": ["OPC 43", "Fly Ash", "GGBS", "Silica Fume", "Water", "PCE Superplasticizer", "Fine Aggregate", "Coarse Aggregate"],
                "CO2_Factor(kg_CO2_per_kg)": [0.85, 0.05, 0.08, 0.1, 0.0, 0.5, 0.01, 0.01]
            })
            
            test_costs_df = pd.DataFrame({
                "Material": ["OPC 43", "Fly Ash", "GGBS", "Silica Fume", "Water", "PCE Superplasticizer", "Fine Aggregate", "Coarse Aggregate"],
                "Cost(₹/kg)": [8.0, 4.0, 6.0, 15.0, 0.05, 120.0, 0.5, 0.6]
            })
            
            test_inputs = {
                "grade": "M60", 
                "exposure": "Severe", 
                "nom_max": 20,
                "target_slump": 100, 
                "agg_shape": "Angular (baseline)",
                "fine_zone": "Zone II", 
                "cement_choice": "OPC 43",
                "material_props": {'sg_fa': 2.65, 'moisture_fa': 1.0, 'sg_ca': 2.70, 'moisture_ca': 0.5},
                "use_sp": True, 
                "optimize_cost": False,
                "purpose": "RPC/HPC",
                "enable_purpose_optimization": True,
                "enable_hpc": True,
                "calibration_kwargs": {}
            }
            
            opt_df, opt_meta, trace = generate_mix(
                **test_inputs,
                emissions=test_emissions_df,
                costs=test_costs_df,
                purpose_profiles_data=CONSTANTS.PURPOSE_PROFILES
            )
            
            if opt_df is not None and opt_meta is not None:
                print("✅ HPC self-test PASSED - Successfully generated HPC mix")
                print(f"   Grade: {opt_meta['grade']}, Binder: {opt_meta['cementitious']:.1f} kg/m³")
                print(f"   Silica Fume: {opt_meta.get('silica_fume', 0):.1f} kg/m³")
                print(f"   SP: {opt_meta.get('sp', 0):.2f} kg/m³")
                print(f"   w/b: {opt_meta['w_b']:.3f}")
            else:
                print("❌ HPC self-test FAILED - Could not generate HPC mix")
                if trace and isinstance(trace[-1], dict) and 'diagnostic' in trace[-1]:
                    print(f"   Diagnostic: {trace[-1]['diagnostic']}")
                    
        except Exception as e:
            print(f"❌ HPC self-test ERROR: {e}")
            import traceback
            traceback.print_exc()
