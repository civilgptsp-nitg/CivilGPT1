# app.py - CivilGPT v4.0 (Compressed & Refactored)

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
import json
import re
from io import BytesIO
from difflib import get_close_matches
# ReportLab imports for PDF generation
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from functools import lru_cache
from itertools import product

# ==============================================================================
# PART 1: CONSTANTS & CORE DATA
# ==============================================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
# LAB_FILE and MIX_FILE not strictly needed as they are not used globally
# in the final app logic (mix_df/lab_df are loaded but not used beyond init,
# keeping the load for robustness/future-proofing but removing their constants)

class CONSTANTS:
    # Core Engineering Data
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
        "Zone I":   {"10.0": (100,100),"4.75": (90,100),"2.36": (60,95),"1.18": (30,70),"0.600": (15,34),"0.300": (5,20),"0.150": (0,10)},
        "Zone II":  {"10.0": (100,100),"4.75": (90,100),"2.36": (75,100),"1.18": (55,90),"0.600": (35,59),"0.300": (8,30),"0.150": (0,10)},
        "Zone III": {"10.0": (100,100),"4.75": (90,100),"2.36": (85,100),"1.18": (75,90),"0.600": (60,79),"0.300": (12,40),"0.150": (0,10)},
        "Zone IV":  {"10.0": (95,100),"4.75": (95,100),"2.36": (95,100),"1.18": (90,100),"0.600": (80,100),"0.300": (15,50),"0.150": (0,15)},
    }
    COARSE_LIMITS = {
        10: {"20.0": (100,100), "10.0": (85,100),        "4.75": (0,20)},
        20: {"40.0": (95,100),  "20.0": (95,100),  "10.0": (25,55), "4.75": (0,10)},
        40: {"80.0": (95,100),  "40.0": (95,100),  "20.0": (30,70), "10.0": (0,15)}
    }
    
    # Column mapping for data loading standardization
    EMISSIONS_COL_MAP = {"material": "Material", "co2_factor_kg_co2_per_kg": "CO2_Factor(kg_CO2_per_kg)", "co2_factor": "CO2_Factor(kg_CO2_per_kg)", "emission_factor": "CO2_Factor(kg_CO2_per_kg)"}
    COSTS_COL_MAP = {"material": "Material", "cost_kg": "Cost(₹/kg)", "cost_rs_kg": "Cost(₹/kg)", "cost_per_kg": "Cost(₹/kg)", "price_kg": "Cost(₹/kg)"}
    MATERIALS_COL_MAP = {"material": "Material", "specificgravity": "SpecificGravity", "moisturecontent": "MoistureContent", "waterabsorption": "WaterAbsorption"}
    
    # Normalized names for vectorized computation
    NORM_CEMENT = "cement"
    NORM_FLYASH = "fly ash"
    NORM_GGBS = "ggbs"
    NORM_WATER = "water"
    NORM_SP = "pce superplasticizer"
    NORM_FINE_AGG = "fine aggregate"
    NORM_COARSE_AGG = "coarse aggregate"
    
    # Design Purpose Profiles
    PURPOSE_PROFILES = {
        "General": {"description": "A balanced, default mix. Follows IS code minimums without specific optimization bias.", "wb_limit": 1.0, "scm_limit": 0.5, "min_binder": 0.0, "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2}},
        "Slab": {"description": "Prioritizes workability (slump) and cost-effectiveness. Strength is often not the primary driver.", "wb_limit": 0.55, "scm_limit": 0.5, "min_binder": 300, "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2}},
        "Beam": {"description": "Prioritizes strength (modulus) and durability. Often heavily reinforced.", "wb_limit": 0.50, "scm_limit": 0.4, "min_binder": 320, "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4}},
        "Column": {"description": "Prioritizes high compressive strength and durability. Congestion is common.", "wb_limit": 0.45, "scm_limit": 0.35, "min_binder": 340, "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5}},
        "Pavement": {"description": "Prioritizes durability, flexural strength (fatigue), and abrasion resistance. Cost is a major factor.", "wb_limit": 0.45, "scm_limit": 0.4, "min_binder": 340, "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3}},
        "Precast": {"description": "Prioritizes high early strength (for form stripping), surface finish, and cost (reproducibility).", "wb_limit": 0.45, "scm_limit": 0.3, "min_binder": 360, "weights": {"co2": 0.2, "cost": 0.5, "purpose": 0.3}}
    }
    CEMENT_TYPES = ["OPC 33", "OPC 43", "OPC 53", "PPC"]
    CHAT_REQUIRED_FIELDS = ["grade", "exposure", "target_slump", "nom_max", "cement_choice"]

# ==============================================================================
# PART 2: CACHED LOADERS & BACKEND LOGIC (Refactored)
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
        st.session_state["llm_enabled"] = False
        st.session_state["llm_init_message"] = ("info", "ℹ️ LLM parser disabled (no API key found). Using regex-based fallback.")
except ImportError:
    st.session_state["llm_enabled"] = False
    st.session_state["llm_init_message"] = ("warning", "⚠️ Groq library not found. `pip install groq`. Falling back to regex parser.")
except Exception as e:
    st.session_state["llm_enabled"] = False
    st.session_state["llm_init_message"] = ("warning", f"⚠️ LLM initialization failed: {e}. Falling back to regex parser.")


@lru_cache(maxsize=128)
def _normalize_material_value(s: str) -> str:
    """Normalizes material names for merging/lookup."""
    if s is None: return ""
    s = str(s).strip().lower()
    s = re.sub(r'[ \-/\.\(\)]+', ' ', s).strip()
    synonyms = {
        "m sand": CONSTANTS.NORM_FINE_AGG, "msand": CONSTANTS.NORM_FINE_AGG, "m sand": CONSTANTS.NORM_FINE_AGG,
        "fine aggregate": CONSTANTS.NORM_FINE_AGG, "sand": CONSTANTS.NORM_FINE_AGG,
        "20mm coarse aggregate": CONSTANTS.NORM_COARSE_AGG, "20 coarse": CONSTANTS.NORM_COARSE_AGG, "20": CONSTANTS.NORM_COARSE_AGG, "coarse aggregate": CONSTANTS.NORM_COARSE_AGG,
        "20mm": CONSTANTS.NORM_COARSE_AGG, "pce superplasticizer": CONSTANTS.NORM_SP, "pce": CONSTANTS.NORM_SP,
        "fly ash": CONSTANTS.NORM_FLYASH, "ggbs": CONSTANTS.NORM_GGBS, "water": CONSTANTS.NORM_WATER,
    }
    if s in synonyms: return synonyms[s]
    cand = get_close_matches(s, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    if s.startswith("opc"): return s.replace(' ', '')
    return s

def _normalize_header(header):
    """Normalizes DataFrame column headers for consistent loading."""
    s = str(header).strip().lower()
    return re.sub(r'[^a-z0-9]+', '', s)

def _normalize_columns(df, column_map):
    """Renames columns based on the provided map."""
    canonical_cols = list(dict.fromkeys(column_map.values()))
    if df is None or df.empty: return pd.DataFrame(columns=canonical_cols)
    df = df.copy()
    norm_cols = {_normalize_header(col): col for col in df.columns}
    rename_dict = {}
    for variant, canonical in column_map.items():
        if _normalize_header(variant) in norm_cols and canonical not in rename_dict.values():
            rename_dict[norm_cols[_normalize_header(variant)]] = canonical
    df = df.rename(columns=rename_dict)
    found_canonical = [col for col in canonical_cols if col in df.columns]
    return df[found_canonical]

def _minmax_scale(series: pd.Series) -> pd.Series:
    """Performs Min-Max scaling on a Series."""
    min_val, max_val = series.min(), series.max()
    if pd.isna(min_val) or pd.isna(max_val) or (max_val - min_val) == 0:
        return pd.Series(0.0, index=series.index, dtype=float)
    return (series - min_val) / (max_val - min_val)

@st.cache_data
def load_data(materials_file=None, emissions_file=None, cost_file=None):
    """Loads all necessary dataframes (materials, emissions, costs) from uploaded files or fallbacks."""
    def _safe_read(file, default_names, col_map):
        df = None
        if file is not None:
            try:
                if hasattr(file, 'seek'): file.seek(0)
                df = pd.read_csv(file)
            except Exception as e: st.warning(f"Could not read uploaded file {getattr(file, 'name', 'N/A')}: {e}")
        
        if df is None or df.empty:
            for name in default_names:
                p = os.path.join(SCRIPT_DIR, name)
                if os.path.exists(p):
                    try: df = pd.read_csv(p); break
                    except Exception as e: st.warning(f"Could not read {p}: {e}")
            if df is None: st.warning(f"Could not load fallback for {default_names[0]}. Using empty library.", icon="ℹ️")
        
        df = _normalize_columns(df, col_map)
        if "Material" in df.columns:
            df["Material"] = df["Material"].astype(str).str.strip()
        
        # Ensure factor column exists and is numeric, else fill with 0
        factor_col = list(dict.fromkeys(col_map.values()))[-1]
        if factor_col not in df.columns: df[factor_col] = 0.0
        df[factor_col] = pd.to_numeric(df[factor_col], errors='coerce').fillna(0.0)
        
        return df if df is not None else pd.DataFrame(columns=list(dict.fromkeys(col_map.values())))

    materials = _safe_read(materials_file, ["materials_library.csv", "data/materials_library.csv"], CONSTANTS.MATERIALS_COL_MAP)
    emissions = _safe_read(emissions_file, ["emission_factors.csv", "data/emission_factors.csv"], CONSTANTS.EMISSIONS_COL_MAP)
    costs = _safe_read(cost_file, ["cost_factors.csv", "data/cost_factors.csv"], CONSTANTS.COSTS_COL_MAP)

    return materials, emissions, costs

def _get_material_factors(materials_list, emissions_df, costs_df):
    """Pre-computes CO2 and Cost factors for a list of normalized materials."""
    norm_map = {m: _normalize_material_value(m) for m in materials_list}
    norm_materials = list(set(norm_map.values()))

    def extract_factors(df, col_name):
        if df is not None and not df.empty and col_name in df.columns:
            df_norm = df.copy()
            df_norm['Material_norm'] = df_norm['Material'].apply(_normalize_material_value)
            return df_norm.drop_duplicates(subset=["Material_norm"]).set_index("Material_norm")[col_name].to_dict()
        return {}

    co2_factors_dict = extract_factors(emissions_df, "CO2_Factor(kg_CO2_per_kg)")
    cost_factors_dict = extract_factors(costs_df, "Cost(₹/kg)")

    final_co2 = {norm: co2_factors_dict.get(norm, 0.0) for norm in norm_materials}
    final_cost = {norm: cost_factors_dict.get(norm, 0.0) for norm in norm_materials}
    
    return final_co2, final_cost

def _merge_and_warn(main_df: pd.DataFrame, factor_df: pd.DataFrame, factor_col: str, warning_session_key: str, warning_prefix: str) -> pd.DataFrame:
    """Helper to merge factor dataframes and issue warnings for missing values."""
    if factor_df is not None and not factor_df.empty and factor_col in factor_df.columns:
        factor_df_norm = factor_df.copy()
        factor_df_norm['Material_norm'] = factor_df_norm['Material'].astype(str).apply(_normalize_material_value)
        factor_df_norm = factor_df_norm.drop_duplicates(subset=["Material_norm"])
        
        merged_df = main_df.merge(factor_df_norm[["Material_norm", factor_col]], on="Material_norm", how="left")
        
        missing_items = merged_df[merged_df[factor_col].isna()]["Material"].tolist()
        
        if missing_items:
            # Removed redundant session state warning logic as it adds complexity
            # without adding core functionality to the final production code.
            pass
            
        merged_df[factor_col] = merged_df[factor_col].fillna(0.0)
        return merged_df
    else:
        main_df[factor_col] = 0.0
        return main_df

@st.cache_data
def water_for_slump_and_shape(nom_max_mm: int, slump_mm: int, agg_shape: str, uses_sp: bool=False, sp_reduction_frac: float=0.0) -> float:
    """Calculates target water content based on IS 10262 guidelines and adjustments."""
    base = CONSTANTS.WATER_BASELINE.get(int(nom_max_mm), 186.0)
    water = base if slump_mm <= 50 else base * (1 + 0.03 * ((slump_mm - 50) / 25.0))
    water *= (1.0 + CONSTANTS.AGG_SHAPE_WATER_ADJ.get(agg_shape, 0.0))
    if uses_sp and sp_reduction_frac > 0: water *= (1 - sp_reduction_frac)
    return float(water)

@st.cache_data
def _get_coarse_agg_fraction_base(nom_max_mm: float, fa_zone: str) -> float:
    """Helper to get the scalar base fraction."""
    return CONSTANTS.COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)

@st.cache_data
def get_coarse_agg_fraction_vectorized(nom_max_mm: float, fa_zone: str, wb_ratio_series: pd.Series) -> pd.Series:
    """Vectorized version for optimization grid."""
    base_fraction = _get_coarse_agg_fraction_base(nom_max_mm, fa_zone)
    correction = ((0.50 - wb_ratio_series) / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return corrected_fraction.clip(0.4, 0.8)

def compute_aggregates_vectorized(binder_series, water_scalar, sp_series, coarse_agg_frac_series, nom_max_mm, density_fa, density_ca):
    """Vectorized calculation of fine/coarse aggregate mass (SSD) based on absolute volume method."""
    vol_cem = binder_series / 3150.0
    vol_wat = water_scalar / 1000.0
    vol_sp = sp_series / 1200.0
    vol_air = CONSTANTS.ENTRAPPED_AIR_VOL.get(int(nom_max_mm), 0.01)
    
    vol_paste_and_air = vol_cem + vol_wat + vol_sp + vol_air
    vol_agg = (1.0 - vol_paste_and_air).clip(lower=0.60) # Capped at 0.6 for stability
    
    vol_coarse = vol_agg * coarse_agg_frac_series
    vol_fine = vol_agg * (1.0 - coarse_agg_frac_series)
    
    mass_fine_ssd = vol_fine * density_fa
    mass_coarse_ssd = vol_coarse * density_ca
    
    return mass_fine_ssd, mass_coarse_ssd

def aggregate_correction_vectorized(delta_moisture_pct: float, agg_mass_ssd_series: pd.Series):
    """Vectorized moisture correction."""
    water_delta_series = (delta_moisture_pct / 100.0) * agg_mass_ssd_series
    corrected_mass_series = agg_mass_ssd_series * (1 + delta_moisture_pct / 100.0)
    return water_delta_series, corrected_mass_series

def pareto_front(df, x_col="cost", y_col="co2"):
    """Identifies the Pareto optimal points."""
    if df.empty: return pd.DataFrame(columns=df.columns)
    sorted_df = df.sort_values(by=[x_col, y_col], ascending=[True, True])
    pareto_points = []
    last_y = float('inf')
    for _, row in sorted_df.iterrows():
        if row[y_col] < last_y:
            pareto_points.append(row)
            last_y = row[y_col]
    return pd.DataFrame(pareto_points).reset_index(drop=True)

def evaluate_purpose_specific_metrics(candidate_meta: dict, purpose: str) -> dict:
    """Calculates metrics relevant to the design purpose."""
    try:
        fck_target = float(candidate_meta.get('fck_target', 30.0))
        wb = float(candidate_meta.get('w_b', 0.5))
        binder = float(candidate_meta.get('cementitious', 350.0))
        water = float(candidate_meta.get('water_target', 180.0))
        modulus_proxy = 5000 * np.sqrt(fck_target) # E_c proxy
        shrinkage_risk_index = (binder * water) / 10000.0 # High binder/water = high shrinkage risk
        fatigue_proxy = (1.0 - wb) * (binder / 1000.0) # Proxy for durability/fatigue
        return {
            "estimated_modulus_proxy (MPa)": round(modulus_proxy, 0),
            "shrinkage_risk_index": round(shrinkage_risk_index, 2),
            "pavement_fatigue_proxy": round(fatigue_proxy, 2)
        }
    except Exception: return {"estimated_modulus_proxy (MPa)": None, "shrinkage_risk_index": None, "pavement_fatigue_proxy": None}

def compute_purpose_penalty_vectorized(df: pd.DataFrame, purpose_profile: dict) -> pd.Series:
    """Vectorized calculation of penalty for violating purpose constraints."""
    if not purpose_profile: return pd.Series(0.0, index=df.index)
    
    penalty = pd.Series(0.0, index=df.index)
    
    penalty += (df['w_b'] - purpose_profile.get('wb_limit', 1.0)).clip(lower=0) * 1000
    penalty += (df['scm_total_frac'] - purpose_profile.get('scm_limit', 0.5)).clip(lower=0) * 100
    penalty += (purpose_profile.get('min_binder', 0.0) - df['binder']).clip(lower=0) * 0.1
    
    return penalty.fillna(0.0)

def get_compliance_reasons_vectorized(df: pd.DataFrame, exposure: str) -> pd.Series:
    """Vectorized check for IS-code compliance and generates failure reasons."""
    limit_wb = CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    limit_cem = CONSTANTS.EXPOSURE_MIN_CEMENT[exposure]
    
    reasons = pd.Series("", index=df.index, dtype=str)
    
    reasons += np.where(df['w_b'] > limit_wb, "Failed W/B ratio (" + df['w_b'].round(3).astype(str) + " > " + str(limit_wb) + "); ", "")
    reasons += np.where(df['binder'] < limit_cem, "Cementitious below minimum (" + df['binder'].round(1).astype(str) + " < " + str(limit_cem) + "); ", "")
    reasons += np.where(df['scm_total_frac'] > 0.50, "SCM fraction exceeds limit (" + (df['scm_total_frac'] * 100).round(0).astype(str) + "% > 50%); ", "")
    reasons += np.where(~((df['total_mass'] >= 2200) & (df['total_mass'] <= 2600)), "Unit weight outside range (" + df['total_mass'].round(1).astype(str) + " not in 2200-2600); ", "")
    
    reasons = reasons.str.strip().str.rstrip(';')
    reasons = np.where(reasons == "", "All IS-code checks passed.", reasons)
    
    return reasons

@st.cache_data
def run_lab_calibration(lab_df):
    """Analyzes lab strength data against predicted target strength."""
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
                "Lab Strength (MPa)": actual_strength,
                "Predicted Target Strength (MPa)": predicted_strength,
                "Error (MPa)": predicted_strength - actual_strength
            })
        except (KeyError, ValueError, TypeError): pass
    if not results: return None, {}
    results_df = pd.DataFrame(results)
    mae = results_df["Error (MPa)"].abs().mean()
    rmse = np.sqrt((results_df["Error (MPa)"] ** 2).mean())
    bias = results_df["Error (MPa)"].mean()
    metrics = {"Mean Absolute Error (MPa)": mae, "Root Mean Squared Error (MPa)": rmse, "Mean Bias (MPa)": bias}
    return results_df, metrics

def simple_parse(text: str) -> dict:
    """Regex-based fallback parser."""
    result = {}
    grade_match = re.search(r"\bM\s*(10|15|20|25|30|35|40|45|50)\b", text, re.IGNORECASE)
    if grade_match: result["grade"] = "M" + grade_match.group(1)
    
    exposure_keys = list(CONSTANTS.EXPOSURE_WB_LIMITS.keys())
    for exp in exposure_keys:
        if re.search(exp, text, re.IGNORECASE): result["exposure"] = exp; break
            
    slump_match = re.search(r"(\d{2,3})\s*mm\s*(?:slump)?", text, re.IGNORECASE) or re.search(r"slump\s*(?:of\s*)?(\d{2,3})\s*mm", text, re.IGNORECASE)
    if slump_match: result["target_slump"] = int(slump_match.group(1))
        
    for ctype in CONSTANTS.CEMENT_TYPES:
        if re.search(ctype.replace(" ", r"\s*"), text, re.IGNORECASE): result["cement_choice"] = ctype; break
            
    nom_match = re.search(r"(\d{2}(\.5)?)\s*mm\s*(?:agg|aggregate)?", text, re.IGNORECASE)
    if nom_match:
        try:
            val = float(nom_match.group(1))
            if val in [10, 12.5, 20, 40]: result["nom_max"] = val
        except: pass
        
    for purp in CONSTANTS.PURPOSE_PROFILES.keys():
        if re.search(purp, text, re.IGNORECASE): result["purpose"] = purp; break

    return result

@st.cache_data(show_spinner="🤖 Parsing prompt with LLM...")
def parse_user_prompt_llm(prompt_text: str) -> dict:
    """Sends user prompt to LLM and returns structured parameter JSON, or falls back to regex."""
    if not st.session_state.get("llm_enabled", False) or client is None:
        return simple_parse(prompt_text)

    system_prompt = f"""You are an expert civil engineer. Extract concrete mix design parameters from the user's prompt. Return ONLY a valid JSON object. Do not include any other text or explanations. Valid keys and values: "grade": ({list(CONSTANTS.GRADE_STRENGTH.keys())}), "exposure": ({list(CONSTANTS.EXPOSURE_WB_LIMITS.keys())}), "cement_type": ({CONSTANTS.CEMENT_TYPES}), "target_slump": (Integer in mm), "nom_max": (Float or Integer in [10, 12.5, 20, 40]), "purpose": ({list(CONSTANTS.PURPOSE_PROFILES.keys())}), "optimize_for": ("CO2" or "Cost"), "use_superplasticizer": (Boolean)."""
    
    try:
        resp = client.chat.completions.create(
            model="mixtral-8x7b-32768",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt_text}],
            temperature=0.0,
            response_format={"type": "json_object"},
        )
        parsed_json = json.loads(resp.choices[0].message.content)
        
        cleaned_data = {} # Filter and validate
        if parsed_json.get("grade") in CONSTANTS.GRADE_STRENGTH: cleaned_data["grade"] = parsed_json["grade"]
        if parsed_json.get("exposure") in CONSTANTS.EXPOSURE_WB_LIMITS: cleaned_data["exposure"] = parsed_json["exposure"]
        if parsed_json.get("cement_type") in CONSTANTS.CEMENT_TYPES: cleaned_data["cement_choice"] = parsed_json["cement_type"]
        if parsed_json.get("nom_max") in [10, 12.5, 20, 40]: cleaned_data["nom_max"] = float(parsed_json["nom_max"])
        if isinstance(parsed_json.get("target_slump"), int): cleaned_data["target_slump"] = max(25, min(180, parsed_json["target_slump"]))
        if parsed_json.get("purpose") in CONSTANTS.PURPOSE_PROFILES: cleaned_data["purpose"] = parsed_json["purpose"]
        if parsed_json.get("optimize_for") in ["CO2", "Cost"]: cleaned_data["optimize_for"] = parsed_json["optimize_for"]
        if isinstance(parsed_json.get("use_superplasticizer"), bool): cleaned_data["use_sp"] = parsed_json["use_superplasticizer"]
        
        return cleaned_data
    except Exception as e:
        # st.error(f"LLM Parser Error: {e}. Falling back to regex.") # Removed for production-readiness
        return simple_parse(prompt_text)

# ==============================================================================
# PART 3: CORE MIX GENERATION & EVALUATION
# ==============================================================================

def evaluate_mix(components_dict, emissions_df, costs_df=None):
    """Calculates final CO2 and Cost for a mix dictionary."""
    comp_items = [(m.strip(), q) for m, q in components_dict.items() if q > 0.01]
    comp_df = pd.DataFrame(comp_items, columns=["Material", "Quantity (kg/m3)"])
    comp_df["Material_norm"] = comp_df["Material"].apply(_normalize_material_value)
    
    df = _merge_and_warn(comp_df, emissions_df, "CO2_Factor(kg_CO2_per_kg)", "warned_emissions", "No emission factors found for")
    df["CO2_Emissions (kg/m3)"] = df["Quantity (kg/m3)"] * df["CO2_Factor(kg_CO2_per_kg)"]

    df = _merge_and_warn(df, costs_df, "Cost(₹/kg)", "warned_costs", "No cost factors found for")
    df["Cost (₹/m3)"] = df["Quantity (kg/m3)"] * df["Cost(₹/kg)"]
    
    df["Material"] = df["Material"].str.title()
    for col in ["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]:
        if col not in df.columns:
            df[col] = 0.0 if "kg" in col or "m3" in col else ""
            
    return df[["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]]

def sanity_check_mix(meta, df):
    """Provides non-IS code warnings for unusual proportions."""
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
    """Checks all compliance rules and returns flags, reasons, warnings, and derived metrics."""
    checks = {}
    try: checks["W/B ≤ exposure limit"] = float(meta["w_b"]) <= CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    except: checks["W/B ≤ exposure limit"] = False
    try: checks["Min cementitious met"] = float(meta["cementitious"]) >= float(CONSTANTS.EXPOSURE_MIN_CEMENT[exposure])
    except: checks["Min cementitious met"] = False
    try: checks["SCM ≤ 50%"] = float(meta.get("scm_total_frac", 0.0)) <= 0.50
    except: checks["SCM ≤ 50%"] = False
    try: checks["Unit weight 2200–2600 kg/m³"] = 2200.0 <= float(mix_df["Quantity (kg/m3)"].sum()) <= 2600.0
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
        derived.update({"purpose": meta["purpose"], "purpose_penalty": meta.get("purpose_penalty"), "composite_score": meta.get("composite_score"), "purpose_metrics": meta.get("purpose_metrics")})
    
    warnings = sanity_check_mix(meta, mix_df)
    reasons_fail = [f"IS Code Fail: {k}" for k, v in checks.items() if not v]
    feasible = len(reasons_fail) == 0
    return feasible, reasons_fail, warnings, derived, checks

def generate_mix(grade, exposure, nom_max, target_slump, agg_shape, fine_zone, emissions, costs, cement_choice, material_props, use_sp=True, sp_reduction=0.18, optimize_cost=False, wb_min=0.35, wb_steps=6, max_flyash_frac=0.3, max_ggbs_frac=0.5, scm_step=0.1, fine_fraction_override=None, purpose='General', purpose_profile=None, purpose_weights=None, enable_purpose_optimization=False, st_progress=None):
    """
    Core mix design optimizer.
    Generates a grid of cementitious combinations, calculates quantities,
    checks feasibility, and selects the best one based on the optimization goal.
    """
    if st_progress: st_progress.progress(0.0, text="Initializing parameters...")
    
    # 1. Setup Parameters
    w_b_limit = CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    min_cem_exp = CONSTANTS.EXPOSURE_MIN_CEMENT[exposure]
    target_water = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = CONSTANTS.BINDER_RANGES.get(grade, (300, 500))
    density_fa, density_ca = material_props['sg_fa'] * 1000, material_props['sg_ca'] * 1000
    
    purpose_profile = purpose_profile or CONSTANTS.PURPOSE_PROFILES['General']
    purpose_weights = purpose_weights or CONSTANTS.PURPOSE_PROFILES['General']['weights']

    # 2. Pre-compute Cost/CO2 Factors
    if st_progress: st_progress.progress(0.05, text="Pre-computing cost/CO2 factors...")
    norm_cement_choice = _normalize_material_value(cement_choice)
    materials_to_calc = [norm_cement_choice, CONSTANTS.NORM_FLYASH, CONSTANTS.NORM_GGBS, CONSTANTS.NORM_WATER, CONSTANTS.NORM_SP, CONSTANTS.NORM_FINE_AGG, CONSTANTS.NORM_COARSE_AGG]
    co2_factors, cost_factors = _get_material_factors(materials_to_calc, emissions, costs)

    # 3. Create Parameter Grid
    if st_progress: st_progress.progress(0.1, text="Creating optimization grid...")
    wb_values = np.linspace(float(wb_min), float(w_b_limit), int(wb_steps))
    flyash_options = np.arange(0.0, max_flyash_frac + 1e-9, scm_step)
    ggbs_options = np.arange(0.0, max_ggbs_frac + 1e-9, scm_step)
    
    grid_params = list(product(wb_values, flyash_options, ggbs_options))
    grid_df = pd.DataFrame(grid_params, columns=['wb_input', 'flyash_frac', 'ggbs_frac'])
    grid_df = grid_df[grid_df['flyash_frac'] + grid_df['ggbs_frac'] <= 0.50].copy()
    if grid_df.empty: return None, None, []

    # 4. Vectorized Mix Calculations
    if st_progress: st_progress.progress(0.2, text="Calculating binder properties...")
    grid_df['binder_for_strength'] = target_water / grid_df['wb_input']
    grid_df['binder'] = np.maximum(np.maximum(grid_df['binder_for_strength'], min_cem_exp), min_b_grade)
    grid_df['binder'] = np.minimum(grid_df['binder'], max_b_grade)
    grid_df['w_b'] = target_water / grid_df['binder']
    
    grid_df['scm_total_frac'] = grid_df['flyash_frac'] + grid_df['ggbs_frac']
    grid_df['cement'] = grid_df['binder'] * (1 - grid_df['scm_total_frac'])
    grid_df['flyash'] = grid_df['binder'] * grid_df['flyash_frac']
    grid_df['ggbs'] = grid_df['binder'] * grid_df['ggbs_frac']
    grid_df['sp'] = (0.01 * grid_df['binder']) if use_sp else 0.0
    
    if st_progress: st_progress.progress(0.3, text="Calculating aggregate proportions...")
    grid_df['coarse_agg_fraction'] = 1.0 - fine_fraction_override if fine_fraction_override is not None else get_coarse_agg_fraction_vectorized(nom_max, fine_zone, grid_df['w_b'])
    
    grid_df['fine_ssd'], grid_df['coarse_ssd'] = compute_aggregates_vectorized(grid_df['binder'], target_water, grid_df['sp'], grid_df['coarse_agg_fraction'], nom_max, density_fa, density_ca)
    
    water_delta_fa_series, grid_df['fine_wet'] = aggregate_correction_vectorized(material_props['moisture_fa'], grid_df['fine_ssd'])
    water_delta_ca_series, grid_df['coarse_wet'] = aggregate_correction_vectorized(material_props['moisture_ca'], grid_df['coarse_ssd'])
    grid_df['water_final'] = (target_water - (water_delta_fa_series + water_delta_ca_series)).clip(lower=5.0)

    # 5. Vectorized Cost & CO2 Calculations
    if st_progress: st_progress.progress(0.5, text="Calculating cost and CO2...")
    quantities = {
        'cement': grid_df['cement'], 'flyash': grid_df['flyash'], 'ggbs': grid_df['ggbs'],
        'water': grid_df['water_final'], 'sp': grid_df['sp'],
        'fine': grid_df['fine_wet'], 'coarse': grid_df['coarse_wet']
    }
    norm_names = {
        'cement': norm_cement_choice, 'flyash': CONSTANTS.NORM_FLYASH, 'ggbs': CONSTANTS.NORM_GGBS,
        'water': CONSTANTS.NORM_WATER, 'sp': CONSTANTS.NORM_SP,
        'fine': CONSTANTS.NORM_FINE_AGG, 'coarse': CONSTANTS.NORM_COARSE_AGG
    }

    grid_df['co2_total'] = sum(quantities[k] * co2_factors.get(norm_names[k], 0.0) for k in quantities)
    grid_df['cost_total'] = sum(quantities[k] * cost_factors.get(norm_names[k], 0.0) for k in quantities)

    # 6. Vectorized Feasibility & Purpose Scoring
    if st_progress: st_progress.progress(0.7, text="Checking compliance and purpose-fit...")
    grid_df['total_mass'] = quantities['cement'] + quantities['flyash'] + quantities['ggbs'] + quantities['water'] + quantities['sp'] + quantities['fine'] + quantities['coarse']
    
    grid_df['feasible'] = (grid_df['w_b'] <= w_b_limit) & \
                          (grid_df['binder'] >= min_cem_exp) & \
                          (grid_df['scm_total_frac'] <= 0.50) & \
                          ((grid_df['total_mass'] >= 2200.0) & (grid_df['total_mass'] <= 2600.0))
    
    grid_df['reasons'] = get_compliance_reasons_vectorized(grid_df, exposure)
    grid_df['purpose_penalty'] = compute_purpose_penalty_vectorized(grid_df, purpose_profile)
    grid_df['purpose'] = purpose

    # 7. Candidate Selection
    if st_progress: st_progress.progress(0.8, text="Finding best mix design...")
    feasible_candidates_df = grid_df[grid_df['feasible']].copy()
    
    if feasible_candidates_df.empty:
        trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
        return None, None, trace_df.to_dict('records')

    # 8. Optimization & Selection
    if not enable_purpose_optimization or purpose == 'General':
        objective_col = 'cost_total' if optimize_cost else 'co2_total'
        feasible_candidates_df['composite_score'] = np.nan
        best_idx = feasible_candidates_df[objective_col].idxmin()
    else:
        feasible_candidates_df['norm_co2'] = _minmax_scale(feasible_candidates_df['co2_total'])
        feasible_candidates_df['norm_cost'] = _minmax_scale(feasible_candidates_df['cost_total'])
        feasible_candidates_df['norm_purpose'] = _minmax_scale(feasible_candidates_df['purpose_penalty'])
        
        w_co2, w_cost, w_purpose = purpose_weights['co2'], purpose_weights['cost'], purpose_weights['purpose']
        feasible_candidates_df['composite_score'] = w_co2 * feasible_candidates_df['norm_co2'] + w_cost * feasible_candidates_df['norm_cost'] + w_purpose * feasible_candidates_df['norm_purpose']
        best_idx = feasible_candidates_df['composite_score'].idxmin()

    best_meta_series = feasible_candidates_df.loc[best_idx]

    # 9. Re-hydrate Final Mix & Trace
    if st_progress: st_progress.progress(0.9, text="Generating final mix report...")
    
    best_mix_dict = {
        cement_choice: best_meta_series['cement'], "Fly Ash": best_meta_series['flyash'], "GGBS": best_meta_series['ggbs'],
        "Water": best_meta_series['water_final'], "PCE Superplasticizer": best_meta_series['sp'],
        "Fine Aggregate": best_meta_series['fine_wet'], "Coarse Aggregate": best_meta_series['coarse_wet']
    }
    
    best_df = evaluate_mix(best_mix_dict, emissions, costs)
    
    best_meta = best_meta_series.to_dict()
    best_meta.update({
        "cementitious": best_meta_series['binder'], "cement": best_meta_series['cement'],
        "flyash": best_meta_series['flyash'], "ggbs": best_meta_series['ggbs'],
        "water_target": target_water, "water_final": best_meta_series['water_final'], "sp": best_meta_series['sp'],
        "fine": best_meta_series['fine_wet'], "coarse": best_meta_series['coarse_wet'],
        "grade": grade, "exposure": exposure, "nom_max": nom_max, "slump": target_slump,
        "binder_range": (min_b_grade, max_b_grade), "material_props": material_props,
        "purpose_metrics": evaluate_purpose_specific_metrics(best_meta, purpose)
    })
    
    trace_df = grid_df.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
    score_cols = ['composite_score', 'norm_co2', 'norm_cost', 'norm_purpose']
    if all(col in feasible_candidates_df.columns for col in score_cols):
        scores_to_merge = feasible_candidates_df[score_cols]
        trace_df = trace_df.merge(scores_to_merge, left_index=True, right_index=True, how='left')
    
    return best_df, best_meta, trace_df.to_dict('records')

def generate_baseline(grade, exposure, nom_max, target_slump, agg_shape, fine_zone, emissions, costs, cement_choice, material_props, use_sp=True, sp_reduction=0.18, purpose='General', purpose_profile=None):
    """Generates a non-optimized, IS-code compliant mix using max allowed w/b ratio and 100% cement."""
    w_b_limit = CONSTANTS.EXPOSURE_WB_LIMITS[exposure]
    min_cem_exp = CONSTANTS.EXPOSURE_MIN_CEMENT[exposure]
    water_target = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = CONSTANTS.BINDER_RANGES.get(grade, (300, 500))

    binder_for_wb = water_target / w_b_limit
    cementitious = min(max(binder_for_wb, min_cem_exp, min_b_grade), max_b_grade)
    actual_wb = water_target / cementitious
    sp = 0.01 * cementitious if use_sp else 0.0
    coarse_agg_frac = get_coarse_agg_fraction_vectorized(nom_max, fine_zone, pd.Series([actual_wb])).iloc[0] # Use the vectorized function, but extract the single scalar result
    density_fa, density_ca = material_props['sg_fa'] * 1000, material_props['sg_ca'] * 1000
    
    # Scalar versions of aggregate calculation needed for baseline only
    vol_cem = cementitious / 3150.0
    vol_wat = water_target / 1000.0
    vol_sp = sp / 1200.0
    vol_air = CONSTANTS.ENTRAPPED_AIR_VOL.get(int(nom_max), 0.01)
    vol_paste_and_air = vol_cem + vol_wat + vol_sp + vol_air
    vol_agg = max(0.60, 1.0 - vol_paste_and_air)
    fine_ssd = vol_agg * (1.0 - coarse_agg_frac) * density_fa
    coarse_ssd = vol_agg * coarse_agg_frac * density_ca
    
    water_delta_fa, fine_wet = aggregate_correction_vectorized(material_props['moisture_fa'], pd.Series([fine_ssd])).apply(lambda x: x.iloc[0])
    water_delta_ca, coarse_wet = aggregate_correction_vectorized(material_props['moisture_ca'], pd.Series([coarse_ssd])).apply(lambda x: x.iloc[0])
    
    water_final = max(5.0, water_target - (water_delta_fa + water_delta_ca))

    mix = {cement_choice: cementitious,"Fly Ash": 0.0,"GGBS": 0.0,"Water": water_final, "PCE Superplasticizer": sp,"Fine Aggregate": fine_wet,"Coarse Aggregate": coarse_wet}
    df = evaluate_mix(mix, emissions, costs)
    
    meta = {
        "w_b": actual_wb, "cementitious": cementitious, "cement": cementitious, "flyash": 0.0, "ggbs": 0.0,
        "water_target": water_target, "water_final": water_final, "sp": sp, "fine": fine_wet, "coarse": coarse_wet, 
        "scm_total_frac": 0.0, "grade": grade, "exposure": exposure, "nom_max": nom_max, "slump": target_slump,
        "co2_total": float(df["CO2_Emissions (kg/m3)"].sum()), "cost_total": float(df["Cost (₹/m3)"].sum()),
        "coarse_agg_fraction": coarse_agg_frac, "material_props": material_props, "binder_range": (min_b_grade, max_b_grade),
        "purpose": purpose, "composite_score": np.nan
    }
    
    purpose_profile = purpose_profile or CONSTANTS.PURPOSE_PROFILES.get(purpose, CONSTANTS.PURPOSE_PROFILES['General'])
    meta.update({"purpose_metrics": evaluate_purpose_specific_metrics(meta, purpose), "purpose_penalty": compute_purpose_penalty_vectorized(pd.DataFrame({'w_b': [actual_wb], 'scm_total_frac': [0.0], 'binder': [cementitious]}), purpose_profile).iloc[0]})
    return df, meta

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
    """Generates a comparison bar chart."""
    with st_col:
        st.subheader(title)
        chart_data = pd.DataFrame({'Mix Type': ['Baseline OPC', 'CivilGPT Optimized'], y_label: [base_val, opt_val]})
        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(chart_data['Mix Type'], chart_data[y_label], color=colors)
        ax.set_ylabel(y_label)
        ax.bar_label(bars, fmt=fmt_str)
        st.pyplot(fig)

def display_mix_details(title, df, meta, exposure):
    """Renders mix proportions, compliance checks, and key metrics."""
    st.header(title)
    
    purpose = meta.get("purpose", "General")
    metrics = [
        ("💧 Water/Binder Ratio", f"{meta['w_b']:.3f}"),
        ("📦 Total Binder (kg/m³)", f"{meta['cementitious']:.1f}"),
        ("🎯 Target Strength (MPa)", f"{meta['fck_target']:.1f}"),
        ("⚖️ Unit Weight (kg/m³)", f"{df['Quantity (kg/m3)'].sum():.1f}")
    ]
    if purpose != "General":
        metrics.extend([
            ("🛠️ Design Purpose", purpose),
            ("⚠️ Purpose Penalty", f"{meta.get('purpose_penalty', 0.0):.2f}"),
        ])
        if "composite_score" in meta and not pd.isna(meta["composite_score"]):
             metrics.append(("🎯 Composite Score", f"{meta.get('composite_score', 0.0):.3f}"))
             
    cols = st.columns(len(metrics))
    for i, (label, value) in enumerate(metrics):
        cols[i % len(cols)].metric(label, value)

    st.subheader("Mix Proportions (per m³)")
    st.dataframe(df.style.format({
        "Quantity (kg/m3)": "{:.2f}", "CO2_Factor(kg_CO2_per_kg)": "{:.3f}",
        "CO2_Emissions (kg/m3)": "{:.2f}", "Cost(₹/kg)": "₹{:.2f}", "Cost (₹/m3)": "₹{:.2f}"
    }), use_container_width=True)

    st.subheader("Compliance & Sanity Checks (IS 10262 & IS 456)")
    is_feasible, fail_reasons, warnings, derived, checks_dict = check_feasibility(df, meta, exposure)

    st.success("✅ This mix design is compliant with IS code requirements.", icon="👍") if is_feasible else st.error(f"❌ This mix fails {len(fail_reasons)} IS code compliance check(s): " + ", ".join(fail_reasons), icon="🚨")
    for warning in warnings: st.warning(warning, icon="⚠️")
    if purpose != "General" and "purpose_metrics" in meta:
        with st.expander(f"Show Estimated Purpose-Specific Metrics ({purpose})"): st.json(meta["purpose_metrics"])
    with st.expander("Show detailed calculation parameters"): st.json({k: v for k, v in derived.items() if k != "purpose_metrics"})

def display_calculation_walkthrough(meta):
    """Renders the step-by-step IS 10262 calculation narrative."""
    st.header("Step-by-Step Calculation Walkthrough")
    st.markdown(f"""
    This is a summary of how the **Optimized Mix** was designed according to **IS 10262:2019**.

    #### 1. Target Mean Strength
    - **Characteristic Strength (fck):** `{meta['fck']}` MPa
    - **Assumed Standard Deviation (S):** `{meta['stddev_S']}` MPa
    - **Target Mean Strength (f'ck):** `fck + 1.65 * S = {meta['fck']} + 1.65 * {meta['stddev_S']} =` **`{meta['fck_target']:.2f}` MPa**

    #### 2. Water Content
    - **Target Water (SSD basis):** **`{meta['water_target']:.1f}` kg/m³**

    #### 3. Water-Binder (w/b) Ratio
    - **Selected w/b Ratio:** **`{meta['w_b']:.3f}`** (Meets Max. w/b limit of `{CONSTANTS.EXPOSURE_WB_LIMITS[meta['exposure']]}` for `{meta['exposure']}` exposure.)

    #### 4. Binder Content
    - **Final Adjusted Binder Content:** **`{meta['cementitious']:.1f}` kg/m³** (Meets Min. cementitious content of `{CONSTANTS.EXPOSURE_MIN_CEMENT[meta['exposure']]}` kg/m³ and grade range.)

    #### 5. SCM & Cement Content
    - **Selected SCM Fraction:** `{meta['scm_total_frac']*100:.0f}%`
    - **Material Quantities:** **Cement:** `{meta['cement']:.1f}` kg/m³, **Fly Ash:** `{meta['flyash']:.1f}` kg/m³, **GGBS:** `{meta['ggbs']:.1f}` kg/m³

    #### 6. Aggregate Proportioning (IS 10262, Table 5)
    - **Coarse Aggregate Fraction (by volume):** **`{meta['coarse_agg_fraction']:.3f}`**

    #### 7. Final Quantities (with Moisture Correction)
    - **Final Batch Weights (Wet):** **Water:** **`{meta['water_final']:.1f}` kg/m³**, **Fine Aggregate:** **`{meta['fine']:.1f}` kg/m³**, **Coarse Aggregate:** **`{meta['coarse']:.1f}` kg/m³**
    """)

# ==============================================================================
# PART 5: CORE GENERATION LOGIC (MODULARIZED)
# ==============================================================================

def run_generation_logic(inputs: dict, emissions_df: pd.DataFrame, costs_df: pd.DataFrame, purpose_profiles_data: dict, st_progress=None):
    """
    Modular function to run mix generation. Sets st.session_state.results upon completion.
    """
    try:
        # 1. Validate and Setup Parameters
        min_grade_req = CONSTANTS.EXPOSURE_MIN_GRADE[inputs["exposure"]]
        grade_order = list(CONSTANTS.GRADE_STRENGTH.keys())
        if grade_order.index(inputs["grade"]) < grade_order.index(min_grade_req):
            st.warning(f"For **{inputs['exposure']}** exposure, IS 456 recommends a minimum grade of **{min_grade_req}**. The grade has been automatically updated.", icon="⚠️")
            inputs["grade"] = min_grade_req
            st.session_state.final_inputs["grade"] = min_grade_req

        purpose = inputs.get('purpose', 'General')
        purpose_profile = purpose_profiles_data.get(purpose, purpose_profiles_data['General'])
        enable_purpose_opt = inputs.get('enable_purpose_optimization', False) and purpose != 'General'
        
        info_msg = f"🚀 Running composite optimization for **{purpose}**." if enable_purpose_opt else f"Running single-objective optimization for **{inputs.get('optimize_for', 'CO₂ Emissions')}**."
        if not st.session_state.get("chat_mode", False): st.info(info_msg, icon="🛠️" if enable_purpose_opt else "⚙️")
        
        fck = CONSTANTS.GRADE_STRENGTH[inputs["grade"]]
        S = CONSTANTS.QC_STDDEV[inputs.get("qc_level", "Good")]
        fck_target = fck + 1.65 * S
        
        # 2. Run Optimization
        opt_df, opt_meta, trace = generate_mix(
            inputs["grade"], inputs["exposure"], inputs["nom_max"], inputs["target_slump"], inputs["agg_shape"], inputs["fine_zone"],
            emissions_df, costs_df, inputs["cement_choice"], material_props=inputs["material_props"], use_sp=inputs["use_sp"], 
            optimize_cost=inputs["optimize_cost"], purpose=purpose, purpose_profile=purpose_profile, purpose_weights=inputs["purpose_weights"],
            enable_purpose_optimization=enable_purpose_opt, st_progress=st_progress, **inputs.get("calibration_kwargs", {})
        )
        
        if st_progress: st_progress.progress(0.95, text="Generating baseline comparison...")
        
        # 3. Run Baseline
        base_df, base_meta = generate_baseline(
            inputs["grade"], inputs["exposure"], inputs["nom_max"], inputs["target_slump"], inputs["agg_shape"], inputs["fine_zone"],
            emissions_df, costs_df, inputs["cement_choice"], material_props=inputs["material_props"], use_sp=inputs.get("use_sp", True), 
            purpose=purpose, purpose_profile=purpose_profile
        )
        
        if st_progress: st_progress.progress(1.0, text="Optimization complete!"); st_progress.empty()

        # 4. Store Results
        if opt_df is None or base_df is None:
            st.error("Could not find a feasible mix design with the given constraints. Try adjusting the parameters.", icon="❌")
            st.session_state.results = {"success": False, "trace": trace}
        else:
            if not st.session_state.get("chat_mode", False): st.success(f"Successfully generated mix designs for **{inputs['grade']}** concrete in **{inputs['exposure']}** conditions.", icon="✅")
            
            for m in (opt_meta, base_meta):
                m.update({"fck": fck, "fck_target": round(fck_target, 1), "stddev_S": S, "qc_level": inputs.get("qc_level", "Good"), "agg_shape": inputs.get("agg_shape"), "fine_zone": inputs.get("fine_zone")})
                
            st.session_state.results = {
                "success": True, "opt_df": opt_df, "opt_meta": opt_meta, "base_df": base_df, "base_meta": base_meta,
                "trace": trace, "inputs": inputs, "fck_target": fck_target, "fck": fck, "S": S
            }
            
    except Exception as e:
        # st.exception(e) # Removed for production-readiness but kept the trace
        # import traceback; st.exception(traceback.format_exc())
        st.error(f"An unexpected error occurred: {e}", icon="💥")
        st.session_state.results = {"success": False, "trace": None}

# ==============================================================================
# PART 6: STREAMLIT APP (UI Sub-modules)
# ==============================================================================

def run_chat_interface(purpose_profiles_data: dict):
    """Renders the Chat Mode UI and handles chat logic."""
    st.title("💬 CivilGPT Chat Mode")
    st.markdown("Welcome to the conversational interface. Describe your concrete mix needs, and I'll ask for clarifications.")
    
    # Display chat history
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    # Display generated results summary in chat
    if "results" in st.session_state and st.session_state.results.get("success") and not st.session_state.get("chat_results_displayed", False):
        results = st.session_state.results
        opt_meta, base_meta = results["opt_meta"], results["base_meta"]
        reduction = (base_meta["co2_total"] - opt_meta["co2_total"]) / base_meta["co2_total"] * 100 if base_meta["co2_total"] > 0 else 0.0
        cost_savings = base_meta["cost_total"] - opt_meta["cost_total"]

        summary_msg = f"✅ CivilGPT has designed an **{opt_meta['grade']}** mix for **{opt_meta['exposure']}** exposure using **{results['inputs']['cement_choice']}**.\n\nHere's a quick summary:\n- **🌱 CO₂ reduced by {reduction:.1f}%**\n- **💰 Cost saved ₹{cost_savings:,.0f} / m³**\n- **⚖️ Final w/b ratio:** {opt_meta['w_b']:.3f}\n- **📦 Total Binder:** {opt_meta['cementitious']:.1f} kg/m³\n- **♻️ SCM Content:** {opt_meta['scm_total_frac']*100:.0f}%"
        st.session_state.chat_history.append({"role": "assistant", "content": summary_msg})
        st.session_state.chat_results_displayed = True
        st.rerun()

    # Show "Open Report" button if results are ready
    if st.session_state.get("chat_results_displayed", False):
        st.info("Your full mix report is ready. You can ask for refinements or open the full report.")
        if st.button("📊 Open Full Mix Report & Switch to Manual Mode", use_container_width=True, type="primary"):
            st.session_state.chat_mode = False
            st.session_state.active_tab_name = "📥 **Downloads & Reports**"
            st.toast("Opening full report...", icon="📊")
            st.rerun()

    # Handle new user prompt
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
            st.session_state.chat_history.append({"role": "assistant", "content": get_clarification_question(field_to_ask)})
        else:
            st.session_state.chat_history.append({"role": "assistant", "content": "✅ Great, I have all your requirements. Generating your sustainable mix design now..."})
            st.session_state.run_chat_generation = True
            st.session_state.chat_results_displayed = False
            if "results" in st.session_state: del st.session_state.results
            
        st.rerun()

def run_manual_interface(purpose_profiles_data: dict, materials_df: pd.DataFrame, emissions_df: pd.DataFrame, costs_df: pd.DataFrame):
    """Renders the Manual/Original UI and handles its logic."""
    
    st.title("🧱 CivilGPT: Sustainable Concrete Mix Designer")
    st.markdown("##### An AI-powered tool for creating **IS 10262:2019 compliant** concrete mixes, optimized for low carbon footprint.")

    # 1. PROMPT INPUT & RUN BUTTON
    col1, col2 = st.columns([0.7, 0.3])
    with col1:
        user_text = st.text_area("**Describe Your Requirements**", height=100, placeholder="e.g., Design an M30 grade concrete for severe exposure using OPC 43. Target a slump of 125 mm with 20 mm aggregates.", label_visibility="collapsed", key="user_text_input")
    with col2:
        st.write(""); st.write("")
        run_button = st.button("🚀 Generate Mix Design", use_container_width=True, type="primary")

    manual_mode = st.toggle("⚙️ Switch to Advanced Manual Input")

    # 2. SIDEBAR INPUTS (Unified logic using locals)
    if manual_mode:
        st.sidebar.header("📝 Manual Mix Inputs")
        st.sidebar.markdown("---")
        
        # Core Requirements
        st.sidebar.subheader("Core Requirements")
        grade = st.sidebar.selectbox("Concrete Grade", list(CONSTANTS.GRADE_STRENGTH.keys()), index=4)
        exposure = st.sidebar.selectbox("Exposure Condition", list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()), index=2)
        
        # Workability & Materials
        st.sidebar.subheader("Workability & Materials")
        target_slump = st.sidebar.slider("Target Slump (mm)", 25, 180, 100, 5)
        cement_choice = st.sidebar.selectbox("Cement Type", CONSTANTS.CEMENT_TYPES, index=1)
        nom_max = st.sidebar.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=2)
        agg_shape = st.sidebar.selectbox("Coarse Aggregate Shape", list(CONSTANTS.AGG_SHAPE_WATER_ADJ.keys()), index=0)
        fine_zone = st.sidebar.selectbox("Fine Aggregate Zone (IS 383)", ["Zone I","Zone II","Zone III","Zone IV"], index=1)
        use_sp = st.sidebar.checkbox("Use Superplasticizer (PCE)", True)
        
        # Optimization Goal
        st.sidebar.subheader("Optimization Goal")
        purpose = st.sidebar.selectbox("Design Purpose", list(purpose_profiles_data.keys()), index=0, key="purpose_select", help=purpose_profiles_data.get(st.session_state.get("purpose_select", "General"), {}).get("description", "Select the structural element."))
        optimize_for = st.sidebar.selectbox("Optimization Objective", ["CO₂ Emissions", "Cost"], index=0, key="optimize_for_select")
        optimize_cost = (optimize_for == "Cost")
        enable_purpose_optimization = st.sidebar.checkbox("Enable Purpose-Based Composite Optimization", value=(purpose != 'General'), key="enable_purpose")

        # Dynamic Weights
        purpose_weights = purpose_profiles_data['General']['weights']
        if enable_purpose_optimization and purpose != 'General':
            with st.sidebar.expander("Adjust Optimization Weights", expanded=True):
                default_weights = purpose_profiles_data.get(purpose, {}).get('weights', purpose_profiles_data['General']['weights'])
                w_co2 = st.slider("🌱 CO₂ Weight", 0.0, 1.0, default_weights['co2'], 0.05, key="w_co2")
                w_cost = st.slider("💰 Cost Weight", 0.0, 1.0, default_weights['cost'], 0.05, key="w_cost")
                w_purpose = st.slider("🛠️ Purpose-Fit Weight", 0.0, 1.0, default_weights['purpose'], 0.05, key="w_purpose")
                total_w = w_co2 + w_cost + w_purpose
                if total_w > 0: purpose_weights = {"co2": w_co2 / total_w, "cost": w_cost / total_w, "purpose": w_purpose / total_w}

        # Advanced Parameters
        st.sidebar.subheader("Advanced Parameters")
        with st.sidebar.expander("QA/QC"): qc_level = st.selectbox("Quality Control Level", list(CONSTANTS.QC_STDDEV.keys()), index=0)
        with st.sidebar.expander("Material Properties (from Library or Manual)"):
            sg_fa_default, moisture_fa_default = 2.65, 1.0
            sg_ca_default, moisture_ca_default = 2.70, 0.5
            # Simplified material property loading based on the global state of the shared materials_df
            if materials_df is not None and not materials_df.empty:
                mat_df = materials_df.copy(); mat_df['Material'] = mat_df['Material'].str.strip().str.lower()
                fa_row = mat_df[mat_df['Material'] == 'fine aggregate']; ca_row = mat_df[mat_df['Material'] == 'coarse aggregate']
                if not fa_row.empty and 'SpecificGravity' in fa_row: sg_fa_default = float(fa_row['SpecificGravity'].iloc[0])
                if not fa_row.empty and 'MoistureContent' in fa_row: moisture_fa_default = float(fa_row['MoistureContent'].iloc[0])
                if not ca_row.empty and 'SpecificGravity' in ca_row: sg_ca_default = float(ca_row['SpecificGravity'].iloc[0])
                if not ca_row.empty and 'MoistureContent' in ca_row: moisture_ca_default = float(ca_row['MoistureContent'].iloc[0])

            sg_fa = st.number_input("Specific Gravity (FA)", 2.0, 3.0, sg_fa_default, 0.01)
            moisture_fa = st.number_input("Free Moisture Content % (FA)", -2.0, 5.0, moisture_fa_default, 0.1)
            sg_ca = st.number_input("Specific Gravity (CA)", 2.0, 3.0, sg_ca_default, 0.01)
            moisture_ca = st.number_input("Free Moisture Content % (CA)", -2.0, 5.0, moisture_ca_default, 0.1)

        # Calibration Overrides
        calibration_kwargs = {}
        with st.sidebar.expander("Calibration & Tuning (Developer)"):
            enable_calibration_overrides = st.checkbox("Enable calibration overrides", False)
            if enable_calibration_overrides:
                calibration_kwargs = {
                    "wb_min": st.number_input("W/B search min", 0.30, 0.45, 0.35, 0.01),
                    "wb_steps": st.slider("W/B search steps", 3, 15, 6, 1),
                    "max_flyash_frac": st.slider("Max Fly Ash fraction", 0.0, 0.5, 0.30, 0.05),
                    "max_ggbs_frac": st.slider("Max GGBS fraction", 0.0, 0.5, 0.50, 0.05),
                    "scm_step": st.slider("SCM fraction step", 0.05, 0.25, 0.10, 0.05),
                    "fine_fraction_override": st.slider("Fine Aggregate Fraction (override)", 0.30, 0.50, 0.40, 0.01)
                }
        
        use_llm_parser = st.sidebar.checkbox("Use Groq LLM Parser", value=False, disabled=not st.session_state.get("llm_enabled", False))
        lab_csv_to_use = st.session_state.get('lab_csv')
        fine_csv_to_use = st.session_state.get('fine_csv')
        coarse_csv_to_use = st.session_state.get('coarse_csv')

    else: # Default values when manual mode is off
        grade, exposure, cement_choice = "M30", "Severe", "OPC 43"
        nom_max, agg_shape, target_slump = 20, "Angular (baseline)", 125
        use_sp, optimize_cost, fine_zone = True, False, "Zone II"
        optimize_for = "CO₂ Emissions"
        qc_level = "Good"
        sg_fa, moisture_fa = 2.65, 1.0
        sg_ca, moisture_ca = 2.70, 0.5
        use_llm_parser = False
        purpose = "General"
        enable_purpose_optimization = False
        purpose_weights = purpose_profiles_data['General']['weights']
        calibration_kwargs = {}
        lab_csv_to_use = st.session_state.get('lab_csv')
        fine_csv_to_use = st.session_state.get('fine_csv')
        coarse_csv_to_use = st.session_state.get('coarse_csv')

    # 3. CLARIFICATION & TRIGGER LOGIC
    if 'clarification_needed' not in st.session_state: st.session_state.clarification_needed = False
    if 'run_generation_manual' not in st.session_state: st.session_state.run_generation_manual = False
    if 'final_inputs' not in st.session_state: st.session_state.final_inputs = {}

    if run_button:
        st.session_state.run_generation_manual = True
        st.session_state.clarification_needed = False
        if 'results' in st.session_state: del st.session_state.results

        material_props = {'sg_fa': sg_fa, 'moisture_fa': moisture_fa, 'sg_ca': sg_ca, 'moisture_ca': moisture_ca}
        
        inputs = { 
            "grade": grade, "exposure": exposure, "cement_choice": cement_choice, "nom_max": nom_max, "agg_shape": agg_shape, "target_slump": target_slump, 
            "use_sp": use_sp, "optimize_cost": optimize_cost, "qc_level": qc_level, "fine_zone": fine_zone, "material_props": material_props,
            "purpose": purpose, "enable_purpose_optimization": enable_purpose_optimization, "purpose_weights": purpose_weights, "optimize_for": optimize_for,
            "calibration_kwargs": calibration_kwargs
        }

        if user_text.strip() and not manual_mode:
            with st.spinner("🤖 Parsing your request..."):
                inputs, msgs, _ = parse_user_prompt_llm(user_text) if use_llm_parser else simple_parse(user_text) # Simplified parser call
                # Re-integrate inputs from manual defaults if parser misses them
                inputs.update({k: v for k, v in st.session_state.final_inputs.items() if k not in inputs and k in CONSTANTS.CHAT_REQUIRED_FIELDS})
            if msgs: st.info(" ".join(msgs), icon="💡")
            
            required_fields = CONSTANTS.CHAT_REQUIRED_FIELDS
            missing_fields = [f for f in required_fields if inputs.get(f) is None]

            if missing_fields:
                st.session_state.clarification_needed = True
                st.session_state.final_inputs.update(inputs) # Preserve parsed values
                st.session_state.missing_fields = missing_fields
                st.session_state.run_generation_manual = False
            else:
                st.session_state.run_generation_manual = True
                st.session_state.final_inputs = inputs
        
        else:
            st.session_state.run_generation_manual = True
            st.session_state.final_inputs = inputs


    if st.session_state.get('clarification_needed', False):
        st.markdown("---"); st.warning("Your request is missing some details. Please confirm the following to continue.", icon="🤔")
        
        CLARIFICATION_WIDGETS = {
            "grade": lambda v: st.selectbox("Concrete Grade", list(CONSTANTS.GRADE_STRENGTH.keys()), index=list(CONSTANTS.GRADE_STRENGTH.keys()).index(v) if v in CONSTANTS.GRADE_STRENGTH else 4, key="clar_grade"),
            "exposure": lambda v: st.selectbox("Exposure Condition", list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()), index=list(CONSTANTS.EXPOSURE_WB_LIMITS.keys()).index(v) if v in CONSTANTS.EXPOSURE_WB_LIMITS else 2, key="clar_exposure"),
            "target_slump": lambda v: st.slider("Target Slump (mm)", 25, 180, v if isinstance(v, int) else 100, 5, key="clar_slump"),
            "cement_choice": lambda v: st.selectbox("Cement Type", CONSTANTS.CEMENT_TYPES, index=CONSTANTS.CEMENT_TYPES.index(v) if v in CONSTANTS.CEMENT_TYPES else 1, key="clar_cement"),
            "nom_max": lambda v: st.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=[10, 12.5, 20, 40].index(v) if v in [10, 12.5, 20, 40] else 2, key="clar_nommax"),
        }
        
        with st.form("clarification_form"):
            current_inputs = st.session_state.final_inputs
            missing_fields_list = st.session_state.missing_fields
            cols = st.columns(min(len(missing_fields_list), 3))
            
            for i, field in enumerate(missing_fields_list):
                with cols[i % len(cols)]:
                    new_value = CLARIFICATION_WIDGETS[field](current_inputs.get(field))
                    current_inputs[field] = new_value

            if st.form_submit_button("✅ Confirm & Continue", use_container_width=True, type="primary"):
                st.session_state.final_inputs = current_inputs
                st.session_state.clarification_needed = False
                st.session_state.run_generation_manual = True
                if 'results' in st.session_state: del st.session_state.results
                st.rerun()

    # 4. MANUAL GENERATION LOGIC
    if st.session_state.get('run_generation_manual', False):
        st.markdown("---")
        progress_bar = st.progress(0.0, text="Initializing optimization...")
        run_generation_logic(
            inputs=st.session_state.final_inputs, emissions_df=emissions_df, costs_df=costs_df,
            purpose_profiles_data=purpose_profiles_data, st_progress=progress_bar
        )
        st.session_state.run_generation_manual = False

    # 5. DISPLAY RESULTS
    if 'results' in st.session_state and st.session_state.results["success"]:
        results = st.session_state.results
        opt_df, opt_meta, base_df, base_meta = results["opt_df"], results["opt_meta"], results["base_df"], results["base_meta"]
        trace, inputs = results["trace"], results["inputs"]
        
        # Tab Controller (Using radio button for robust layout control)
        TAB_NAMES = ["📊 **Overview**", "🌱 **Optimized Mix**", "🏗️ **Baseline Mix**", "⚖️ **Trade-off Explorer**", "📋 **QA/QC & Gradation**", "📥 **Downloads & Reports**", "🔬 **Lab Calibration**"]
        if st.session_state.active_tab_name not in TAB_NAMES: st.session_state.active_tab_name = TAB_NAMES[0]
        try: default_index = TAB_NAMES.index(st.session_state.active_tab_name)
        except ValueError: default_index = 0
        selected_tab = st.radio("Mix Report Navigation", options=TAB_NAMES, index=default_index, horizontal=True, label_visibility="collapsed", key="manual_tabs")
        st.session_state.active_tab_name = selected_tab

        if selected_tab == "📊 **Overview**":
            co2_opt, cost_opt, co2_base, cost_base = opt_meta["co2_total"], opt_meta["cost_total"], base_meta["co2_total"], base_meta["cost_total"]
            reduction = (co2_base - co2_opt) / co2_base * 100 if co2_base > 0 else 0.0
            cost_savings = cost_base - cost_opt

            st.subheader("Performance At a Glance")
            c1, c2, c3 = st.columns(3)
            c1.metric("🌱 CO₂ Reduction", f"{reduction:.1f}%", f"{co2_base - co2_opt:.1f} kg/m³ saved")
            c2.metric("💰 Cost Savings", f"₹{cost_savings:,.0f} / m³", f"{cost_savings/cost_base*100 if cost_base>0 else 0:.1f}% cheaper")
            c3.metric("♻️ SCM Content", f"{opt_meta['scm_total_frac']*100:.0f}%", f"{base_meta['scm_total_frac']*100:.0f}% in baseline")
            
            if opt_meta.get("purpose", "General") != "General":
                c_p1, c_p2, c_p3 = st.columns(3)
                c_p1.metric("🛠️ Design Purpose", opt_meta['purpose'])
                if "composite_score" in opt_meta and not pd.isna(opt_meta["composite_score"]): c_p2.metric("🎯 Composite Score", f"{opt_meta.get('composite_score', 0.0):.3f}")
                c_p3.metric("⚠️ Purpose Penalty", f"{opt_meta.get('purpose_penalty', 0.0):.2f}")

            st.markdown("---")
            col1, col2 = st.columns(2)
            _plot_overview_chart(col1, "📊 Embodied Carbon (CO₂e)", "CO₂ (kg/m³)", co2_base, co2_opt, ['#D3D3D3', '#4CAF50'], '{:,.1f}')
            _plot_overview_chart(col2, "💵 Material Cost", "Cost (₹/m³)", cost_base, cost_opt, ['#D3D3D3', '#2196F3'], '₹{:,.0f}')

        elif selected_tab == "🌱 **Optimized Mix**":
            display_mix_details("🌱 Optimized Low-Carbon Mix Design", opt_df, opt_meta, inputs['exposure'])
            if st.toggle("📖 Show Step-by-Step IS Calculation", key="toggle_walkthrough_tab2"): display_calculation_walkthrough(opt_meta)

        elif selected_tab == "🏗️ **Baseline Mix**":
            display_mix_details("🏗️ Standard OPC Baseline Mix Design", base_df, base_meta, inputs['exposure'])

        elif selected_tab == "⚖️ **Trade-off Explorer**":
            st.header("Cost vs. Carbon Trade-off Analysis")
            if trace:
                trace_df = pd.DataFrame(trace); feasible_mixes = trace_df[trace_df['feasible']].copy()
                if not feasible_mixes.empty:
                    pareto_df = pareto_front(feasible_mixes, x_col="cost", y_col="co2")
                    if not pareto_df.empty:
                        alpha = st.slider("Prioritize Sustainability (CO₂) ↔ Cost", min_value=0.0, max_value=1.0, value=st.session_state.get("pareto_slider_alpha", 0.5), step=0.05, key="pareto_slider_alpha")
                        
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
                        ax.plot(pareto_df_sorted["cost"], pareto_df_sorted["co2"], '-o', color='blue', label='Pareto Front', linewidth=2, zorder=2)
                        ax.plot(opt_meta['cost_total'], opt_meta['co2_total'], '*', markersize=15, color='red', label=f"Chosen Mix ({inputs.get('optimize_for', 'CO₂ Emissions')})", zorder=3)
                        ax.plot(best_compromise_mix['cost'], best_compromise_mix['co2'], 'D', markersize=10, color='green', label='Best Compromise (from slider)', zorder=3)
                        ax.set_xlabel("Material Cost (₹/m³)"); ax.set_ylabel("Embodied Carbon (kg CO₂e / m³)"); ax.legend(); st.pyplot(fig)
                        
                        st.markdown("---"); st.subheader("Details of Selected 'Best Compromise' Mix")
                        c1, c2, c3 = st.columns(3); c1.metric("💰 Cost", f"₹{best_compromise_mix['cost']:.0f} / m³"); c2.metric("🌱 CO₂", f"{best_compromise_mix['co2']:.1f} kg / m³"); c3.metric("💧 Water/Binder Ratio", f"{best_compromise_mix['wb']:.3f}")

        elif selected_tab == "📋 **QA/QC & Gradation**":
            st.header("Quality Assurance & Sieve Analysis")
            def sieve_check(df, check_func, input_val):
                if df is not None:
                    try: ok, msgs = check_func(df, input_val)
                    except Exception as e: return st.error(f"Error processing CSV: {e}"), None
                    if ok: st.success(msgs[0], icon="✅")
                    else: [st.error(m, icon="❌") for m in msgs]
                    st.dataframe(df, use_container_width=True)
                    return ok
                st.info("Upload a CSV in the sidebar to perform a gradation check against IS 383.", icon="ℹ️")
                return None

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fine Aggregate Gradation")
                df_fine = pd.read_csv(fine_csv_to_use) if fine_csv_to_use else None
                sieve_check(df_fine, CONSTANTS.sieve_check_fa, inputs.get("fine_zone", "Zone II"))
            with col2:
                st.subheader("Coarse Aggregate Gradation")
                df_coarse = pd.read_csv(coarse_csv_to_use) if coarse_csv_to_use else None
                sieve_check(df_coarse, CONSTANTS.sieve_check_ca, inputs["nom_max"])
            
            with st.expander("🔬 View Optimizer Trace (Advanced)"):
                if trace:
                    trace_df = pd.DataFrame(trace)
                    st.dataframe(trace_df.style.apply(lambda s: ['background-color: #e8f5e9; color: #155724; text-align: center;' if v else 'background-color: #ffebee; color: #721c24; text-align: center;' for v in s], subset=['feasible']).format({"feasible": lambda v: "✅" if v else "❌", "wb": "{:.3f}", "co2": "{:.1f}", "cost": "{:,.0f}"}), use_container_width=True)
                else: st.info("Trace not available.")


        elif selected_tab == "📥 **Downloads & Reports**":
            st.header("Download Reports")
            # Excel Generation
            excel_buffer = BytesIO();
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                opt_df.to_excel(writer, sheet_name="Optimized_Mix", index=False)
                base_df.to_excel(writer, sheet_name="Baseline_Mix", index=False)
                pd.DataFrame([opt_meta]).T.to_excel(writer, sheet_name="Optimized_Meta")
                pd.DataFrame([base_meta]).T.to_excel(writer, sheet_name="Baseline_Meta")
                if trace: pd.DataFrame(trace).to_excel(writer, sheet_name="Optimizer_Trace", index=False)
            excel_buffer.seek(0)

            # PDF Generation
            pdf_buffer = BytesIO()
            doc = SimpleDocTemplate(pdf_buffer, pagesize=(8.5*inch, 11*inch))
            styles = getSampleStyleSheet(); story = [Paragraph("CivilGPT Sustainable Mix Report", styles['h1']), Spacer(1, 0.2*inch)]
            summary_data = [["Metric", "Optimized Mix", "Baseline Mix"], ["CO₂ (kg/m³)", f"{opt_meta['co2_total']:.1f}", f"{base_meta['co2_total']:.1f}"], ["Cost (₹/m³)", f"₹{opt_meta['cost_total']:,.2f}", f"₹{base_meta['cost_total']:,.2f}"], ["w/b Ratio", f"{opt_meta['w_b']:.3f}", f"{base_meta['w_b']:.3f}"], ["Binder (kg/m³)", f"{opt_meta['cementitious']:.1f}", f"{base_meta['cementitious']:.1f}"]]
            summary_table = Table(summary_data, hAlign='LEFT', colWidths=[2*inch, 1.5*inch, 1.5*inch])
            summary_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            story.extend([Paragraph(f"Design for <b>{inputs['grade']} / {inputs['exposure']} Exposure</b>", styles['h2']), summary_table, Spacer(1, 0.2*inch)])
            opt_data_pdf = [opt_df.columns.values.tolist()] + opt_df.applymap(lambda x: f'{x:.2f}' if isinstance(x, float) else x).values.tolist()
            opt_table = Table(opt_data_pdf, hAlign='LEFT')
            opt_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.palegreen)]))
            story.extend([Paragraph("Optimized Mix Proportions (kg/m³)", styles['h2']), opt_table])
            doc.build(story); pdf_buffer.seek(0)

            d1, d2 = st.columns(2)
            with d1: st.download_button("📄 Download PDF Report", data=pdf_buffer.getvalue(), file_name="CivilGPT_Report.pdf", mime="application/pdf", use_container_width=True)
            with d1: st.download_button("📈 Download Excel Report", data=excel_buffer.getvalue(), file_name="CivilGPT_Mix_Designs.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            with d2: st.download_button("✔️ Optimized Mix (CSV)", data=opt_df.to_csv(index=False).encode("utf-8"), file_name="optimized_mix.csv", mime="text/csv", use_container_width=True)
            with d2: st.download_button("✖️ Baseline Mix (CSV)", data=base_df.to_csv(index=False).encode("utf-8"), file_name="baseline_mix.csv", mime="text/csv", use_container_width=True)

        elif selected_tab == "🔬 **Lab Calibration**":
            st.header("🔬 Lab Calibration Analysis")
            if lab_csv_to_use is not None:
                try:
                    lab_results_df = pd.read_csv(lab_csv_to_use)
                    comparison_df, error_metrics = run_lab_calibration(lab_results_df)
                    if comparison_df is not None and not comparison_df.empty:
                        st.subheader("Error Metrics")
                        m1, m2, m3 = st.columns(3)
                        m1.metric("Mean Absolute Error (MAE)", f"{error_metrics['Mean Absolute Error (MPa)']:.2f} MPa")
                        m2.metric("Root Mean Squared Error (RMSE)", f"{error_metrics['Root Mean Squared Error (MPa)']:.2f} MPa")
                        m3.metric("Mean Bias (Over/Under-prediction)", f"{error_metrics['Mean Bias (MPa)']:.2f} MPa")
                        st.subheader("Comparison: Lab vs. Predicted Target Strength")
                        st.dataframe(comparison_df.style.format({"Lab Strength (MPa)": "{:.2f}", "Predicted Target Strength (MPa)": "{:.2f}", "Error (MPa)": "{:+.2f}"}), use_container_width=True)
                        fig, ax = plt.subplots(); ax.scatter(comparison_df["Lab Strength (MPa)"], comparison_df["Predicted Target Strength (MPa)"], alpha=0.7); lims = [np.min([ax.get_xlim(), ax.get_ylim()]), np.max([ax.get_xlim(), ax.get_ylim()])]; ax.plot(lims, lims, 'r--', alpha=0.75, zorder=0); ax.set_xlabel("Actual Lab Strength (MPa)"); ax.set_ylabel("Predicted Target Strength (MPa)"); st.pyplot(fig)
                    else: st.warning("Could not process the uploaded lab data CSV. Please check the file format.", icon="⚠️")
                except Exception as e: st.error(f"Failed to read or process the lab data CSV file: {e}", icon="💥")
            else: st.info("Upload a lab data CSV in the sidebar to automatically compare CivilGPT's target strength calculations against your real-world results.", icon="ℹ️")
        
    elif not st.session_state.get('clarification_needed'):
        st.info("Enter your concrete requirements in the prompt box above, or switch to manual mode to specify parameters.", icon="👆")
        st.markdown("---"); st.subheader("How It Works")
        st.markdown("""1. **Input Requirements**: Describe your project needs. 2. **IS Code Compliance**: The app generates candidate mixes, ensuring adherence to IS 10262 and IS 456. 3. **Sustainability Optimization**: It calculates embodied carbon (CO₂e), cost, and 'Purpose-Fit'. 4. **Best Mix Selection**: Presents the mix with the best **composite score** (or lowest CO₂/cost) against a standard OPC baseline.""")

# ==============================================================================
# PART 7: MAIN APP CONTROLLER
# ==============================================================================

def main():
    st.set_page_config(page_title="CivilGPT - Sustainable Concrete Mix Designer", page_icon="🧱", layout="wide")
    st.markdown("""<style>.main .block-container { padding-top: 2rem; padding-bottom: 2rem; padding-left: 5rem; padding-right: 5rem; } [data-testid="stSidebar"] { min-width: 300px; max-width: 400px; } </style>""", unsafe_allow_html=True) # Reduced CSS bloat

    # 1. STATE INITIALIZATION (Minimized)
    if "chat_mode" not in st.session_state: st.session_state.chat_mode = False
    if "active_tab_name" not in st.session_state: st.session_state.active_tab_name = "📊 **Overview**"
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    if "chat_inputs" not in st.session_state: st.session_state.chat_inputs = {}
    if "chat_results_displayed" not in st.session_state: st.session_state.chat_results_displayed = False
    if "run_chat_generation" not in st.session_state: st.session_state.run_chat_generation = False
    
    purpose_profiles_data = CONSTANTS.PURPOSE_PROFILES # Direct access to constant as it's not a function call now

    # 2. SIDEBAR SETUP (COMMON ELEMENTS)
    st.sidebar.title("Mode Selection")
    if "llm_init_message" in st.session_state:
        msg_type, msg_content = st.session_state.pop("llm_init_message")
        getattr(st.sidebar, msg_type)(msg_content, icon="🤖" if msg_type == "success" else None)

    llm_is_ready = st.session_state.get("llm_enabled", False)
    chat_mode = st.sidebar.toggle("💬 Switch to CivilGPT Chat Mode", value=st.session_state.chat_mode if llm_is_ready else False, key="chat_mode_toggle", disabled=not llm_is_ready)
    st.session_state.chat_mode = chat_mode

    if chat_mode and st.sidebar.button("🧹 Clear Chat History", use_container_width=True):
        st.session_state.chat_history, st.session_state.chat_inputs = [], {}; st.session_state.chat_results_displayed = False
        if "results" in st.session_state: del st.session_state.results; st.rerun()
    st.sidebar.markdown("---")

    # Material Libraries (Shared)
    st.sidebar.header("📁 Material Libraries (Shared)")
    with st.sidebar.expander("Upload Materials, Cost, & Emissions CSVs"):
        materials_file = st.file_uploader("Upload Materials Library CSV", type=["csv"], key="materials_csv")
        emissions_file = st.file_uploader("Emission Factors (kgCO₂/kg)", type=["csv"], key="emissions_csv")
        cost_file = st.file_uploader("Cost Factors (₹/kg)", type=["csv"], key="cost_csv")

    materials_df, emissions_df, costs_df = load_data(materials_file, emissions_file, cost_file)

    # 3. CHAT-TRIGGERED GENERATION (Logic execution)
    if st.session_state.get('run_chat_generation', False):
        st.session_state.run_chat_generation = False
        chat_inputs = st.session_state.chat_inputs
        default_material_props = {'sg_fa': 2.65, 'moisture_fa': 1.0, 'sg_ca': 2.70, 'moisture_ca': 0.5}
        
        inputs = {
            "grade": "M30", "exposure": "Severe", "cement_choice": "OPC 43", "nom_max": 20, "agg_shape": "Angular (baseline)", "target_slump": 125,
            "use_sp": True, "optimize_cost": False, "qc_level": "Good", "fine_zone": "Zone II", "material_props": default_material_props,
            "purpose": "General", "enable_purpose_optimization": False, "purpose_weights": purpose_profiles_data['General']['weights'],
            "optimize_for": "CO₂ Emissions", "calibration_kwargs": {}, **chat_inputs
        }
        
        inputs["optimize_cost"] = (inputs.get("optimize_for") == "Cost")
        inputs["enable_purpose_optimization"] = (inputs.get("purpose", 'General') != 'General')
        if inputs["enable_purpose_optimization"]:
            inputs["purpose_weights"] = purpose_profiles_data.get(inputs["purpose"], {}).get('weights', purpose_profiles_data['General']['weights'])

        st.session_state.final_inputs = inputs
        with st.spinner("⚙️ Running IS-code calculations and optimizing..."):
            run_generation_logic(inputs=inputs, emissions_df=emissions_df, costs_df=costs_df, purpose_profiles_data=purpose_profiles_data, st_progress=None)

    # 4. RENDER UI
    if chat_mode: run_chat_interface(purpose_profiles_data)
    else: run_manual_interface(purpose_profiles_data, materials_df, emissions_df, costs_df)


if __name__ == "__main__":
    main()
