# app.py - CivilGPT v2.7 (Emission & Cost Fix)
# v2.7: Fixed material matching for emissions and cost factors. Non-zero values now appear for all components.

import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
from io import BytesIO, StringIO
import json
import traceback
import re
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
import logging # --- FIX: Added for test harness ---
from difflib import get_close_matches # <--- FIX: Added import

# ==============================================================================
# PART 1: BACKEND LOGIC (CORRECTED & ENHANCED)
# ==============================================================================

# Groq client (optional)
try:
    from groq import Groq
    client = Groq(api_key=st.secrets.get("GROQ_API_KEY", None))
except Exception:
    client = None

# --- FIX: Column normalization maps ---
# Define canonical column names and their common variants (keys are normalized)
EMISSIONS_COL_MAP = {
    "material": "Material",
    "co2_factor_kg_co2_per_kg": "CO2_Factor(kg_CO2_per_kg)",
    "co2_factor": "CO2_Factor(kg_CO2_per_kg)",
    "co2factor": "CO2_Factor(kg_CO2_per_kg)",
    "emission_factor": "CO2_Factor(kg_CO2_per_kg)",
    "co2factor_kgco2perkg": "CO2_Factor(kg_CO2_per_kg)",
    "co2": "CO2_Factor(kg_CO2_per_kg)" # --- FIX: Added variant ---
}
# --- v2.7 FIX: Added 'kg' (from '₹/kg') and 'rs_kg' (from 'rs/kg') variants ---
COSTS_COL_MAP = {
    "material": "Material",
    "cost_kg": "Cost(₹/kg)",        # From "Cost (₹/kg)"
    "cost_rs_kg": "Cost(₹/kg)",     # From "Cost (rs/kg)"
    "cost": "Cost(₹/kg)",           # From "Cost"
    "cost_per_kg": "Cost(₹/kg)",    # From "cost_per_kg"
    "costperkg": "Cost(₹/kg)",      # From "costperkg"
    "price": "Cost(₹/kg)",          # From "Price"
    "kg": "Cost(₹/kg)",             # FIX: From "₹/kg"
    "rs_kg": "Cost(₹/kg)",      # FIX: From "rs/kg"
    # --- FIX: Added requested variants ---
    "costper": "Cost(₹/kg)",
    "price_kg": "Cost(₹/kg)",
    "priceperkg": "Cost(₹/kg)",
}
MATERIALS_COL_MAP = {
    "material": "Material",
    "specificgravity": "SpecificGravity",
    "specific_gravity": "SpecificGravity",
    "moisturecontent": "MoistureContent",
    "moisture_content": "MoistureContent",
    "waterabsorption": "WaterAbsorption",
    "water_absorption": "WaterAbsorption"
}

# --- FIX: Helper for robust header normalization (slugify) ---
def _normalize_header(header):
    """Converts a messy header to a clean, underscore-based slug."""
    s = str(header).strip().lower()
    # Replace common separators with underscore
    s = re.sub(r'[ \-/\.\(\)]+', '_', s)
    # Remove any remaining non-alphanumeric characters (like ₹)
    s = re.sub(r'[^a-z0-9_]+', '', s)
    # Clean up multiple or trailing underscores
    s = re.sub(r'_+', '_', s)
    return s.strip('_')


# --- FIX: Add new function for robust material VALUE normalization ---
def _normalize_material_value(s: str) -> str:
    """Normalize material name value to canonical slug for matching."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    # Replace punctuation, mm numbers, and multiple spaces
    s = re.sub(r'\b(\d+mm)\b', r'\1', s)  # keep but normalize spacing
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    # Remove common size tokens (we'll handle '20mm' separately)
    s = s.replace('mm', '').strip()
    
    # canonical synonyms mapping (extend as needed)
    synonyms = {
        "m sand": "fine aggregate",
        "msand": "fine aggregate",
        "m-sand": "fine aggregate",
        "m sand": "fine aggregate",
        "fine aggregate": "fine aggregate",
        "sand": "fine aggregate",
        "20 coarse aggregate": "coarse aggregate",
        "20mm coarse aggregate": "coarse aggregate",
        "20 coarse": "coarse aggregate",
        "20": "coarse aggregate",
        "coarse aggregate": "coarse aggregate",
        "20mm": "coarse aggregate",
        "pce superplasticizer": "pce superplasticizer",
        "pce superplasticiser": "pce superplasticizer",
        "pce": "pce superplasticizer",
        "opc 43": "opc 43",
        "opc 53": "opc 53",
        "fly ash": "fly ash",
        "ggbs": "ggbs",
        "water": "water",
    }
    key = s
    # direct synonym
    if key in synonyms:
        return synonyms[key]
    
    # fuzzy match against synonyms keys
    cand = get_close_matches(key, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand:
        return synonyms[cand[0]]
    
    # fallback: collapse numeric prefixes and try again
    key2 = re.sub(r'^\d+\s*', '', key)
    cand = get_close_matches(key2, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand:
        return synonyms[cand[0]]
        
    # final fallback: return normalized spaces version
    return key


# --- FIX: Helper for robust column normalization ---
def _normalize_columns(df, column_map):
    """
    Normalizes DataFrame columns based on a map of {normalized_variant: canonical_name}.
    """
    # --- FIX: Get canonical columns, ensuring unique order ---
    canonical_cols = list(dict.fromkeys(column_map.values()))
    if df is None or df.empty:
        # Return an empty DF with the canonical columns
        return pd.DataFrame(columns=canonical_cols)

    df = df.copy()
    
    # Create a map of {normalized_col_name: original_col_name}
    # This allows us to find the *first* column in the CSV that matches a variant
    norm_cols = {}
    for col in df.columns:
        norm_col = _normalize_header(col)
        if norm_col not in norm_cols: # Keep first occurrence
            norm_cols[norm_col] = col
    
    rename_dict = {}
    for variant, canonical in column_map.items():
        # The variant key in the map is *already* normalized
        if variant in norm_cols:
            # Map the original column name to the canonical name
            original_col_name = norm_cols[variant]
            
            # --- FIX: Only map if canonical name hasn't been found yet ---
            if canonical not in rename_dict.values():
                rename_dict[original_col_name] = canonical

    df = df.rename(columns=rename_dict)
    
    # Keep only the canonical columns that were found in the file
    found_canonical = [col for col in canonical_cols if col in df.columns]
    return df[found_canonical]


# Dataset Path Handling
LAB_FILE = "lab_processed_mgrades_only.xlsx"
MIX_FILE = "concrete_mix_design_data_cleaned_standardized.xlsx"

def safe_load_excel(name):
    # name is e.g., "lab_processed_mgrades_only.xlsx"
    # Try paths relative to the script's location
    paths_to_try = [
        os.path.join(SCRIPT_DIR, name),
        os.path.join(SCRIPT_DIR, "data", name)
    ]
    for p in paths_to_try:
        if os.path.exists(p):
            try:
                return pd.read_excel(p)
            except Exception:
                try:
                    return pd.read_excel(p, engine="openpyxl")
                except Exception:
                    st.warning(f"Failed to read Excel file at {p}")
                    return None
    # st.warning(f"Could not find Excel file: {name}") # Optional: can be noisy
    return None

lab_df = safe_load_excel(LAB_FILE)
mix_df = safe_load_excel(MIX_FILE)


# --- IS Code Rules & Tables (IS 456 & IS 10262) ---
EXPOSURE_WB_LIMITS = {"Mild": 0.60,"Moderate": 0.55,"Severe": 0.50,"Very Severe": 0.45,"Marine": 0.40}
EXPOSURE_MIN_CEMENT = {"Mild": 300, "Moderate": 300, "Severe": 320,"Very Severe": 340, "Marine": 360}
EXPOSURE_MIN_GRADE = {"Mild": "M20", "Moderate": "M25", "Severe": "M30","Very Severe": "M35", "Marine": "M40"}
GRADE_STRENGTH = {"M10": 10, "M15": 15, "M20": 20, "M25": 25,"M30": 30, "M35": 35, "M40": 40, "M45": 45, "M50": 50}
WATER_BASELINE = {10: 208, 12.5: 202, 20: 186, 40: 165} # IS 10262, Table 4 (for 50mm slump)
AGG_SHAPE_WATER_ADJ = {"Angular (baseline)": 0.00, "Sub-angular": -0.03,"Sub-rounded": -0.05, "Rounded": -0.07,"Flaky/Elongated": +0.03}
QC_STDDEV = {"Good": 5.0, "Fair": 7.5, "Poor": 10.0} # IS 10262, Table 2

# --- FIX: Add entrapped air volume estimation as per IS 10262, Table 4, Note 2 ---
ENTRAPPED_AIR_VOL = {10: 0.02, 12.5: 0.015, 20: 0.01, 40: 0.008} # m³ per m³ of concrete

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
    20: {"40.0": (95,100),   "20.0": (95,100),     "10.0": (25,55), "4.75": (0,10)},
    40: {"80.0": (95,100),   "40.0": (95,100),     "20.0": (30,70), "10.0": (0,15)}
}

# Parsers (Original, Unchanged)
def simple_parse(text: str) -> dict:
    result = {}
    grade_match = re.search(r"\bM\s*(10|15|20|25|30|35|40|45|50)\b", text, re.IGNORECASE)
    if grade_match: result["grade"] = "M" + grade_match.group(1)
    for exp in EXPOSURE_WB_LIMITS.keys():
        if re.search(exp, text, re.IGNORECASE): result["exposure"] = exp; break
    slump_match = re.search(r"slump\s*(?:of\s*)?(\d{2,3})\s*mm", text, re.IGNORECASE)
    if slump_match: result["slump"] = int(slump_match.group(1))
    cement_types = ["OPC 43"]
    for ctype in cement_types:
        if re.search(ctype.replace(" ", r"\s*"), text, re.IGNORECASE):
            result["cement"] = ctype; break
    nom_match = re.search(r"(\d{2}(\.5)?)\s*mm", text, re.IGNORECASE)
    if nom_match:
        try: result["nom_max"] = float(nom_match.group(1))
        except: pass
    return result

def parse_input_with_llm(user_text: str) -> dict:
    if client is None:
        return simple_parse(user_text)
    prompt = f"Extract grade, exposure, slump (mm), cement type, and nominal max aggregate from: {user_text}. Return JSON."
    resp = client.chat.completions.create(
        model="mixtral-8x7b-32768",
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )
    try:
        parsed = json.loads(resp.choices[0].message.content)
    except Exception:
        parsed = simple_parse(user_text)
    return parsed

# Helpers
@st.cache_data
def _read_csv_try(path): return pd.read_csv(path)

# --- FIX: Rewritten load_data function for robust loading and column normalization ---
@st.cache_data
def load_data(materials_file=None, emissions_file=None, cost_file=None):
    """
    Loads materials, emissions, and cost data from uploaded files or default paths.
    Searches root and /data, normalizes columns, and handles errors.
    """
    def _safe_read(file, default):
        """Reads an uploaded file or returns default."""
        if file is not None:
            try:
                # Ensure file pointer is at the beginning
                if hasattr(file, 'seek'):
                    file.seek(0)
                return pd.read_csv(file)
            except Exception as e:
                st.warning(f"Could not read uploaded file {file.name}: {e}")
                return default
        return default

    def _load_fallback(default_names):
        """Tries to read a CSV from a list of default paths (root and data/)."""
        # default_names is ["cost_factors.csv", "data/cost_factors.csv"]
        # We build absolute paths based on the script's location.
        paths_to_try = [
            os.path.join(SCRIPT_DIR, default_names[0]), # Path to root file
            os.path.join(SCRIPT_DIR, default_names[1])  # Path to data/ file
        ]
        
        for p in paths_to_try:
            if os.path.exists(p):
                try:
                    return pd.read_csv(p)
                except Exception as e:
                    st.warning(f"Could not read {p}: {e}")
        return None # Return None if all paths fail

    # 1. Load data from uploaded files or fallbacks
    # --- FIX: Use fallback logic for all files ---
    materials = _safe_read(materials_file, _load_fallback(["materials_library.csv", "data/materials_library.csv"]))
    emissions = _safe_read(emissions_file, _load_fallback(["emission_factors.csv", "data/emission_factors.csv"]))
    costs = _safe_read(cost_file, _load_fallback(["cost_factors.csv", "data/cost_factors.csv"]))

    # 2. Normalize columns and handle missing files
    materials = _normalize_columns(materials, MATERIALS_COL_MAP)
    # --- FIX: Force Material to string *after* normalization ---
    if "Material" in materials.columns:
        materials["Material"] = materials["Material"].astype(str).str.strip()
        
    # --- FIX: Check for 'Material' column as required ---
    if materials.empty or "Material" not in materials.columns:
        st.warning("Could not load 'materials_library.csv' or 'Material' column not found. Using empty library.", icon="ℹ️")
        # --- FIX: Return a clean empty DF with canonical headers ---
        materials = pd.DataFrame(columns=list(dict.fromkeys(MATERIALS_COL_MAP.values())))

    emissions = _normalize_columns(emissions, EMISSIONS_COL_MAP)
    # --- FIX: Force Material to string *after* normalization ---
    if "Material" in emissions.columns:
        emissions["Material"] = emissions["Material"].astype(str).str.strip()
        
    # --- FIX: Check for 'Material' AND the value column ---
    if emissions.empty or "Material" not in emissions.columns or "CO2_Factor(kg_CO2_per_kg)" not in emissions.columns:
        st.warning("⚠️ Could not load 'emission_factors.csv' or required columns ('Material', 'CO2_Factor') not found. CO2 calculations will be zero.")
        emissions = pd.DataFrame(columns=list(dict.fromkeys(EMISSIONS_COL_MAP.values())))
        
    costs = _normalize_columns(costs, COSTS_COL_MAP)
    # --- FIX: Force Material to string *after* normalization ---
    if "Material" in costs.columns:
        costs["Material"] = costs["Material"].astype(str).str.strip()
        
    # --- FIX: Check for 'Material' AND the value column ---
    if costs.empty or "Material" not in costs.columns or "Cost(₹/kg)" not in costs.columns:
        st.warning("⚠️ Could not load 'cost_factors.csv' or required columns ('Material', 'Cost') not found. Cost calculations will be zero.")
        costs = pd.DataFrame(columns=list(dict.fromkeys(COSTS_COL_MAP.values())))

    return materials, emissions, costs

# NEW: Helper function for Pareto Front calculation (Original, Unchanged)
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
    if not pareto_points:
        return pd.DataFrame(columns=df.columns)
    return pd.DataFrame(pareto_points).reset_index(drop=True)


def water_for_slump_and_shape(nom_max_mm: int, slump_mm: int,
                            agg_shape: str, uses_sp: bool=False,
                            sp_reduction_frac: float=0.0) -> float:
    base = WATER_BASELINE.get(int(nom_max_mm), 186.0)
    if slump_mm <= 50: water = base
    else: water = base * (1 + 0.03 * ((slump_mm - 50) / 25.0))
    water *= (1.0 + AGG_SHAPE_WATER_ADJ.get(agg_shape, 0.0))
    if uses_sp and sp_reduction_frac > 0: water *= (1 - sp_reduction_frac)
    return float(water)

def reasonable_binder_range(grade: str):
    return BINDER_RANGES.get(grade, (300, 500))

def get_coarse_agg_fraction(nom_max_mm: float, fa_zone: str, wb_ratio: float):
    base_fraction = COARSE_AGG_FRAC_BY_ZONE.get(nom_max_mm, {}).get(fa_zone, 0.62)
    wb_diff = 0.50 - wb_ratio
    correction = (wb_diff / 0.05) * 0.01
    corrected_fraction = base_fraction + correction
    return max(0.4, min(0.8, corrected_fraction))

def run_lab_calibration(lab_df):
    results = []
    default_qc_level = "Good"
    std_dev_S = QC_STDDEV[default_qc_level]
    for _, row in lab_df.iterrows():
        try:
            grade = str(row['grade']).strip()
            actual_strength = float(row['actual_strength'])
            if grade not in GRADE_STRENGTH:
                continue
            fck = GRADE_STRENGTH[grade]
            predicted_strength = fck + 1.65 * std_dev_S
            results.append({
                "Grade": grade,
                "Exposure": row.get('exposure', 'N/A'),
                "Slump (mm)": row.get('slump', 'N/A'),
                "Lab Strength (MPa)": actual_strength,
                "Predicted Target Strength (MPa)": predicted_strength,
                "Error (MPa)": predicted_strength - actual_strength
            })
        except (KeyError, ValueError, TypeError):
            pass
    if not results:
        return None, {}
    results_df = pd.DataFrame(results)
    mae = results_df["Error (MPa)"].abs().mean()
    rmse = np.sqrt((results_df["Error (MPa)"] ** 2).mean())
    bias = results_df["Error (MPa)"].mean()
    metrics = {"Mean Absolute Error (MPa)": mae, "Root Mean Squared Error (MPa)": rmse, "Mean Bias (MPa)": bias}
    return results_df, metrics

# ==============================================================================
# PART 2: CORE MIX LOGIC (UPDATED)
# ==============================================================================

# --- FIX: REPLACED entire evaluate_mix function with robust normalization logic ---
def evaluate_mix(components_dict, emissions_df, costs_df=None):
    """Calculates CO2 and Cost for a given mix, with robust merging and warnings."""
    
    # --- FIX: Create comp_df with original names AND normalized names ---
    comp_items = [(m.strip(), q) for m, q in components_dict.items() if q > 0.01]
    comp_df = pd.DataFrame(comp_items, columns=["Material", "Quantity (kg/m3)"])
    comp_df["Material_norm"] = comp_df["Material"].apply(_normalize_material_value)
    
    # --- CO2 Calculation ---
    if emissions_df is not None and not emissions_df.empty and "CO2_Factor(kg_CO2_per_kg)" in emissions_df.columns:
        emissions_df_norm = emissions_df.copy()
        # --- FIX: Use new normalizer on emissions file ---
        emissions_df_norm['Material'] = emissions_df_norm['Material'].astype(str)
        emissions_df_norm["Material_norm"] = emissions_df_norm["Material"].apply(_normalize_material_value)
        # drop duplicates keeping first
        emissions_df_norm = emissions_df_norm.drop_duplicates(subset=["Material_norm"])
        
        # Merge on the normalized slug
        df = comp_df.merge(emissions_df_norm[["Material_norm","CO2_Factor(kg_CO2_per_kg)"]],
                            on="Material_norm", how="left")
        
        # --- FIX: Get missing list from ORIGINAL material name, filter empties ---
        missing_rows = df[df["CO2_Factor(kg_CO2_per_kg)"].isna()]
        missing_emissions = [m for m in missing_rows["Material"].tolist() if m and str(m).strip()]
        
        if missing_emissions:
            if 'warned_emissions' not in st.session_state:
                st.session_state.warned_emissions = set()
            # Use the *original* name (e.g., "Fine Aggregate") for the warning set
            new_missing = set(missing_emissions) - st.session_state.warned_emissions
            if new_missing:
                # Show human-readable names in warning
                st.warning(f"No emission factors found for: {', '.join(list(new_missing))}. CO2 will be 0 for these materials.", icon="⚠️")
                st.session_state.warned_emissions.update(new_missing)
        
        df["CO2_Factor(kg_CO2_per_kg)"] = df["CO2_Factor(kg_CO2_per_kg)"].fillna(0.0)
    else:
        df = comp_df.copy()
        df["CO2_Factor(kg_CO2_per_kg)"] = 0.0
        
    df["CO2_Emissions (kg/m3)"] = df["Quantity (kg/m3)"] * df["CO2_Factor(kg_CO2_per_kg)"]

    # --- Cost Calculation ---
    if costs_df is not None and not costs_df.empty and "Cost(₹/kg)" in costs_df.columns:
        costs_df_norm = costs_df.copy()
        # --- FIX: Use new normalizer on costs file ---
        costs_df_norm['Material'] = costs_df_norm['Material'].astype(str)
        costs_df_norm["Material_norm"] = costs_df_norm["Material"].apply(_normalize_material_value)
        # drop duplicates keeping first
        costs_df_norm = costs_df_norm.drop_duplicates(subset=["Material_norm"])
        
        # Merge on the normalized slug
        df = df.merge(costs_df_norm[["Material_norm", "Cost(₹/kg)"]], on="Material_norm", how="left")
        
        # --- FIX: Get missing list from ORIGINAL material name, filter empties ---
        missing_rows_cost = df[df["Cost(₹/kg)"].isna()]
        missing_costs = [m for m in missing_rows_cost["Material"].tolist() if m and str(m).strip()]
        
        if missing_costs:
            if 'warned_costs' not in st.session_state:
                st.session_state.warned_costs = set()
            # Use the *original* name (e.g., "Fine Aggregate") for the warning set
            new_missing = set(missing_costs) - st.session_state.warned_costs
            if new_missing:
                # Show human-readable names in warning
                st.warning(f"No cost factors found for: {', '.join(list(new_missing))}. Cost will be 0 for these materials.", icon="⚠️")
                st.session_state.warned_costs.update(new_missing)
                
        df["Cost(₹/kg)"] = df["Cost(₹/kg)"].fillna(0.0)
    else:
        df["Cost(₹/kg)"] = 0.0
        
    df["Cost (₹/m3)"] = df["Quantity (kg/m3)"] * df["Cost(₹/kg)"]
    
    # --- Final Formatting ---
    # Use the original "Material" column from comp_df, which is human-readable.
    df["Material"] = df["Material"].str.title()
    
    # Ensure all required columns exist, even if empty
    # --- SYNTAX FIX: Removed <br> tag ---
    for col in ["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]:
        if col not in df.columns:
            df[col] = 0.0 if "kg" in col or "m3" in col else ""
            
    return df[["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]]


# --- FIX: Unchanged aggregate_correction, logic is correct ---
def aggregate_correction(delta_moisture_pct: float, agg_mass_ssd: float):
    water_delta = (delta_moisture_pct / 100.0) * agg_mass_ssd
    corrected_mass = agg_mass_ssd * (1 + delta_moisture_pct / 100.0)
    return float(water_delta), float(corrected_mass)

# --- FIX: Rewritten compute_aggregates to include entrapped air ---
def compute_aggregates(cementitious, water, sp, coarse_agg_fraction,
                        nom_max_mm, # <-- FIX: Added nom_max_mm
                        density_fa=2650.0, density_ca=2700.0):
    """
    Computes aggregate volumes and masses based on absolute volume method,
    including entrapped air as per IS 10262.
    """
    vol_cem = cementitious / 3150.0 # Density of cement
    vol_wat = water / 1000.0       # Density of water
    vol_sp  = sp / 1200.0          # Assumed density of SP
    
    # --- FIX: Get entrapped air based on nominal max aggregate size ---
    vol_air = ENTRAPPED_AIR_VOL.get(int(nom_max_mm), 0.01) # Default to 1% (for 20mm)
    
    # This is the volume of everything *except* aggregates
    vol_paste_and_air = vol_cem + vol_wat + vol_sp + vol_air # <-- FIX: Added air
    
    vol_agg = 1.0 - vol_paste_and_air # <-- FIX: Corrected total aggregate volume
    
    if vol_agg <= 0: 
        # This can happen with very high water/binder contents.
        # Don't use st.warning here, it's too noisy inside the optimizer loop.
        # This mix will fail compliance checks later.
        vol_agg = 0.60 # Fallback as requested
    
    vol_coarse = vol_agg * coarse_agg_fraction
    vol_fine = vol_agg * (1.0 - coarse_agg_fraction)

    mass_fine_ssd = vol_fine * density_fa
    mass_coarse_ssd = vol_coarse * density_ca
    
    return float(mass_fine_ssd), float(mass_coarse_ssd)

def compliance_checks(mix_df, meta, exposure):
    checks = {}
    try: checks["W/B ≤ exposure limit"] = float(meta["w_b"]) <= EXPOSURE_WB_LIMITS[exposure]
    except: checks["W/B ≤ exposure limit"] = False
    try: checks["Min cementitious met"] = float(meta["cementitious"]) >= float(EXPOSURE_MIN_CEMENT[exposure])
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
    return checks, derived

def sanity_check_mix(meta, df):
    warnings = []
    try:
        cement, water, fine, coarse, sp = float(meta.get("cement", 0)), float(meta.get("water_target", 0)), float(meta.get("fine", 0)), float(meta.get("coarse", 0)), float(meta.get("sp", 0))
        unit_wt = float(df["Quantity (kg/m3)"].sum())
    # --- SYNTAX FIX: Removed <br> tag ---
    except Exception: return ["Insufficient data to run sanity checks."]
    
    # (Original "Low cement content" logic preserved)
    if cement > 500: warnings.append(f"High cement content ({cement:.1f} kg/m³). Increases cost, shrinkage, and CO₂.")
    if water < 140 or water > 220: warnings.append(f"Water content ({water:.1f} kg/m³) is outside the typical range of 140-220 kg/m³.")
    if fine < 500 or fine > 900: warnings.append(f"Fine aggregate quantity ({fine:.1f} kg/m³) is unusual.")
    if coarse < 1000 or coarse > 1300: warnings.append(f"Coarse aggregate quantity ({coarse:.1f} kg/m³) is unusual.")
    if sp > 20: warnings.append(f"Superplasticizer dosage ({sp:.1f} kg/m³) is unusually high.")
    return warnings

def check_feasibility(mix_df, meta, exposure):
    checks, derived = compliance_checks(mix_df, meta, exposure)
    warnings = sanity_check_mix(meta, mix_df) # Original bug fix preserved
    reasons_fail = [f"IS Code Fail: {k}" for k, v in checks.items() if not v]
    feasible = len(reasons_fail) == 0
    return feasible, reasons_fail, warnings, derived, checks

def get_compliance_reasons(mix_df, meta, exposure):
    reasons = []
    try:
        limit = EXPOSURE_WB_LIMITS[exposure]
        used = float(meta["w_b"])
        if used > limit:
            reasons.append(f"Failed W/B ratio limit ({used:.3f} > {limit:.2f})")
    except: reasons.append("Failed W/B ratio check (parsing error)")
    try:
        limit = float(EXPOSURE_MIN_CEMENT[exposure])
        used = float(meta["cementitious"])
        if used < limit:
            reasons.append(f"Cementitious below minimum ({used:.1f} kg/m³ < {limit:.1f} kg/m³)")
    except: reasons.append("Failed min. cementitious check (parsing error)")
    try:
        limit = 0.50
        used = float(meta.get("scm_total_frac", 0.0))
        if used > limit:
            reasons.append(f"SCM fraction exceeds limit ({used*100:.0f}% > {limit*100:.0f}%)")
    except: reasons.append("Failed SCM fraction check (parsing error)")
    try:
        min_limit, max_limit = 2200.0, 2600.0
        total_mass = float(mix_df["Quantity (kg/m3)"].sum())
        if not (min_limit <= total_mass <= max_limit):
            reasons.append(f"Unit weight outside range ({total_mass:.1f} kg/m³ not in {min_limit:.0f}-{max_limit:.0f} kg/m³)")
    except: reasons.append("Failed unit weight check (parsing error)")
    feasible = len(reasons) == 0
    if feasible:
        return feasible, "All IS-code checks passed."
    else:
        return feasible, "; ".join(reasons)

def sieve_check_fa(df: pd.DataFrame, zone: str):
    try:
        limits, ok, msgs = FINE_AGG_ZONE_LIMITS[zone], True, []
        for sieve, (lo, hi) in limits.items():
            row = df.loc[df["Sieve_mm"].astype(str) == sieve]
            if row.empty:
                ok = False; msgs.append(f"Missing sieve size: {sieve} mm."); continue
            p = float(row["PercentPassing"].iloc[0])
            if not (lo <= p <= hi): ok = False; msgs.append(f"Sieve {sieve} mm: {p:.1f}% passing is outside the required range of {lo}-{hi}%.")
        # --- SYNTAX FIX: Removed <br> tag ---
        if ok: msgs = [f"Fine aggregate conforms to IS 383 for {zone}."]
        return ok, msgs
    # --- SYNTAX FIX: Removed <br> tag ---
    except: return False, ["Invalid fine aggregate CSV format. Ensure 'Sieve_mm' and 'PercentPassing' columns exist."]

def sieve_check_ca(df: pd.DataFrame, nominal_mm: int):
    try:
        limits, ok, msgs = COARSE_LIMITS[int(nominal_mm)], True, []
        for sieve, (lo, hi) in limits.items():
            row = df.loc[df["Sieve_mm"].astype(str) == sieve]
            if row.empty:
                ok = False; msgs.append(f"Missing sieve size: {sieve} mm."); continue
            p = float(row["PercentPassing"].iloc[0])
            if not (lo <= p <= hi): ok = False; msgs.append(f"Sieve {sieve} mm: {p:.1f}% passing is outside the required range of {lo}-{hi}%.")
        # --- SYNTAX FIX: Removed <br> tag ---
        if ok: msgs = [f"Coarse aggregate conforms to IS 383 for {nominal_mm} mm graded aggregate."]
        return ok, msgs
    # --- SYNTAX FIX: Removed <br> tag ---
    except: return False, ["Invalid coarse aggregate CSV format. Ensure 'Sieve_mm' and 'PercentPassing' columns exist."]


def generate_mix(grade, exposure, nom_max, target_slump, agg_shape, fine_zone, emissions, costs, cement_choice, material_props, use_sp=True, sp_reduction=0.18, optimize_cost=False, wb_min=0.35, wb_steps=6, max_flyash_frac=0.3, max_ggbs_frac=0.5, scm_step=0.1, fine_fraction_override=None):
    w_b_limit, min_cem_exp = float(EXPOSURE_WB_LIMITS[exposure]), float(EXPOSURE_MIN_CEMENT[exposure])
    target_water = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    best_df, best_meta, best_score = None, None, float("inf")
    trace = []

    wb_values = np.linspace(float(wb_min), float(w_b_limit), int(wb_steps))
    flyash_options = np.arange(0.0, max_flyash_frac + 1e-9, scm_step)
    ggbs_options = np.arange(0.0, max_ggbs_frac + 1e-9, scm_step)
    min_b_grade, max_b_grade = reasonable_binder_range(grade)

    # --- v2.7: Clear warnings at the start of a new generation ---
    if 'warned_emissions' in st.session_state:
        st.session_state.warned_emissions.clear()
    if 'warned_costs' in st.session_state:
        st.session_state.warned_costs.clear()

    for wb in wb_values:
        for flyash_frac in flyash_options:
            for ggbs_frac in ggbs_options:
                if flyash_frac + ggbs_frac > 0.50: continue

                binder_for_strength = target_water / wb
                binder = max(binder_for_strength, min_cem_exp, min_b_grade)
                binder = min(binder, max_b_grade)
                actual_wb = target_water / binder

                cement, flyash, ggbs = binder * (1 - flyash_frac - ggbs_frac), binder * flyash_frac, binder * ggbs_frac
                sp = 0.01 * binder if use_sp else 0.0

                density_fa = material_props['sg_fa'] * 1000
                density_ca = material_props['sg_ca'] * 1000

                if fine_fraction_override is not None:
                    coarse_agg_frac = 1.0 - fine_fraction_override
                else:
                    coarse_agg_frac = get_coarse_agg_fraction(nom_max, fine_zone, actual_wb)

                # --- FIX: Pass nom_max to compute_aggregates for air volume calculation ---
                fine_ssd, coarse_ssd = compute_aggregates(binder, target_water, sp, coarse_agg_frac, nom_max, density_fa, density_ca)

                water_delta_fa, fine_wet = aggregate_correction(material_props['moisture_fa'], fine_ssd)
                water_delta_ca, coarse_wet = aggregate_correction(material_props['moisture_ca'], coarse_ssd)

                water_to_remove = water_delta_fa + water_delta_ca
                water_final = target_water - water_to_remove
                # --- FIX: Clip water to a minimum positive value to avoid errors ---
                if water_final < 5.0:
                    water_final = 5.0 # This mix will be non-compliant, but avoids calculation errors

                mix = {cement_choice: cement,"Fly Ash": flyash,"GGBS": ggbs,"Water": water_final,"PCE Superplasticizer": sp,"Fine Aggregate": fine_wet,"Coarse Aggregate": coarse_wet}
                
                # --- FIX: Ensure emissions and costs DFs are passed ---
                df = evaluate_mix(mix, emissions, costs)
                
                # --- FIX: Ensure co2_total and cost_total are floats ---
                co2_total = float(df["CO2_Emissions (kg/m3)"].sum())
                cost_total = float(df["Cost (₹/m3)"].sum())

                candidate_meta = {
                    "w_b": actual_wb, "cementitious": binder, "cement": cement, 
                    "flyash": flyash, "ggbs": ggbs, "water_target": target_water, 
                    "water_final": water_final, "sp": sp, "fine": fine_wet, 
                    "coarse": coarse_wet, "scm_total_frac": flyash_frac + ggbs_frac, 
                    "grade": grade, "exposure": exposure, "nom_max": nom_max, 
                    "slump": target_slump, 
                    "co2_total": co2_total, # <-- FIX: Ensured this is populated
                    "cost_total": cost_total, # <-- FIX: Ensured this is populated
                    "coarse_agg_fraction": coarse_agg_frac, 
                    "binder_range": (min_b_grade, max_b_grade), 
                    "material_props": material_props
                }
                
                feasible, _, _, _, _ = check_feasibility(df, candidate_meta, exposure)
                trace_feasible, trace_reasons = get_compliance_reasons(df, candidate_meta, exposure)
                
                score = co2_total if not optimize_cost else cost_total
                
                trace.append({
                    "wb": float(actual_wb), 
                    "flyash_frac": float(flyash_frac), 
                    "ggbs_frac": float(ggbs_frac),
                    "co2": float(co2_total), # <-- FIX: Ensured this is populated
                    "cost": float(cost_total), # <-- FIX: Ensured this is populated
                    "score": float(score), 
                    "feasible": bool(trace_feasible),
                    "reasons": str(trace_reasons)
                })
                
                if feasible and score < best_score:
                    best_df, best_score, best_meta = df.copy(), score, candidate_meta.copy()
                    
    return best_df, best_meta, trace

def generate_baseline(grade, exposure, nom_max, target_slump, agg_shape, fine_zone, emissions, costs, cement_choice, material_props, use_sp=True, sp_reduction=0.18):
    w_b_limit, min_cem_exp = float(EXPOSURE_WB_LIMITS[exposure]), float(EXPOSURE_MIN_CEMENT[exposure])
    water_target = water_for_slump_and_shape(nom_max_mm=nom_max, slump_mm=int(target_slump), agg_shape=agg_shape, uses_sp=use_sp, sp_reduction_frac=sp_reduction)
    min_b_grade, max_b_grade = reasonable_binder_range(grade)

    binder_for_wb = water_target / w_b_limit
    cementitious = max(binder_for_wb, min_cem_exp, min_b_grade)
    cementitious = min(cementitious, max_b_grade)
    actual_wb = water_target / cementitious
    sp = 0.01 * cementitious if use_sp else 0.0
    coarse_agg_frac = get_coarse_agg_fraction(nom_max, fine_zone, actual_wb)

    density_fa = material_props['sg_fa'] * 1000
    density_ca = material_props['sg_ca'] * 1000
    
    # --- FIX: Pass nom_max to compute_aggregates for air volume calculation ---
    fine_ssd, coarse_ssd = compute_aggregates(cementitious, water_target, sp, coarse_agg_frac, nom_max, density_fa, density_ca)

    water_delta_fa, fine_wet = aggregate_correction(material_props['moisture_fa'], fine_ssd)
    water_delta_ca, coarse_wet = aggregate_correction(material_props['moisture_ca'], coarse_ssd)
    
    water_to_remove = water_delta_fa + water_delta_ca
    water_final = water_target - water_to_remove
    # --- FIX: Clip water to a minimum positive value to avoid errors ---
    if water_final < 5.0:
        water_final = 5.0

    mix = {cement_choice: cementitious,"Fly Ash": 0.0,"GGBS": 0.0,"Water": water_final, "PCE Superplasticizer": sp,"Fine Aggregate": fine_wet,"Coarse Aggregate": coarse_wet}
    
    # --- FIX: Ensure emissions and costs DFs are passed ---
    df = evaluate_mix(mix, emissions, costs)
    
    # --- FIX: Ensure co2_total and cost_total are floats ---
    co2_total = float(df["CO2_Emissions (kg/m3)"].sum())
    cost_total = float(df["Cost (₹/m3)"].sum())
    
    meta = {
        "w_b": actual_wb, "cementitious": cementitious, "cement": cementitious, 
        "flyash": 0.0, "ggbs": 0.0, "water_target": water_target, 
        "water_final": water_final, "sp": sp, "fine": fine_wet, 
        "coarse": coarse_wet, "scm_total_frac": 0.0, "grade": grade, 
        "exposure": exposure, "nom_max": nom_max, "slump": target_slump, 
        "co2_total": co2_total, # <-- FIX: Ensured this is populated
        "cost_total": cost_total, # <-- FIX: Ensured this is populated
        "coarse_agg_fraction": coarse_agg_frac, 
        "material_props": material_props
    }
    return df, meta

def apply_parser(user_text, current_inputs):
    if not user_text.strip():
        return current_inputs, [], {}
    try:
        parsed = parse_input_with_llm(user_text) if use_llm_parser else simple_parse(user_text)
    except Exception as e:
        st.warning(f"Parser error: {e}, falling back to regex")
        parsed = simple_parse(user_text)
    messages, updated = [], current_inputs.copy()
    if "grade" in parsed and parsed["grade"] in GRADE_STRENGTH:
        updated["grade"] = parsed["grade"]; messages.append(f"✅ Parser set Grade to **{parsed['grade']}**")
    if "exposure" in parsed and parsed["exposure"] in EXPOSURE_WB_LIMITS:
        updated["exposure"] = parsed["exposure"]; messages.append(f"✅ Parser set Exposure to **{parsed['exposure']}**")
    if "slump" in parsed:
        s = max(25, min(180, int(parsed["slump"])))
        updated["target_slump"] = s; messages.append(f"✅ Parser set Target Slump to **{s} mm**")
    if "cement" in parsed:
        updated["cement_choice"] = parsed["cement"]; messages.append(f"✅ Parser set Cement Type to **{parsed['cement']}**")
    if "nom_max" in parsed and parsed["nom_max"] in [10, 12.5, 20, 40]:
        updated["nom_max"] = parsed["nom_max"]; messages.append(f"✅ Parser set Aggregate Size to **{parsed['nom_max']} mm**")
    return updated, messages, parsed

# ==============================================================================
# PART 3: REFACTORED USER INTERFACE (Original, Unchanged)
# --- FIX: Wrapped all UI/Streamlit code in a main() function ---
# ==============================================================================

def main():
    # --- App Config (Moved inside main) ---
    st.set_page_config(
        page_title="CivilGPT - Sustainable Concrete Mix Designer",
        page_icon="🧱",
        layout="wide"
    )

    # --- Page Styling ---
    st.markdown("""
    <style>
        /* Center the title and main interface elements */
        .main .block-container {
            padding-top: 2rem;
            padding-bottom: 2rem;
            padding-left: 5rem;
            padding-right: 5rem;
        }
        .st-emotion-cache-1y4p8pa {
            max-width: 100%;
        }
        /* Style the main text area like a prompt box */
        .stTextArea [data-baseweb=base-input] {
            border-color: #4A90E2;
            box-shadow: 0 0 5px #4A90E2;
        }
    </style>
    """, unsafe_allow_html=True)


    # --- Landing Page / Main Interface ---
    st.title("🧱 CivilGPT: Sustainable Concrete Mix Designer")
    st.markdown("##### An AI-powered tool for creating **IS 10262:2019 compliant** concrete mixes, optimized for low carbon footprint.")

    # Main input area
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

    manual_mode = st.toggle("⚙️ Switch to Advanced Manual Input")

    # --- Sidebar for Manual Inputs ---
    if 'user_text_input' not in st.session_state:
        st.session_state.user_text_input = ""

    if manual_mode:
        st.sidebar.header("📝 Manual Mix Inputs")
        st.sidebar.markdown("---")

        st.sidebar.subheader("Core Requirements")
        grade = st.sidebar.selectbox("Concrete Grade", list(GRADE_STRENGTH.keys()), index=4, help="Target characteristic compressive strength at 28 days.")
        exposure = st.sidebar.selectbox("Exposure Condition", list(EXPOSURE_WB_LIMITS.keys()), index=2, help="Determines durability requirements like min. cement content and max. water-binder ratio as per IS 456.")

        st.sidebar.subheader("Workability & Materials")
        target_slump = st.sidebar.slider("Target Slump (mm)", 25, 180, 100, 5, help="Specifies the desired consistency and workability of the fresh concrete.")
        cement_choice = st.sidebar.selectbox("Cement Type", ["OPC 43"], index=0, help="Type of Ordinary Portland Cement.")
        nom_max = st.sidebar.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=2, help="Largest practical aggregate size, influences water demand.")
        agg_shape = st.sidebar.selectbox("Coarse Aggregate Shape", list(AGG_SHAPE_WATER_ADJ.keys()), index=0, help="Shape affects water demand; angular requires more water than rounded.")
        fine_zone = st.sidebar.selectbox("Fine Aggregate Zone (IS 383)", ["Zone I","Zone II","Zone III","Zone IV"], index=1, help="Grading zone as per IS 383. This is crucial for determining aggregate proportions per IS 10262.")

        st.sidebar.subheader("Optimization & Admixtures")
        use_sp = st.sidebar.checkbox("Use Superplasticizer (PCE)", True, help="Chemical admixture to increase workability or reduce water content.")
        optimize_for = st.sidebar.radio("Optimize For", ["Lowest CO₂", "Lowest Cost"], help="The optimizer will prioritize finding a feasible mix that minimizes either carbon emissions or material cost.")
        optimize_cost = (optimize_for == "Lowest Cost")

        st.sidebar.subheader("Advanced Parameters")
        with st.sidebar.expander("QA/QC"):
            qc_level = st.selectbox("Quality Control Level", list(QC_STDDEV.keys()), index=0, help="Assumed site quality control, affecting the target strength calculation (f_target = fck + 1.65 * S).")

        with st.sidebar.expander("Material Properties (from Library or Manual)"):
            materials_file = st.file_uploader("Upload Materials Library CSV", type=["csv"], key="materials_csv", help="CSV with 'Material', 'SpecificGravity', 'MoistureContent', 'WaterAbsorption' columns.")
            sg_fa_default, moisture_fa_default = 2.65, 1.0
            sg_ca_default, moisture_ca_default = 2.70, 0.5

            if materials_file is not None:
                try:
                    materials_file.seek(0)
                    # --- FIX: Use normalization logic from load_data ---
                    temp_mat_df = pd.read_csv(materials_file)
                    mat_df = _normalize_columns(temp_mat_df, MATERIALS_COL_MAP)
                    mat_df['Material'] = mat_df['Material'].str.strip().lower()

                    fa_row = mat_df[mat_df['Material'] == 'fine aggregate']
                    if not fa_row.empty:
                        if 'SpecificGravity' in fa_row: sg_fa_default = float(fa_row['SpecificGravity'].iloc[0])
                        if 'MoistureContent' in fa_row: moisture_fa_default = float(fa_row['MoistureContent'].iloc[0])

                    ca_row = mat_df[mat_df['Material'] == 'coarse aggregate']
                    if not ca_row.empty:
                        if 'SpecificGravity' in ca_row: sg_ca_default = float(ca_row['SpecificGravity'].iloc[0])
                        if 'MoistureContent' in ca_row: moisture_ca_default = float(ca_row['MoistureContent'].iloc[0])

                    st.success("Materials library CSV loaded and properties updated.")
                except Exception as e:
                    st.error(f"Failed to parse materials CSV: {e}")

            st.markdown("###### Fine Aggregate")
            sg_fa = st.number_input("Specific Gravity (FA)", 2.0, 3.0, sg_fa_default, 0.01)
            moisture_fa = st.number_input("Free Moisture Content % (FA)", -2.0, 5.0, moisture_fa_default, 0.1, help="Moisture beyond SSD condition. Negative if absorbent.")

            st.markdown("###### Coarse Aggregate")
            sg_ca = st.number_input("Specific Gravity (CA)", 2.0, 3.0, sg_ca_default, 0.01)
            moisture_ca = st.number_input("Free Moisture Content % (CA)", -2.0, 5.0, moisture_ca_default, 0.1, help="Moisture beyond SSD condition. Negative if absorbent.")

        st.sidebar.subheader("File Uploads (Optional)")
        with st.sidebar.expander("Upload Sieve Analysis & Financials"):
            st.markdown("###### Sieve Analysis (IS 383)")
            fine_csv = st.file_uploader("Fine Aggregate CSV", type=["csv"], key="fine_csv", help="CSV with 'Sieve_mm' and 'PercentPassing' columns.")
            coarse_csv = st.file_uploader("Coarse Aggregate CSV", type=["csv"], key="coarse_csv", help="CSV with 'Sieve_mm' and 'PercentPassing' columns.")

            st.markdown("###### Cost & Emissions Data")
            emissions_file = st.file_uploader("Emission Factors (kgCO₂/kg)", type=["csv"], key="emissions_csv")
            cost_file = st.file_uploader("Cost Factors (₹/kg)", type=["csv"], key="cost_csv")

        with st.sidebar.expander("🔬 Lab Calibration Dataset"):
            st.markdown("""
            Upload a CSV with lab results to compare against CivilGPT's predictions.
            **Required columns:**
            - `grade` (e.g., M30)
            - `exposure` (e.g., Severe)
            - `slump` (mm)
            - `nom_max` (mm)
            - `cement_choice` (e.g., OPC 43)
            - `actual_strength` (MPa)
            """)
            lab_csv = st.file_uploader("Upload Lab Data CSV", type=["csv"], key="lab_csv")

        st.sidebar.markdown("---")
        use_llm_parser = st.sidebar.checkbox("Use Groq LLM Parser", value=False, help="Use a Large Language Model for parsing the text prompt. Requires API key.")

    else: # Default values when manual mode is off
        grade, exposure, cement_choice = "M30", "Severe", "OPC 43"
        nom_max, agg_shape, target_slump = 20, "Angular (baseline)", 125
        use_sp, optimize_cost, fine_zone = True, False, "Zone II"
        qc_level = "Good"
        sg_fa, moisture_fa = 2.65, 1.0
        sg_ca, moisture_ca = 2.70, 0.5
        fine_csv, coarse_csv, lab_csv = None, None, None
        emissions_file, cost_file, materials_file = None, None, None
        use_llm_parser = False

    with st.sidebar.expander("Calibration & Tuning (Developer)"):
        enable_calibration_overrides = st.checkbox("Enable calibration overrides", False, help="Override default optimizer search parameters with the values below.")
        calib_wb_min = st.number_input("W/B search minimum (wb_min)", 0.30, 0.45, 0.35, 0.01, help="Lower bound for the Water/Binder ratio search space.")
        calib_wb_steps = st.slider("W/B search steps (wb_steps)", 3, 15, 6, 1, help="Number of W/B ratios to test between min and the exposure limit.")
        calib_fine_fraction = st.slider("Fine Aggregate Fraction (fine_fraction)", 0.30, 0.50, 0.40, 0.01, help="Manually overrides the IS 10262 calculation for aggregate proportions.")
        calib_max_flyash_frac = st.slider("Max Fly Ash fraction", 0.0, 0.5, 0.30, 0.05, help="Maximum Fly Ash replacement percentage to test.")
        calib_max_ggbs_frac = st.slider("Max GGBS fraction", 0.0, 0.5, 0.50, 0.05, help="Maximum GGBS replacement percentage to test.")
        calib_scm_step = st.slider("SCM fraction step (scm_step)", 0.05, 0.25, 0.10, 0.05, help="Step size for testing different SCM replacement percentages.")


    # --- FIX: Call rewritten load_data. This is where cost/emission DFs are loaded. ---
    materials_df, emissions_df, costs_df = load_data(materials_file, emissions_file, cost_file)


    # --- Main Execution Block ---

    if 'clarification_needed' not in st.session_state:
        st.session_state.clarification_needed = False
    if 'run_generation' not in st.session_state:
        st.session_state.run_generation = False
    if 'final_inputs' not in st.session_state:
        st.session_state.final_inputs = {}

    CLARIFICATION_WIDGETS = {
        "grade": lambda v: st.selectbox("Concrete Grade", list(GRADE_STRENGTH.keys()), index=list(GRADE_STRENGTH.keys()).index(v) if v in GRADE_STRENGTH else 4),
        "exposure": lambda v: st.selectbox("Exposure Condition", list(EXPOSURE_WB_LIMITS.keys()), index=list(EXPOSURE_WB_LIMITS.keys()).index(v) if v in EXPOSURE_WB_LIMITS else 2),
        "target_slump": lambda v: st.slider("Target Slump (mm)", 25, 180, v if isinstance(v, int) else 100, 5),
        "cement_choice": lambda v: st.selectbox("Cement Type", ["OPC 43"], index=0),
        "nom_max": lambda v: st.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=[10, 12.5, 20, 40].index(v) if v in [10, 12.5, 20, 40] else 2),
    }

    if run_button:
        st.session_state.run_generation = True
        st.session_state.clarification_needed = False
        if 'results' in st.session_state:
            del st.session_state.results

        material_props = {'sg_fa': sg_fa, 'moisture_fa': moisture_fa, 'sg_ca': sg_ca, 'moisture_ca': moisture_ca}
        inputs = { "grade": grade, "exposure": exposure, "cement_choice": cement_choice, "nom_max": nom_max, "agg_shape": agg_shape, "target_slump": target_slump, "use_sp": use_sp, "optimize_cost": optimize_cost, "qc_level": qc_level, "fine_zone": fine_zone, "material_props": material_props }

        if user_text.strip() and not manual_mode:
            with st.spinner("🤖 Parsing your request..."):
                inputs, msgs, _ = apply_parser(user_text, inputs)

            if msgs:
                st.info(" ".join(msgs), icon="💡")

            required_fields = ["grade", "exposure", "target_slump", "nom_max", "cement_choice"]
            missing_fields = [f for f in required_fields if inputs.get(f) is None]

            if missing_fields:
                st.session_state.clarification_needed = True
                st.session_state.final_inputs = inputs
                st.session_state.missing_fields = missing_fields
                st.session_state.run_generation = False
            else:
                st.session_state.run_generation = True
                st.session_state.final_inputs = inputs
        else:
            st.session_state.run_generation = True
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
                st.session_state.run_generation = True
                if 'results' in st.session_state:
                    del st.session_state.results
                st.rerun()

    # ==============================================================================
    # COMPUTATION BLOCK (Original, Unchanged logic)
    # ==============================================================================
    if st.session_state.get('run_generation', False):
        st.markdown("---")
        try:
            inputs = st.session_state.final_inputs

            min_grade_req = EXPOSURE_MIN_GRADE[inputs["exposure"]]
            grade_order = list(GRADE_STRENGTH.keys())
            if grade_order.index(inputs["grade"]) < grade_order.index(min_grade_req):
                st.warning(f"For **{inputs['exposure']}** exposure, IS 456 recommends a minimum grade of **{min_grade_req}**. The grade has been automatically updated.", icon="⚠️")
                inputs["grade"] = min_grade_req
                st.session_state.final_inputs["grade"] = min_grade_req

            calibration_kwargs = {}
            if enable_calibration_overrides:
                calibration_kwargs = {
                    "wb_min": calib_wb_min,
                    "wb_steps": calib_wb_steps,
                    "max_flyash_frac": calib_max_flyash_frac,
                    "max_ggbs_frac": calib_max_ggbs_frac,
                    "scm_step": calib_scm_step,
                    "fine_fraction_override": calib_fine_fraction
                }
                st.info("Developer calibration overrides are enabled.", icon="🛠️")

            with st.spinner("⚙️ Running IS-code calculations and optimizing for sustainability..."):
                fck, S = GRADE_STRENGTH[inputs["grade"]], QC_STDDEV[inputs.get("qc_level", "Good")]
                fck_target = fck + 1.65 * S
                
                # --- FIX: Pass the correctly loaded emissions_df and costs_df ---
                opt_df, opt_meta, trace = generate_mix(
                    inputs["grade"], inputs["exposure"], inputs["nom_max"],
                    inputs["target_slump"], inputs["agg_shape"], inputs["fine_zone"],
                    emissions_df, costs_df, inputs["cement_choice"], # <-- Pass loaded DFs
                    material_props=inputs["material_props"],
                    use_sp=inputs["use_sp"], optimize_cost=inputs["optimize_cost"],
                    **calibration_kwargs
                )
                
                # --- FIX: Pass the correctly loaded emissions_df and costs_df ---
                base_df, base_meta = generate_baseline(
                    inputs["grade"], inputs["exposure"], inputs["nom_max"],
                    inputs["target_slump"], inputs["agg_shape"], inputs["fine_zone"],
                    emissions_df, costs_df, inputs["cement_choice"], # <-- Pass loaded DFs
                    material_props=inputs["material_props"],
                    use_sp=inputs["use_sp"]
                )

            if opt_df is None or base_df is None:
                st.error("Could not find a feasible mix design with the given constraints. Try adjusting the parameters, such as a higher grade or less restrictive exposure condition.", icon="❌")
                st.dataframe(pd.DataFrame(trace))
                st.session_state.results = {"success": False, "trace": trace}
            else:
                st.success(f"Successfully generated mix designs for **{inputs['grade']}** concrete in **{inputs['exposure']}** conditions.", icon="✅")
                for m in (opt_meta, base_meta):
                    m["fck"], m["fck_target"], m["stddev_S"] = fck, round(fck_target, 1), S
                
                st.session_state.results = {
                    "success": True,
                    "opt_df": opt_df,
                    "opt_meta": opt_meta,
                    "base_df": base_df,
                    "base_meta": base_meta,
                    "trace": trace,
                    "inputs": inputs,
                    "fck_target": fck_target,
                    "fck": fck,
                    "S": S
                }

        except Exception as e:
            st.error(f"An unexpected error occurred: {e}", icon="💥")
            st.code(traceback.format_exc())
            st.session_state.results = {"success": False, "trace": None}
        finally:
            st.session_state.run_generation = False

    # ==============================================================================
    # DISPLAY BLOCK (Original, Unchanged)
    # ==============================================================================
    if 'results' in st.session_state and st.session_state.results["success"]:
        
        results = st.session_state.results
        opt_df = results["opt_df"]
        opt_meta = results["opt_meta"]
        base_df = results["base_df"]
        base_meta = results["base_meta"]
        trace = results["trace"]
        inputs = results["inputs"]
        
        tab1, tab2, tab3, tab_pareto, tab4, tab5, tab6 = st.tabs([
            "📊 **Overview**",
            "🌱 **Optimized Mix**",
            "🏗️ **Baseline Mix**",
            "⚖️ **Trade-off Explorer (Pareto Front)**",
            "📋 **QA/QC & Gradation**",
            "📥 **Downloads & Reports**",
            "🔬 **Lab Calibration**"
        ])

        with tab1:
            co2_opt, cost_opt = opt_meta["co2_total"], opt_meta["cost_total"]
            co2_base, cost_base = base_meta["co2_total"], base_meta["cost_total"]
            reduction = (co2_base - co2_opt) / co2_base * 100 if co2_base > 0 else 0.0
            cost_savings = cost_base - cost_opt

            st.subheader("Performance At a Glance")
            c1, c2, c3 = st.columns(3)
            c1.metric("🌱 CO₂ Reduction", f"{reduction:.1f}%", f"{co2_base - co2_opt:.1f} kg/m³ saved")
            c2.metric("💰 Cost Savings", f"₹{cost_savings:,.0f} / m³", f"{cost_savings/cost_base*100 if cost_base>0 else 0:.1f}% cheaper")
            c3.metric("♻️ SCM Content", f"{opt_meta['scm_total_frac']*100:.0f}%", f"{base_meta['scm_total_frac']*100:.0f}% in baseline", help="Supplementary Cementitious Materials (Fly Ash, GGBS) replace high-carbon cement.")
            st.markdown("---")

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("📊 Embodied Carbon (CO₂e)")
                chart_data = pd.DataFrame({'Mix Type': ['Baseline OPC', 'CivilGPT Optimized'], 'CO₂ (kg/m³)': [co2_base, co2_opt]})
                fig, ax = plt.subplots(figsize=(6, 4))
                bars = ax.bar(chart_data['Mix Type'], chart_data['CO₂ (kg/m³)'], color=['#D3D3D3', '#4CAF50'])
                ax.set_ylabel("Embodied Carbon (kg CO₂e / m³)")
                ax.bar_label(bars, fmt='{:,.1f}')
                st.pyplot(fig)
            with col2:
                st.subheader("💵 Material Cost")
                chart_data_cost = pd.DataFrame({'Mix Type': ['Baseline OPC', 'CivilGPT Optimized'], 'Cost (₹/m³)': [cost_base, cost_opt]})
                fig2, ax2 = plt.subplots(figsize=(6, 4))
                bars2 = ax2.bar(chart_data_cost['Mix Type'], chart_data_cost['Cost (₹/m³)'], color=['#D3D3D3', '#2196F3'])
                ax2.set_ylabel("Material Cost (₹ / m³)")
                ax2.bar_label(bars2, fmt='₹{:,.0f}')
                st.pyplot(fig2)

        def display_mix_details(title, df, meta, exposure):
            st.header(title)
            c1, c2, c3, c4 = st.columns(4)
            c1.metric("💧 Water/Binder Ratio", f"{meta['w_b']:.3f}")
            c2.metric("📦 Total Binder (kg/m³)", f"{meta['cementitious']:.1f}")
            c3.metric("🎯 Target Strength (MPa)", f"{meta['fck_target']:.1f}")
            c4.metric("⚖️ Unit Weight (kg/m³)", f"{df['Quantity (kg/m3)'].sum():.1f}")

            st.subheader("Mix Proportions (per m³)")
            st.info(
                "CO₂ factors represent cradle-to-gate emissions: the amount of CO₂ released per kg of material during its manufacture. These values do not reduce the material mass in the mix — they are an environmental footprint, not a physical subtraction.",
                icon="ℹ️"
            )
            st.dataframe(df.style.format({
                "Quantity (kg/m3)": "{:.2f}",
                "CO2_Factor(kg_CO2_per_kg)": "{:.3f}",
                "CO2_Emissions (kg/m3)": "{:.2f}",
                "Cost(₹/kg)": "₹{:.2f}",
                "Cost (₹/m3)": "₹{:.2f}"
            }), use_container_width=True)

            st.subheader("Compliance & Sanity Checks (IS 10262 & IS 456)")
            is_feasible, fail_reasons, warnings, derived, checks_dict = check_feasibility(df, meta, exposure)

            if is_feasible:
                st.success("✅ This mix design is compliant with IS code requirements.", icon="👍")
            else:
                st.error(f"❌ This mix fails {len(fail_reasons)} IS code compliance check(s): " + ", ".join(fail_reasons), icon="🚨")

            if warnings:
                for warning in warnings:
                    st.warning(warning, icon="⚠️")

            with st.expander("Show detailed calculation parameters"):
                st.json(derived)

        def display_calculation_walkthrough(meta):
            st.header("Step-by-Step Calculation Walkthrough")
            st.markdown(f"""
            This is a summary of how the **Optimized Mix** was designed according to **IS 10262:2019**.

            #### 1. Target Mean Strength
            - **Characteristic Strength (fck):** `{meta['fck']}` MPa (from Grade {meta['grade']})
            - **Assumed Standard Deviation (S):** `{meta['stddev_S']}` MPa (for '{inputs['qc_level']}' quality control)
            - **Target Mean Strength (f'ck):** `fck + 1.65 * S = {meta['fck']} + 1.65 * {meta['stddev_S']} =` **`{meta['fck_target']:.2f}` MPa**

            #### 2. Water Content
            - **Basis:** IS 10262, Table 4, for `{meta['nom_max']}` mm nominal max aggregate size.
            - **Adjustments:** Slump (`{meta['slump']}` mm), aggregate shape ('{inputs['agg_shape']}'), and superplasticizer use.
            - **Final Target Water (SSD basis):** **`{meta['water_target']:.1f}` kg/m³**

            #### 3. Water-Binder (w/b) Ratio
            - **Constraint:** Maximum w/b ratio for `{meta['exposure']}` exposure is `{EXPOSURE_WB_LIMITS[meta['exposure']]}`.
            - **Optimizer Selection:** The optimizer selected the lowest w/b ratio that resulted in a feasible, low-carbon mix.
            - **Selected w/b Ratio:** **`{meta['w_b']:.3f}`**

            #### 4. Binder Content
            - **Initial Binder (from w/b):** `{meta['water_target']:.1f} / {meta['w_b']:.3f} = {(meta['water_target']/meta['w_b']):.1f}` kg/m³
            - **Constraints Check:**
                - Min. for `{meta['exposure']}` exposure: `{EXPOSURE_MIN_CEMENT[meta['exposure']]}` kg/m³
                - Typical range for `{meta['grade']}`: `{meta['binder_range'][0]}` - `{meta['binder_range'][1]}` kg/m³
            - **Final Adjusted Binder Content:** **`{meta['cementitious']:.1f}` kg/m³**

            #### 5. SCM & Cement Content
            - **Optimizer Goal:** Minimize CO₂/cost by replacing cement with SCMs (Fly Ash, GGBS).
            - **Selected SCM Fraction:** `{meta['scm_total_frac']*100:.0f}%`
            - **Material Quantities:**
                - **Cement:** `{meta['cement']:.1f}` kg/m³
                - **Fly Ash:** `{meta['flyash']:.1f}` kg/m³
                - **GGBS:** `{meta['ggbs']:.1f}` kg/m³

            #### 6. Aggregate Proportioning (IS 10262, Table 5)
            - **Basis:** Volume of coarse aggregate for `{meta['nom_max']}` mm aggregate and fine aggregate `{inputs['fine_zone']}`.
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


        with tab2:
            display_mix_details("🌱 Optimized Low-Carbon Mix Design", opt_df, opt_meta, inputs['exposure'])
            if st.toggle("📖 Show Step-by-Step IS Calculation", key="toggle_walkthrough_tab2"):
                display_calculation_walkthrough(opt_meta)

        with tab3:
            display_mix_details("🏗️ Standard OPC Baseline Mix Design", base_df, base_meta, inputs['exposure'])

        with tab_pareto:
            st.header("Cost vs. Carbon Trade-off Analysis")
            st.markdown("This chart displays all IS-code compliant mixes found by the optimizer. The blue line represents the **Pareto Front**—the set of most efficient mixes where you can't improve one objective (e.g., lower CO₂) without worsening the other (e.g., increasing cost).")

            if trace:
                trace_df = pd.DataFrame(trace)
                feasible_mixes = trace_df[trace_df['feasible']].copy()

                if not feasible_mixes.empty:
                    pareto_df = pareto_front(feasible_mixes, x_col="cost", y_col="co2")

                    if not pareto_df.empty:
                        alpha = st.slider(
                            "Prioritize Sustainability (CO₂) ↔ Cost",
                            min_value=0.0, max_value=1.0, value=st.session_state.get("pareto_slider_alpha", 0.5), step=0.05,
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
                        
                        optimize_for_label = "Lowest Cost" if inputs['optimize_cost'] else "Lowest CO₂"
                        ax.plot(opt_meta['cost_total'], opt_meta['co2_total'], '*', markersize=15, color='red', label=f'Chosen Mix ({optimize_for_label})', zorder=3)
                        
                        ax.plot(best_compromise_mix['cost'], best_compromise_mix['co2'], 'D', markersize=10, color='green', label='Best Compromise (from slider)', zorder=3)

                        ax.set_xlabel("Material Cost (₹/m³)")
                        ax.set_ylabel("Embodied Carbon (kg CO₂e / m³)")
                        ax.set_title("Pareto Front of Feasible Concrete Mixes")
                        ax.grid(True, linestyle='--', alpha=0.6)
                        ax.legend()
                        st.pyplot(fig)

                        st.markdown("---")
                        st.subheader("Details of Selected 'Best Compromise' Mix")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("💰 Cost", f"₹{best_compromise_mix['cost']:.0f} / m³")
                        c2.metric("🌱 CO₂", f"{best_compromise_mix['co2']:.1f} kg / m³")
                        c3.metric("💧 Water/Binder Ratio", f"{best_compromise_mix['wb']:.3f}")

                    else:
                        st.info("No Pareto front could be determined from the feasible mixes.", icon="ℹ️")
                else:
                    st.warning("No feasible mixes were found by the optimizer, so no trade-off plot can be generated.", icon="⚠️")
            else:
                st.error("Optimizer trace data is missing.", icon="❌")


        with tab4:
            st.header("Quality Assurance & Sieve Analysis")

            sample_fa_data = "Sieve_mm,PercentPassing\n4.75,95\n2.36,80\n1.18,60\n0.600,40\n0.300,15\n0.150,5"
            sample_ca_data = "Sieve_mm,PercentPassing\n40.0,100\n20.0,98\n10.0,40\n4.75,5"

            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fine Aggregate Gradation")
                if fine_csv is not None:
                    try:
                        fine_csv.seek(0)
                        df_fine = pd.read_csv(fine_csv)
                        ok_fa, msgs_fa = sieve_check_fa(df_fine, inputs.get("fine_zone", "Zone II"))
                        if ok_fa: st.success(msgs_fa[0], icon="✅")
                        else:
                            for m in msgs_fa: st.error(m, icon="❌")
                        st.dataframe(df_fine, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error processing Fine Aggregate CSV: {e}")
                else:
                    st.info("Upload a Fine Aggregate CSV in the sidebar to perform a gradation check against IS 383.", icon="ℹ️")
                    st.download_button(
                        label="Download Sample Fine Agg. CSV",
                        data=sample_fa_data,
                        file_name="sample_fine_aggregate.csv",
                        mime="text/csv",
                    )
            with col2:
                st.subheader("Coarse Aggregate Gradation")
                if coarse_csv is not None:
                    try:
                        coarse_csv.seek(0)
                        df_coarse = pd.read_csv(coarse_csv)
                        ok_ca, msgs_ca = sieve_check_ca(df_coarse, inputs["nom_max"])
                        if ok_ca: st.success(msgs_ca[0], icon="✅")
                        else:
                            for m in msgs_ca: st.error(m, icon="❌")
                        st.dataframe(df_coarse, use_container_width=True)
                    except Exception as e:
                        st.error(f"Error processing Coarse Aggregate CSV: {e}")
                else:
                    st.info("Upload a Coarse Aggregate CSV in the sidebar to perform a gradation check against IS 383.", icon="ℹ️")
                    st.download_button(
                        label="Download Sample Coarse Agg. CSV",
                        data=sample_ca_data,
                        file_name="sample_coarse_aggregate.csv",
                        mime="text/csv",
                    )

            st.markdown("---")
            with st.expander("📖 View Step-by-Step Calculation Walkthrough"):
                display_calculation_walkthrough(opt_meta)

            with st.expander("🔬 View Optimizer Trace (Advanced)"):
                if trace:
                    trace_df = pd.DataFrame(trace)
                    st.markdown("The table below shows every mix combination attempted by the optimizer. 'Feasible' mixes met all IS-code checks.")
                    
                    def style_feasible_cell(v):
                        if v:
                            return 'background-color: #e8f5e9; color: #155724; text-align: center;'
                        else:
                            return 'background-color: #ffebee; color: #721c24; text-align: center;'
                    
                    st.dataframe(
                        trace_df.style
                            .apply(lambda s: [style_feasible_cell(v) for v in s], subset=['feasible'])
                            .format({"feasible": lambda v: "✅" if v else "❌"}),
                        use_container_width=True
                    )
                    
                    st.markdown("#### CO₂ vs. Cost of All Candidate Mixes")
                    fig, ax = plt.subplots()
                    scatter_colors = ["#4CAF50" if f else "#F44336" for f in trace_df["feasible"]]
                    ax.scatter(trace_df["cost"], trace_df["co2"], c=scatter_colors, alpha=0.6)
                    ax.set_xlabel("Material Cost (₹/m³)")
                    ax.set_ylabel("Embodied Carbon (kg CO₂e/m³)")
                    ax.grid(True, linestyle='--', alpha=0.6)
                    st.pyplot(fig)
                else:
                    st.info("Trace not available.")

        with tab5:
            st.header("Download Reports")

            excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                opt_df.to_excel(writer, sheet_name="Optimized_Mix", index=False)
                base_df.to_excel(writer, sheet_name="Baseline_Mix", index=False)
                pd.DataFrame([opt_meta]).T.to_excel(writer, sheet_name="Optimized_Meta")
                pd.DataFrame([base_meta]).T.to_excel(writer, sheet_name="Baseline_Meta")
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
            ]
            summary_table = Table(summary_data, hAlign='LEFT', colWidths=[2*inch, 1.5*inch, 1.5*inch])
            summary_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            story.extend([Paragraph(f"Design for <b>{inputs['grade']} / {inputs['exposure']} Exposure</b>", styles['h2']), summary_table, Spacer(1, 0.2*inch)])

            opt_data_pdf = [opt_df.columns.values.tolist()] + opt_df.applymap(lambda x: f'{x:.2f}' if isinstance(x, float) else x).values.tolist()
            opt_table = Table(opt_data_pdf, hAlign='LEFT')
            opt_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.palegreen)]))
            story.extend([Paragraph("Optimized Mix Proportions (kg/m³)", styles['h2']), opt_table])
            doc.build(story)
            pdf_buffer.seek(0)

            d1, d2 = st.columns(2)
            with d1:
                st.download_button("📄 Download PDF Report", data=pdf_buffer.getvalue(), file_name="CivilGPT_Report.pdf", mime="application/pdf", use_container_width=True)
                st.download_button("📈 Download Excel Report", data=excel_buffer.getvalue(), file_name="CivilGPT_Mix_Designs.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            with d2:
                st.download_button("✔️ Optimized Mix (CSV)", data=opt_df.to_csv(index=False).encode("utf-8"), file_name="optimized_mix.csv", mime="text/csv", use_container_width=True)
                st.download_button("✖️ Baseline Mix (CSV)", data=base_df.to_csv(index=False).encode("utf-8"), file_name="baseline_mix.csv", mime="text/csv", use_container_width=True)

        with tab6:
            st.header("🔬 Lab Calibration Analysis")
            if lab_csv is not None:
                try:
                    lab_csv.seek(0)
                    lab_results_df = pd.read_csv(lab_csv)
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
                        lims = [
                            np.min([ax.get_xlim(), ax.get_ylim()]),
                            np.max([ax.get_xlim(), ax.get_ylim()]),
                        ]
                        ax.plot(lims, lims, 'r--', alpha=0.75, zorder=0, label="Perfect Prediction (y=x)")
                        ax.set_xlabel("Actual Lab Strength (MPa)")
                        ax.set_ylabel("Predicted Target Strength (MPa)")
                        ax.set_title("Lab Strength vs. Predicted Target Strength")
                        ax.legend()
                        ax.grid(True)
                        st.pyplot(fig)
                    else:
                        st.warning("Could not process the uploaded lab data CSV. Please check the file format, column names, and ensure it contains valid data.", icon="⚠️")
                except Exception as e:
                    st.error(f"Failed to read or process the lab data CSV file: {e}", icon="💥")
            else:
                # --- SYNTAX FIX: Removed <br> tags ---
                st.info(
                    "Upload a lab data CSV in the sidebar to automatically compare CivilGPT's "
                    "target strength calculations against your real-world results.",
                    icon="ℹ️"
                )
                
    elif 'results' in st.session_state and not st.session_state.results["success"]:
        pass

    elif not st.session_state.get('clarification_needed'):
        st.info("Enter your concrete requirements in the prompt box above, or switch to manual mode to specify parameters.", icon="👆")
        st.markdown("---")
        st.subheader("How It Works")
        st.markdown("""
        1.  **Input Requirements**: Describe your project needs in plain English (e.g., "M25 concrete for moderate exposure") or use the manual sidebar for detailed control.
        2.  **IS Code Compliance**: The app generates dozens of candidate mixes, ensuring each one adheres to the durability and strength requirements of Indian Standards **IS 10262** and **IS 456**.
        3.  **Sustainability Optimization**: It then calculates the embodied carbon (CO₂e) and cost for every compliant mix.
        4.  **Best Mix Selection**: Finally, it presents the mix with the lowest carbon footprint (or cost) alongside a standard OPC baseline for comparison.
        """)


# --- FIX: Call main() at the global scope so Streamlit runs the app ---
main() 

# --- FIX: Add __name__ == "__main__" guard and test harness ---
if __name__ == "__main__":
    
    # --- FIX: Optional local test harness ---
    # Check for test flag in env vars or secrets
    TEST_FLAG = os.environ.get("TEST_LOCAL_CALCS", "False").lower() == "true"
    if not TEST_FLAG:
        try:
            if st.secrets.get("TEST_LOCAL_CALCS", False):
                TEST_FLAG = True
        except Exception:
            pass # No secrets file, run as normal
    
    if TEST_FLAG:
        print("--- RUNNING LOCAL TEST HARNESS ---")
        
        # Setup logging to file
        report_path = "/tmp/civilgpt_test_report.txt"
        if os.path.exists(report_path):
                    os.remove(report_path) # Clear old report

        logging.basicConfig(
            filename=report_path,
            filemode='w',
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s'
        )
        logging.info("Starting CivilGPT Local Calculation Test")
        print(f"Logging test results to {report_path}...")

        try:
            # --- FIX: Load data from default CSVs to test normalization pipeline ---
            logging.info("Loading data from default CSVs (data/emission_factors.csv, data/cost_factors.csv)...")
            
            # Clear cache and set up mock session state for warning capture
            load_data.clear_cache()
            if 'warned_emissions' not in st.session_state: st.session_state.warned_emissions = set()
            if 'warned_costs' not in st.session_state: st.session_state.warned_costs = set()
            st.session_state.warned_emissions.clear()
            st.session_state.warned_costs.clear()

            # Call load_data with default (None) arguments
            test_materials_df, test_emissions_df, test_costs_df = load_data()

            if test_emissions_df.empty or "CO2_Factor(kg_CO2_per_kg)" not in test_emissions_df.columns:
                logging.error("FAIL: Failed to load 'emission_factors.csv' or its columns. Check file path and headers.")
                raise ValueError("Test emissions file failed to load.")
            else:
                logging.info("Loaded emission_factors.csv successfully.")
            
            if test_costs_df.empty or "Cost(₹/kg)" not in test_costs_df.columns:
                logging.error("FAIL: Failed to load 'cost_factors.csv' or its columns. Check file path and headers ('Cost', 'rs/kg', etc.).")
                raise ValueError("Test cost file failed to load.")
            else:
                logging.info("Loaded cost_factors.csv successfully.")
            
            logging.info("Test dataframes loaded and normalized.")
            # --- END of new loading block ---
            
            # 2. Define test inputs
            test_material_props = {'sg_fa': 2.65, 'moisture_fa': 1.0, 'sg_ca': 2.70, 'moisture_ca': 0.5}
            test_grade = "M30"
            test_exposure = "Severe"
            test_nom_max = 20
            test_target_slump = 100
            test_agg_shape = "Angular (baseline)"
            test_fine_zone = "Zone II"
            test_cement_choice = "OPC 43"

            logging.info(f"Test Parameters: {test_grade}, {test_exposure}, {test_nom_max}mm, {test_target_slump}mm slump")

            # 3. Call generate_baseline
            logging.info("Calling generate_baseline...")
            base_df, base_meta = generate_baseline(
                test_grade, test_exposure, test_nom_max, test_target_slump, 
                test_agg_shape, test_fine_zone, 
                test_emissions_df, test_costs_df, test_cement_choice, 
                test_material_props, use_sp=True
            )
            
            if base_df is None or base_meta is None:
                raise ValueError("generate_baseline returned None")
            
            logging.info(f"generate_baseline returned 'meta': {base_meta}")
            
            # 4. Validate baseline results
            co2_total_base = base_meta.get("co2_total", 0.0)
            cost_total_base = base_meta.get("cost_total", 0.0)
            
            # --- FIX: Add specific warning checks ---
            logging.info(f"Checking for spurious warnings. Emissions: {st.session_state.warned_emissions} | Costs: {st.session_state.warned_costs}")
            
            # Check for the *human-readable* names used in the `mix` dict
            if "Fine Aggregate" in st.session_state.warned_emissions or "fine aggregate" in st.session_state.warned_emissions:
                logging.error("FAIL: 'Fine Aggregate' was in warned_emissions.")
            else:
                logging.info("SUCCESS: 'Fine Aggregate' was NOT in warned_emissions.")

            if "Coarse Aggregate" in st.session_state.warned_emissions or "coarse aggregate" in st.session_state.warned_emissions:
                logging.error("FAIL: 'Coarse Aggregate' was in warned_emissions.")
            else:
                logging.info("SUCCESS: 'Coarse Aggregate' was NOT in warned_emissions.")
            
            if "Fine Aggregate" in st.session_state.warned_costs or "fine aggregate" in st.session_state.warned_costs:
                logging.error("FAIL: 'Fine Aggregate' was in warned_costs.")
            else:
                logging.info("SUCCESS: 'Fine Aggregate' was NOT in warned_costs.")
            
            if "Coarse Aggregate" in st.session_state.warned_costs or "coarse aggregate" in st.session_state.warned_costs:
                logging.error("FAIL: 'Coarse Aggregate' was in warned_costs.")
            else:
                logging.info("SUCCESS: 'Coarse Aggregate' was NOT in warned_costs.")
            # --- END of warning checks ---
            
            if co2_total_base <= 0:
                logging.error(f"FAIL: Baseline CO2 is zero or negative: {co2_total_base}")
            else:
                logging.info(f"SUCCESS: Baseline CO2 > 0: {co2_total_base:.2f} kg/m³")
                
            if cost_total_base <= 0:
                logging.error(f"FAIL: Baseline Cost is zero or negative: {cost_total_base}")
            else:
                logging.info(f"SUCCESS: Baseline Cost > 0: {cost_total_base:.2f} ₹/m³")
            
            logging.info("Baseline DataFrame:\n" + base_df.to_string())
            
            # 5. Call generate_mix
            logging.info("Calling generate_mix (optimized)...")
            opt_df, opt_meta, trace = generate_mix(
                test_grade, test_exposure, test_nom_max, test_target_slump, 
                test_agg_shape, test_fine_zone, 
                test_emissions_df, test_costs_df, test_cement_choice, 
                test_material_props, use_sp=True, optimize_cost=False
            )
            
            if opt_df is None or opt_meta is None:
                logging.warning("generate_mix returned None (no feasible mix found). Trace:")
                logging.warning(pd.DataFrame(trace))
            else:
                logging.info(f"generate_mix returned 'meta': {opt_meta}")
                co2_total_opt = opt_meta.get("co2_total", 0.0)
                cost_total_opt = opt_meta.get("cost_total", 0.0)

                if co2_total_opt <= 0:
                    logging.error(f"FAIL: Optimized CO2 is zero or negative: {co2_total_opt}")
                else:
                    logging.info(f"SUCCESS: Optimized CO2 > 0: {co2_total_opt:.2f} kg/m³")
                    
                if cost_total_opt <= 0:
                    logging.error(f"FAIL: Optimized Cost is zero or negative: {cost_total_opt}")
                else:
                    logging.info(f"SUCCESS: Optimized Cost > 0: {cost_total_opt:.2f} ₹/m³")
                    
                logging.info("Optimized DataFrame:\n" + opt_df.to_string())
                
                if not (co2_total_opt > 0 and co2_total_opt <= co2_total_base):
                    logging.warning(f"Optimized CO2 ({co2_total_opt:.2f}) is not less than or equal to baseline ({co2_total_base:.2f})")
                else:
                    logging.info("SUCCESS: Optimized CO2 is less than or equal to baseline.")

        except Exception as e:
            logging.error("--- TEST HARNESS FAILED ---")
            logging.error(str(e))
            logging.error(traceback.format_exc())
        
        logging.info(f"--- TEST HARNESS COMPLETE. Report at {report_path} ---")
        print(f"--- TEST HARNESS COMPLETE. Report at {report_path} ---")
