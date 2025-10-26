import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import os, json, re, uuid, time, traceback
from io import BytesIO
from difflib import get_close_matches
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from functools import lru_cache
from itertools import product

# ==============================================================================
# PART 1: CONSTANTS & CORE DATA
# ==============================================================================

S_DIR = os.path.dirname(os.path.abspath(__file__))
LAB_FILE, MIX_FILE = "lab_processed_mgrades_only.xlsx", "concrete_mix_design_data_cleaned_standardized.xlsx"

class C:
    # IS 456 / IS 10262 Constants
    GS = {"M10": 10, "M15": 15, "M20": 20, "M25": 25, "M30": 30, "M35": 35, "M40": 40, "M45": 45, "M50": 50}
    EWL = {"Mild": 0.60, "Moderate": 0.55, "Severe": 0.50, "Very Severe": 0.45, "Marine": 0.40}
    EMC = {"Mild": 300, "Moderate": 300, "Severe": 320, "Very Severe": 340, "Marine": 360}
    EMG = {"Mild": "M20", "Moderate": "M25", "Severe": "M30", "Very Severe": "M35", "Marine": "M40"}
    WB = {10: 208, 12.5: 202, 20: 186, 40: 165}
    ASWA = {"Angular (baseline)": 0.00, "Sub-angular": -0.03, "Sub-rounded": -0.05, "Rounded": -0.07, "Flaky/Elongated": +0.03}
    QCSD = {"Good": 5.0, "Fair": 7.5, "Poor": 10.0}
    EAV = {10: 0.02, 12.5: 0.015, 20: 0.01, 40: 0.008}
    BR = {"M10": (220, 320), "M15": (250, 350), "M20": (300, 400), "M25": (320, 420), "M30": (340, 450), "M35": (360, 480), "M40": (380, 500), "M45": (400, 520), "M50": (420, 540)}
    CAFBZ = {10: {"Zone I": 0.50, "Zone II": 0.48, "Zone III": 0.46, "Zone IV": 0.44}, 12.5: {"Zone I": 0.59, "Zone II": 0.57, "Zone III": 0.55, "Zone IV": 0.53}, 20: {"Zone I": 0.66, "Zone II": 0.64, "Zone III": 0.62, "Zone IV": 0.60}, 40: {"Zone I": 0.71, "Zone II": 0.69, "Zone III": 0.67, "Zone IV": 0.65}}
    FAZL = {"Zone I": {"10.0": (100,100),"4.75": (90,100),"2.36": (60,95),"1.18": (30,70),"0.600": (15,34),"0.300": (5,20),"0.150": (0,10)}, "Zone II": {"10.0": (100,100),"4.75": (90,100),"2.36": (75,100),"1.18": (55,90),"0.600": (35,59),"0.300": (8,30),"0.150": (0,10)}, "Zone III": {"10.0": (100,100),"4.75": (90,100),"2.36": (85,100),"1.18": (75,90),"0.600": (60,79),"0.300": (12,40),"0.150": (0,10)}, "Zone IV": {"10.0": (95,100),"4.75": (95,100),"2.36": (95,100),"1.18": (90,100),"0.600": (80,100),"0.300": (15,50),"0.150": (0,15)}}
    CL = {10: {"20.0": (100,100), "10.0": (85,100), "4.75": (0,20)}, 20: {"40.0": (95,100), "20.0": (95,100), "10.0": (25,55), "4.75": (0,10)}, 40: {"80.0": (95,100), "40.0": (95,100), "20.0": (30,70), "10.0": (0,15)}}
    
    # Column mapping for factor files
    ECM = {"material": "Material", "co2_factor_kg_co2_per_kg": "CO2_Factor(kg_CO2_per_kg)", "co2_factor": "CO2_Factor(kg_CO2_per_kg)", "co2factor": "CO2_Factor(kg_CO2_per_kg)", "emission_factor": "CO2_Factor(kg_CO2_per_kg)", "co2factor_kgco2perkg": "CO2_Factor(kg_CO2_per_kg)", "co2": "CO2_Factor(kg_CO2_per_kg)"}
    CCM = {"material": "Material", "cost_kg": "Cost(₹/kg)", "cost_rs_kg": "Cost(₹/kg)", "cost": "Cost(₹/kg)", "cost_per_kg": "Cost(₹/kg)", "costperkg": "Cost(₹/kg)", "price": "Cost(₹/kg)", "kg": "Cost(₹/kg)", "rs_kg": "Cost(₹/kg)", "costper": "Cost(₹/kg)", "price_kg": "Cost(₹/kg)", "priceperkg": "Cost(₹/kg)"}
    MCM = {"material": "Material", "specificgravity": "SpecificGravity", "specific_gravity": "SpecificGravity", "moisturecontent": "MoistureContent", "moisture_content": "MoistureContent", "waterabsorption": "WaterAbsorption", "water_absorption": "WaterAbsorption"}
    
    # Purpose Profiles
    PP = {"General": {"description": "A balanced, default mix. Follows IS code minimums without specific optimization bias.", "wb_limit": 1.0, "scm_limit": 0.5, "min_binder": 0.0, "weights": {"co2": 0.4, "cost": 0.4, "purpose": 0.2}}, "Slab": {"description": "Prioritizes workability (slump) and cost-effectiveness. Strength is often not the primary driver.", "wb_limit": 0.55, "scm_limit": 0.5, "min_binder": 300, "weights": {"co2": 0.3, "cost": 0.5, "purpose": 0.2}}, "Beam": {"description": "Prioritizes strength (modulus) and durability. Often heavily reinforced.", "wb_limit": 0.50, "scm_limit": 0.4, "min_binder": 320, "weights": {"co2": 0.4, "cost": 0.2, "purpose": 0.4}}, "Column": {"description": "Prioritizes high compressive strength and durability. Congestion is common.", "wb_limit": 0.45, "scm_limit": 0.35, "min_binder": 340, "weights": {"co2": 0.3, "cost": 0.2, "purpose": 0.5}}, "Pavement": {"description": "Prioritizes durability, flexural strength (fatigue), and abrasion resistance. Cost is a major factor.", "wb_limit": 0.45, "scm_limit": 0.4, "min_binder": 340, "weights": {"co2": 0.3, "cost": 0.4, "purpose": 0.3}}, "Precast": {"description": "Prioritizes high early strength (for form stripping), surface finish, and cost (reproducibility).", "wb_limit": 0.45, "scm_limit": 0.3, "min_binder": 360, "weights": {"co2": 0.2, "cost": 0.5, "purpose": 0.3}}}
    CT = ["OPC 33", "OPC 43", "OPC 53", "PPC"]
    
    # Normalized names
    NC, NFA, NGGBS, NW, NSP, NFA_AGG, NCA_AGG = "cement", "fly ash", "ggbs", "water", "pce superplasticizer", "fine aggregate", "coarse aggregate"
    CHR = ["grade", "exposure", "target_slump", "nom_max", "cement_choice"]

# ==============================================================================
# PART 2: CACHED LOADERS & BACKEND LOGIC
# ==============================================================================

client = None
try:
    from groq import Groq
    GAK = os.getenv("GROQ_API_KEY") or st.secrets.get("GROQ_API_KEY", None)
    if GAK:
        client = Groq(api_key=GAK)
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

@st.cache_data
def lde(fn):
    paths = [os.path.join(S_DIR, fn), os.path.join(S_DIR, "data", fn)]
    for p in paths:
        if os.path.exists(p):
            try: return pd.read_excel(p)
            except Exception:
                try: return pd.read_excel(p, engine="openpyxl")
                except Exception as e: st.warning(f"Failed to read {p}: {e}")
    return None

lab_df, mix_df = lde(LAB_FILE), lde(MIX_FILE)

def _nh(h):
    s = str(h).strip().lower()
    s = re.sub(r'[ \-/\.\(\)]+', '_', s)
    s = re.sub(r'[^a-z0-9_]+', '', s)
    return re.sub(r'_+', '_', s).strip('_')

@lru_cache(maxsize=128)
def _nmv(s: str) -> str:
    if s is None: return ""
    s = str(s).strip().lower()
    s = re.sub(r'\b(\d+mm)\b', r'\1', s)
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip().replace('mm', '').strip()
    synonyms = {"m sand": C.NFA_AGG, "msand": C.NFA_AGG, "m-sand": C.NFA_AGG, "fine aggregate": C.NFA_AGG, "sand": C.NFA_AGG, "20 coarse aggregate": C.NCA_AGG, "20mm coarse aggregate": C.NCA_AGG, "20 coarse": C.NCA_AGG, "20": C.NCA_AGG, "coarse aggregate": C.NCA_AGG, "20mm": C.NCA_AGG, "pce superplasticizer": C.NSP, "pce superplasticiser": C.NSP, "pce": C.NSP, "opc 33": "opc 33", "opc 43": "opc 43", "opc 53": "opc 53", "ppc": "ppc", "fly ash": C.NFA, "ggbs": C.NGGBS, "water": C.NW}
    cand = get_close_matches(s, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    key2 = re.sub(r'^\d+\s*', '', s)
    cand = get_close_matches(key2, list(synonyms.keys()), n=1, cutoff=0.78)
    if cand: return synonyms[cand[0]]
    if s.startswith("opc"): return s
    return s

def _nc(df, cm):
    cc = list(dict.fromkeys(cm.values()))
    if df is None or df.empty: return pd.DataFrame(columns=cc)
    df = df.copy()
    nc, rd = {}, {}
    for col in df.columns: nc[_nh(col)] = col
    for variant, canonical in cm.items():
        if variant in nc:
            ocn = nc[variant]
            if canonical not in rd.values(): rd[ocn] = canonical
    df = df.rename(columns=rd)
    return df[[col for col in cc if col in df.columns]]

def _ms(s: pd.Series) -> pd.Series:
    min_v, max_v = s.min(), s.max()
    if pd.isna(min_v) or pd.isna(max_v) or (max_v - min_v) == 0: return pd.Series(0.0, index=s.index, dtype=float)
    return (s - min_v) / (max_v - min_v)

@st.cache_data
def lpp(filepath=None): return C.PP

def e_p_s_m(cm: dict, purpose: str) -> dict:
    try:
        fck_t, wb = float(cm.get('fck_target', 30.0)), float(cm.get('w_b', 0.5))
        binder, water = float(cm.get('cementitious', 350.0)), float(cm.get('water_target', 180.0))
        mp = 5000 * np.sqrt(fck_t)
        sri = (binder * water) / 10000.0
        fp = (1.0 - wb) * (binder / 1000.0)
        return {"estimated_modulus_proxy (MPa)": round(mp, 0), "shrinkage_risk_index": round(sri, 2), "pavement_fatigue_proxy": round(fp, 2)}
    except Exception:
        return {"estimated_modulus_proxy (MPa)": None, "shrinkage_risk_index": None, "pavement_fatigue_proxy": None}

@st.cache_data
def c_p_p_v(df: pd.DataFrame, pp: dict) -> pd.Series:
    if not pp: return pd.Series(0.0, index=df.index)
    penalty = pd.Series(0.0, index=df.index)
    penalty += (df['w_b'] - pp.get('wb_limit', 1.0)).clip(lower=0) * 1000
    penalty += (df['scm_total_frac'] - pp.get('scm_limit', 0.5)).clip(lower=0) * 100
    penalty += (pp.get('min_binder', 0.0) - df['binder']).clip(lower=0) * 0.1
    return penalty.fillna(0.0)

@st.cache_data
def ld(mf=None, ef=None, cf=None):
    def _sr(f, d):
        if f is not None:
            try:
                if hasattr(f, 'seek'): f.seek(0)
                return pd.read_csv(f)
            except Exception as e: st.warning(f"Could not read uploaded file {f.name}: {e}"); return d
        return d
    
    def _lf(dn):
        paths = [os.path.join(S_DIR, name) for name in dn]
        for p in paths:
            if os.path.exists(p):
                try: return pd.read_csv(p)
                except Exception as e: st.warning(f"Could not read {p}: {e}")
        return None

    m = _sr(mf, _lf(["materials_library.csv", "data/materials_library.csv"]))
    e = _sr(ef, _lf(["emission_factors.csv", "data/emission_factors.csv"]))
    c = _sr(cf, _lf(["cost_factors.csv", "data/cost_factors.csv"]))

    m = _nc(m, C.MCM)
    if "Material" in m.columns: m["Material"] = m["Material"].astype(str).str.strip()
    if m.empty or "Material" not in m.columns: m = pd.DataFrame(columns=list(dict.fromkeys(C.MCM.values())))

    e = _nc(e, C.ECM)
    if "Material" in e.columns: e["Material"] = e["Material"].astype(str).str.strip()
    if e.empty or "Material" not in e.columns or "CO2_Factor(kg_CO2_per_kg)" not in e.columns: e = pd.DataFrame(columns=list(dict.fromkeys(C.ECM.values())))
        
    c = _nc(c, C.CCM)
    if "Material" in c.columns: c["Material"] = c["Material"].astype(str).str.strip()
    if c.empty or "Material" not in c.columns or "Cost(₹/kg)" not in c.columns: c = pd.DataFrame(columns=list(dict.fromkeys(C.CCM.values())))

    return m, e, c

def _m_w(m_df: pd.DataFrame, f_df: pd.DataFrame, f_col: str, w_sk: str, w_p: str) -> pd.DataFrame:
    if f_df is not None and not f_df.empty and f_col in f_df.columns:
        f_df_norm = f_df.copy()
        f_df_norm['Material'] = f_df_norm['Material'].astype(str)
        f_df_norm["Material_norm"] = f_df_norm["Material"].apply(_nmv)
        f_df_norm = f_df_norm.drop_duplicates(subset=["Material_norm"])
        m_df = m_df.merge(f_df_norm[["Material_norm", f_col]], on="Material_norm", how="left")
        
        missing_rows = m_df[m_df[f_col].isna()]
        missing_items = [m for m in missing_rows["Material"].tolist() if m and str(m).strip()]
        
        if missing_items:
            if w_sk not in st.session_state: st.session_state[w_sk] = set()
            new_missing = set(missing_items) - st.session_state[w_sk]
            if new_missing: st.session_state[w_sk].update(new_missing)
            
        m_df[f_col] = m_df[f_col].fillna(0.0)
        return m_df
    else:
        m_df[f_col] = 0.0
        return m_df

def p_f(df, x_col="cost", y_col="co2"):
    if df.empty: return pd.DataFrame(columns=df.columns)
    sorted_df = df.sort_values(by=[x_col, y_col], ascending=[True, True])
    pareto_points, last_y = [], float('inf')
    for _, row in sorted_df.iterrows():
        if row[y_col] < last_y:
            pareto_points.append(row)
            last_y = row[y_col]
    return pd.DataFrame(pareto_points).reset_index(drop=True)

@st.cache_data
def wsas(nmm: int, smm: int, ashape: str, ussp: bool=False, sp_rf: float=0.0) -> float:
    base = C.WB.get(int(nmm), 186.0)
    water = base if smm <= 50 else base * (1 + 0.03 * ((smm - 50) / 25.0))
    water *= (1.0 + C.ASWA.get(ashape, 0.0))
    if ussp and sp_rf > 0: water *= (1 - sp_rf)
    return float(water)

def rbr(grade: str): return C.BR.get(grade, (300, 500))

@st.cache_data
def _gcaf_b(nmm: float, faz: str) -> float: return C.CAFBZ.get(nmm, {}).get(faz, 0.62)

@st.cache_data
def gcaf_v(nmm: float, faz: str, wbr_s: pd.Series) -> pd.Series:
    bf = _gcaf_b(nmm, faz)
    correction = ((0.50 - wbr_s) / 0.05) * 0.01
    return (bf + correction).clip(0.4, 0.8)

@st.cache_data
def rlc(ldf):
    results, std_dev_S = [], C.QCSD["Good"]
    for _, row in ldf.iterrows():
        try:
            grade, strength = str(row['grade']).strip(), float(row['actual_strength'])
            if grade not in C.GS: continue
            fck = C.GS[grade]
            predicted = fck + 1.65 * std_dev_S
            results.append({"Grade": grade, "Exposure": row.get('exposure', 'N/A'), "Slump (mm)": row.get('slump', 'N/A'), "Lab Strength (MPa)": strength, "Predicted Target Strength (MPa)": predicted, "Error (MPa)": predicted - strength})
        except: pass
    if not results: return None, {}
    rdf = pd.DataFrame(results)
    mae = rdf["Error (MPa)"].abs().mean()
    rmse = np.sqrt((rdf["Error (MPa)"].clip(lower=0) ** 2).mean())
    bias = rdf["Error (MPa)"].mean()
    return rdf, {"Mean Absolute Error (MPa)": mae, "Root Mean Squared Error (MPa)": rmse, "Mean Bias (MPa)": bias}

@st.cache_data
def sp(text: str) -> dict:
    result = {}
    grade_match = re.search(r"\bM\s*(10|15|20|25|30|35|40|45|50)\b", text, re.IGNORECASE)
    if grade_match: result["grade"] = "M" + grade_match.group(1)
    if re.search("Marine", text, re.IGNORECASE): result["exposure"] = "Marine"
    else:
        for exp in C.EWL.keys():
            if exp != "Marine" and re.search(exp, text, re.IGNORECASE): result["exposure"] = exp; break
    slump_match = re.search(r"(\d{2,3})\s*mm\s*(?:slump)?", text, re.IGNORECASE)
    if not slump_match: slump_match = re.search(r"slump\s*(?:of\s*)?(\d{2,3})\s*mm", text, re.IGNORECASE)
    if slump_match: result["target_slump"] = int(slump_match.group(1))
    for ctype in C.CT:
        if re.search(ctype.replace(" ", r"\s*"), text, re.IGNORECASE): result["cement_choice"] = ctype; break
    nom_match = re.search(r"(\d{2}(\.5)?)\s*mm\s*(?:agg|aggregate)?", text, re.IGNORECASE)
    if nom_match:
        try:
            val = float(nom_match.group(1))
            if val in [10, 12.5, 20, 40]: result["nom_max"] = val
        except: pass
    for purp in C.PP.keys():
        if re.search(purp, text, re.IGNORECASE): result["purpose"] = purp; break
    return result

@st.cache_data(show_spinner="🤖 Parsing prompt with LLM...")
def pullm(pt: str) -> dict:
    if not st.session_state.get("llm_enabled", False) or client is None: return sp(pt)
    sprompt = f"""You are an expert civil engineer. Extract concrete mix design parameters from the user's prompt.
    Return ONLY a valid JSON object. Do not include any other text or explanations. If a value is not found, omit the key.
    Valid keys and values: - "grade": (String) Must be one of {list(C.GS.keys())} - "exposure": (String) Must be one of {list(C.EWL.keys())}. "Marine" takes precedence over "Severe". - "cement_type": (String) Must be one of {C.CT} - "target_slump": (Integer) Slump in mm (e.g., 100, 125). - "nom_max": (Float or Integer) Must be one of [10, 12.5, 20, 40] - "purpose": (String) Must be one of {list(C.PP.keys())} - "optimize_for": (String) Must be "CO2" or "Cost". - "use_superplasticizer": (Boolean)
    User Prompt: "I need M30 for severe marine exposure, 20mm agg, 100 slump, use PPC for a column"
    JSON: {{"grade": "M30", "exposure": "Marine", "nom_max": 20, "target_slump": 100, "cement_type": "PPC", "purpose": "Column"}}"""
    
    try:
        resp = client.chat.completions.create(model="mixtral-8x7b-32768", messages=[{"role": "system", "content": sprompt}, {"role": "user", "content": pt}], temperature=0.0, response_format={"type": "json_object"})
        pj = json.loads(resp.choices[0].message.content)
        cd = {}
        if pj.get("grade") in C.GS: cd["grade"] = pj["grade"]
        if pj.get("exposure") in C.EWL: cd["exposure"] = pj["exposure"]
        if pj.get("cement_type") in C.CT: cd["cement_choice"] = pj["cement_type"]
        if pj.get("nom_max") in [10, 12.5, 20, 40]: cd["nom_max"] = float(pj["nom_max"])
        if isinstance(pj.get("target_slump"), int): cd["target_slump"] = max(25, min(180, pj["target_slump"]))
        if pj.get("purpose") in C.PP: cd["purpose"] = pj["purpose"]
        if pj.get("optimize_for") in ["CO2", "Cost"]: cd["optimize_for"] = pj["optimize_for"]
        if isinstance(pj.get("use_superplasticizer"), bool): cd["use_sp"] = pj["use_superplasticizer"]
        return cd
    except Exception as e:
        st.error(f"LLM Parser Error: {e}. Falling back to regex.")
        return sp(pt)

# ==============================================================================
# PART 3: CORE MIX GENERATION & EVALUATION
# ==============================================================================

def em(cd, edf, cdf=None):
    comp_items = [(m.strip(), q) for m, q in cd.items() if q > 0.01]
    df = pd.DataFrame(comp_items, columns=["Material", "Quantity (kg/m3)"])
    df["Material_norm"] = df["Material"].apply(_nmv)
    
    df = _m_w(df, edf, "CO2_Factor(kg_CO2_per_kg)", "warned_emissions", "No emission factors found for")
    df["CO2_Emissions (kg/m3)"] = df["Quantity (kg/m3)"] * df["CO2_Factor(kg_CO2_per_kg)"]

    df = _m_w(df, cdf, "Cost(₹/kg)", "warned_costs", "No cost factors found for")
    df["Cost (₹/m3)"] = df["Quantity (kg/m3)"] * df["Cost(₹/kg)"]
    
    df["Material"] = df["Material"].str.title()
    for col in ["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]:
        if col not in df.columns: df[col] = 0.0 if "kg" in col or "m3" in col else ""
            
    return df[["Material","Quantity (kg/m3)","CO2_Factor(kg_CO2_per_kg)","CO2_Emissions (kg/m3)","Cost(₹/kg)","Cost (₹/m3)"]]

def ac_v(dmp: float, ams_s: pd.Series):
    water_delta_s = (dmp / 100.0) * ams_s
    corrected_mass_s = ams_s * (1 + dmp / 100.0)
    return water_delta_s, corrected_mass_s

def ca_v(b_s, w_s, sp_s, caf_s, nmm, dfa, dca):
    vc = b_s / 3150.0
    vw = w_s / 1000.0
    vsp = sp_s / 1200.0
    va = C.EAV.get(int(nmm), 0.01)
    vpa = vc + vw + vsp + va
    vagg = (1.0 - vpa).clip(lower=0.60)
    vc_agg = vagg * caf_s
    vf_agg = vagg * (1.0 - caf_s)
    mfa_ssd = vf_agg * dfa
    mca_ssd = vc_agg * dca
    return mfa_ssd, mca_ssd

def cc(mdf, meta, exposure):
    checks = {}
    try: checks["W/B ≤ exposure limit"] = float(meta["w_b"]) <= C.EWL[exposure]
    except: checks["W/B ≤ exposure limit"] = False
    try: checks["Min cementitious met"] = float(meta["cementitious"]) >= float(C.EMC[exposure])
    except: checks["Min cementitious met"] = False
    try: checks["SCM ≤ 50%"] = float(meta.get("scm_total_frac", 0.0)) <= 0.50
    except: checks["SCM ≤ 50%"] = False
    try:
        tm = float(mdf["Quantity (kg/m3)"].sum())
        checks["Unit weight 2200–2600 kg/m³"] = 2200.0 <= tm <= 2600.0
    except: checks["Unit weight 2200–2600 kg/m³"] = False
    derived = {"w/b used": round(float(meta.get("w_b", 0.0)), 3), "cementitious (kg/m³)": round(float(meta.get("cementitious", 0.0)), 1), "SCM % of cementitious": round(100 * float(meta.get("scm_total_frac", 0.0)), 1), "total mass (kg/m³)": round(float(mdf["Quantity (kg/m3)"].sum()), 1) if "Quantity (kg/m3)" in mdf.columns else None, "water target (kg/m³)": round(float(meta.get("water_target", 0.0)), 1), "cement (kg/m³)": round(float(meta.get("cement", 0.0)), 1), "fly ash (kg/m³)": round(float(meta.get("flyash", 0.0)), 1), "GGBS (kg/m³)": round(float(meta.get("ggbs", 0.0)), 1), "fine agg (kg/m³)": round(float(meta.get("fine", 0.0)), 1), "coarse agg (kg/m³)": round(float(meta.get("coarse", 0.0)), 1), "SP (kg/m³)": round(float(meta.get("sp", 0.0)), 2), "fck (MPa)": meta.get("fck"), "fck,target (MPa)": meta.get("fck_target"), "QC (S, MPa)": meta.get("stddev_S")}
    if "purpose" in meta and meta["purpose"] != "General":
        derived.update({"purpose": meta["purpose"], "purpose_penalty": meta.get("purpose_penalty"), "composite_score": meta.get("composite_score"), "purpose_metrics": meta.get("purpose_metrics")})
    return checks, derived

def s_c_m(meta, df):
    warnings = []
    try: cement, water, fine, coarse, sp = float(meta.get("cement", 0)), float(meta.get("water_target", 0)), float(meta.get("fine", 0)), float(meta.get("coarse", 0)), float(meta.get("sp", 0))
    except Exception: return ["Insufficient data to run sanity checks."]
    if cement > 500: warnings.append(f"High cement content ({cement:.1f} kg/m³). Increases cost, shrinkage, and CO₂.")
    if not 140 <= water <= 220: warnings.append(f"Water content ({water:.1f} kg/m³) is outside the typical range of 140-220 kg/m³.")
    if not 500 <= fine <= 900: warnings.append(f"Fine aggregate quantity ({fine:.1f} kg/m³) is unusual.")
    if not 1000 <= coarse <= 1300: warnings.append(f"Coarse aggregate quantity ({coarse:.1f} kg/m³) is unusual.")
    if sp > 20: warnings.append(f"Superplasticizer dosage ({sp:.1f} kg/m³) is unusually high.")
    return warnings

def cf(mdf, meta, exposure):
    checks, derived = cc(mdf, meta, exposure)
    warnings = s_c_m(meta, mdf)
    reasons_fail = [f"IS Code Fail: {k}" for k, v in checks.items() if not v]
    feasible = len(reasons_fail) == 0
    return feasible, reasons_fail, warnings, derived, checks

def gcr_v(df: pd.DataFrame, e: str) -> pd.Series:
    lwb, lcem = C.EWL[e], C.EMC[e]
    reasons = pd.Series("", index=df.index, dtype=str)
    reasons += np.where(df['w_b'] > lwb, "Failed W/B ratio (" + df['w_b'].round(3).astype(str) + " > " + str(lwb) + "); ", "")
    reasons += np.where(df['binder'] < lcem, "Cementitious below minimum (" + df['binder'].round(1).astype(str) + " < " + str(lcem) + "); ", "")
    reasons += np.where(df['scm_total_frac'] > 0.50, "SCM fraction exceeds limit (" + (df['scm_total_frac'] * 100).round(0).astype(str) + "% > 50%); ", "")
    reasons += np.where(~((df['total_mass'] >= 2200) & (df['total_mass'] <= 2600)), "Unit weight outside range (" + df['total_mass'].round(1).astype(str) + " not in 2200-2600); ", "")
    reasons = reasons.str.strip().str.rstrip(';')
    return np.where(reasons == "", "All IS-code checks passed.", reasons)

@st.cache_data
def _gmf(ml, edf, cdf):
    nm = {m: _nmv(m) for m in ml}
    co2_factors, cost_factors = {}, {}
    
    if edf is not None and not edf.empty and "CO2_Factor(kg_CO2_per_kg)" in edf.columns:
        edf_norm = edf.copy(); edf_norm['Material'] = edf_norm['Material'].astype(str)
        edf_norm["Material_norm"] = edf_norm["Material"].apply(_nmv)
        co2_factors = edf_norm.drop_duplicates(subset=["Material_norm"]).set_index("Material_norm")["CO2_Factor(kg_CO2_per_kg)"].to_dict()

    if cdf is not None and not cdf.empty and "Cost(₹/kg)" in cdf.columns:
        cdf_norm = cdf.copy(); cdf_norm['Material'] = cdf_norm['Material'].astype(str)
        cdf_norm["Material_norm"] = cdf_norm["Material"].apply(_nmv)
        cost_factors = cdf_norm.drop_duplicates(subset=["Material_norm"]).set_index("Material_norm")["Cost(₹/kg)"].to_dict()

    fco2 = {norm: co2_factors.get(norm, 0.0) for norm in set(nm.values())}
    fcost = {norm: cost_factors.get(norm, 0.0) for norm in set(nm.values())}
    return fco2, fcost

def gm(g, e, nm, ts, ashape, fz, emissions, costs, cc, mp, ussp=True, sp_r=0.18, oc=False, wb_min=0.35, wb_s=6, mf_frac=0.3, mg_frac=0.5, scm_s=0.1, ff_o=None, purpose='General', pp=None, pw=None, epc=False, st_p=None):
    if st_p: st_p.progress(0.0, text="Initializing parameters...")
    
    lwb, mce = float(C.EWL[e]), float(C.EMC[e])
    tw = wsas(nm, int(ts), ashape, ussp, sp_r)
    m_b_g, m_b_g = rbr(g)
    dfa, dca = mp['sg_fa'] * 1000, mp['sg_ca'] * 1000
    
    if 'warned_emissions' in st.session_state: st.session_state.warned_emissions.clear()
    if 'warned_costs' in st.session_state: st.session_state.warned_costs.clear()
        
    pp = pp or C.PP['General']
    pw = pw or C.PP['General']['weights']

    if st_p: st_p.progress(0.05, text="Pre-computing cost/CO2 factors...")
    nc_c = _nmv(cc)
    ml = [nc_c, C.NFA, C.NGGBS, C.NW, C.NSP, C.NFA_AGG, C.NCA_AGG]
    co2f, costf = _gmf(ml, emissions, costs)

    if st_p: st_p.progress(0.1, text="Creating optimization grid...")
    wb_v = np.linspace(float(wb_min), float(lwb), int(wb_s))
    fa_o = np.arange(0.0, mf_frac + 1e-9, scm_s)
    ggbs_o = np.arange(0.0, mg_frac + 1e-9, scm_s)
    
    gp = list(product(wb_v, fa_o, ggbs_o))
    gdf = pd.DataFrame(gp, columns=['wb_input', 'flyash_frac', 'ggbs_frac'])
    gdf = gdf[gdf['flyash_frac'] + gdf['ggbs_frac'] <= 0.50].copy()
    if gdf.empty: return None, None, []

    if st_p: st_p.progress(0.2, text="Calculating binder properties...")
    gdf['b_for_s'] = tw / gdf['wb_input']
    gdf['binder'] = np.maximum(np.maximum(gdf['b_for_s'], mce), m_b_g)
    gdf['binder'] = np.minimum(gdf['binder'], m_b_g)
    gdf['w_b'] = tw / gdf['binder']
    
    gdf['scm_total_frac'] = gdf['flyash_frac'] + gdf['ggbs_frac']
    gdf['cement'] = gdf['binder'] * (1 - gdf['scm_total_frac'])
    gdf['flyash'] = gdf['binder'] * gdf['flyash_frac']
    gdf['ggbs'] = gdf['binder'] * gdf['ggbs_frac']
    gdf['sp'] = (0.01 * gdf['binder']) if ussp else 0.0
    
    if st_p: st_p.progress(0.3, text="Calculating aggregate proportions...")
    if ff_o is not None and ff_o > 0.3: gdf['coarse_agg_fraction'] = 1.0 - ff_o
    else: gdf['coarse_agg_fraction'] = gcaf_v(nm, fz, gdf['w_b'])
    
    gdf['fine_ssd'], gdf['coarse_ssd'] = ca_v(gdf['binder'], tw, gdf['sp'], gdf['coarse_agg_fraction'], nm, dfa, dca)
    wdfa_s, gdf['fine_wet'] = ac_v(mp['moisture_fa'], gdf['fine_ssd'])
    wdca_s, gdf['coarse_wet'] = ac_v(mp['moisture_ca'], gdf['coarse_ssd'])
    
    gdf['water_final'] = (tw - (wdfa_s + wdca_s)).clip(lower=5.0)

    if st_p: st_p.progress(0.5, text="Calculating cost and CO2...")
    gdf['co2_total'] = (gdf['cement'] * co2f.get(nc_c, 0.0) + gdf['flyash'] * co2f.get(C.NFA, 0.0) + gdf['ggbs'] * co2f.get(C.NGGBS, 0.0) + gdf['water_final'] * co2f.get(C.NW, 0.0) + gdf['sp'] * co2f.get(C.NSP, 0.0) + gdf['fine_wet'] * co2f.get(C.NFA_AGG, 0.0) + gdf['coarse_wet'] * co2f.get(C.NCA_AGG, 0.0))
    gdf['cost_total'] = (gdf['cement'] * costf.get(nc_c, 0.0) + gdf['flyash'] * costf.get(C.NFA, 0.0) + gdf['ggbs'] * costf.get(C.NGGBS, 0.0) + gdf['water_final'] * costf.get(C.NW, 0.0) + gdf['sp'] * costf.get(C.NSP, 0.0) + gdf['fine_wet'] * costf.get(C.NFA_AGG, 0.0) + gdf['coarse_wet'] * costf.get(C.NCA_AGG, 0.0))

    if st_p: st_p.progress(0.7, text="Checking compliance and purpose-fit...")
    gdf['total_mass'] = (gdf['cement'] + gdf['flyash'] + gdf['ggbs'] + gdf['water_final'] + gdf['sp'] + gdf['fine_wet'] + gdf['coarse_wet'])
    gdf['feasible'] = (gdf['w_b'] <= lwb) & (gdf['binder'] >= mce) & (gdf['scm_total_frac'] <= 0.50) & ((gdf['total_mass'] >= 2200.0) & (gdf['total_mass'] <= 2600.0))
    gdf['reasons'] = gcr_v(gdf, e)
    gdf['purpose_penalty'] = c_p_p_v(gdf, pp)
    gdf['purpose'] = purpose

    if st_p: st_p.progress(0.8, text="Finding best mix design...")
    fcdf = gdf[gdf['feasible']].copy()
    
    if fcdf.empty:
        tdf = gdf.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
        return None, None, tdf.to_dict('records')

    if not epc or purpose == 'General':
        obj_col = 'cost_total' if oc else 'co2_total'
        fcdf['composite_score'] = np.nan
        best_idx = fcdf[obj_col].idxmin()
    else:
        fcdf['norm_co2'] = _ms(fcdf['co2_total'])
        fcdf['norm_cost'] = _ms(fcdf['cost_total'])
        fcdf['norm_purpose'] = _ms(fcdf['purpose_penalty'])
        
        w_co2, w_cost, w_purpose = pw.get('w_co2', 0.4), pw.get('w_cost', 0.4), pw.get('w_purpose', 0.2)
        fcdf['composite_score'] = (w_co2 * fcdf['norm_co2'] + w_cost * fcdf['norm_cost'] + w_purpose * fcdf['norm_purpose'])
        best_idx = fcdf['composite_score'].idxmin()

    best_meta_s = fcdf.loc[best_idx]

    if st_p: st_p.progress(0.9, text="Generating final mix report...")
    best_mix_d = {cc: best_meta_s['cement'], "Fly Ash": best_meta_s['flyash'], "GGBS": best_meta_s['ggbs'], "Water": best_meta_s['water_final'], "PCE Superplasticizer": best_meta_s['sp'], "Fine Aggregate": best_meta_s['fine_wet'], "Coarse Aggregate": best_meta_s['coarse_wet']}
    best_df = em(best_mix_d, emissions, costs)
    
    best_meta = best_meta_s.to_dict()
    best_meta.update({"cementitious": best_meta_s['binder'], "water_target": tw, "fine": best_meta_s['fine_wet'], "coarse": best_meta_s['coarse_wet'], "grade": g, "exposure": e, "nom_max": nm, "slump": ts, "binder_range": (m_b_g, m_b_g), "material_props": mp, "purpose_metrics": e_p_s_m(best_meta, purpose)})
    
    tdf = gdf.rename(columns={"w_b": "wb", "cost_total": "cost", "co2_total": "co2"})
    score_cols = ['composite_score', 'norm_co2', 'norm_cost', 'norm_purpose']
    if all(col in fcdf.columns for col in score_cols):
        tdf = tdf.merge(fcdf[score_cols], left_index=True, right_index=True, how='left')
        
    return best_df, best_meta, tdf.to_dict('records')

def gb(g, e, nm, ts, ashape, fz, emissions, costs, cc, mp, ussp=True, sp_r=0.18, purpose='General', pp=None):
    lwb, mce = float(C.EWL[e]), float(C.EMC[e])
    tw = wsas(nm, int(ts), ashape, ussp, sp_r)
    m_b_g, m_b_g = rbr(g)

    b_for_wb = tw / lwb
    c = min(max(b_for_wb, mce, m_b_g), m_b_g)
    awb = tw / c
    sp = 0.01 * c if ussp else 0.0
    caf = gcaf_v(nm, fz, pd.Series([awb])).iloc[0] # Use scalar version's logic
    dfa, dca = mp['sg_fa'] * 1000, mp['sg_ca'] * 1000
    
    # Inline compute_aggregates
    vc, vw, vsp, va = c / 3150.0, tw / 1000.0, sp / 1200.0, C.EAV.get(int(nm), 0.01)
    vagg = 1.0 - (vc + vw + vsp + va)
    if vagg <= 0: vagg = 0.60
    vca, vfa = vagg * caf, vagg * (1.0 - caf)
    f_ssd, c_ssd = vfa * dfa, vca * dca

    wdfa, f_wet = ac_v(mp['moisture_fa'], pd.Series([f_ssd]))
    wdca, c_wet = ac_v(mp['moisture_ca'], pd.Series([c_ssd]))
    wf = max(5.0, tw - (wdfa.iloc[0] + wdca.iloc[0]))
    
    mix = {cc: c,"Fly Ash": 0.0,"GGBS": 0.0,"Water": wf, "PCE Superplasticizer": sp,"Fine Aggregate": f_wet.iloc[0],"Coarse Aggregate": c_wet.iloc[0]}
    df = em(mix, emissions, costs)
    
    co2t, costt = float(df["CO2_Emissions (kg/m3)"].sum()), float(df["Cost (₹/m3)"].sum())
    
    meta = {"w_b": awb, "cementitious": c, "cement": c, "flyash": 0.0, "ggbs": 0.0, "water_target": tw, "water_final": wf, "sp": sp, "fine": f_wet.iloc[0], "coarse": c_wet.iloc[0], "scm_total_frac": 0.0, "grade": g, "exposure": e, "nom_max": nm, "slump": ts, "co2_total": co2t, "cost_total": costt, "coarse_agg_fraction": caf, "material_props": mp, "binder_range": (m_b_g, m_b_g)}
    
    pp = pp or C.PP.get(purpose, C.PP['General'])
    meta.update({"purpose": purpose, "purpose_metrics": e_p_s_m(meta, purpose), "purpose_penalty": 0.0, "composite_score": np.nan}) # Baseline has 0 penalty
    return df, meta

def ap(ut, ci, ullm=False):
    if not ut.strip(): return ci, [], {}
    try: parsed = pullm(ut) if ullm else sp(ut)
    except Exception as e: st.warning(f"Parser error: {e}, falling back to regex"); parsed = sp(ut)
    
    msgs, updated = [], ci.copy()
    if "grade" in parsed and parsed["grade"] in C.GS: updated["grade"] = parsed["grade"]; msgs.append(f"✅ Parser set Grade to **{parsed['grade']}**")
    if "exposure" in parsed and parsed["exposure"] in C.EWL: updated["exposure"] = parsed["exposure"]; msgs.append(f"✅ Parser set Exposure to **{parsed['exposure']}**")
    if "target_slump" in parsed: s = max(25, min(180, int(parsed["target_slump"]))); updated["target_slump"] = s; msgs.append(f"✅ Parser set Target Slump to **{s} mm**")
    if "cement_choice" in parsed and parsed["cement_choice"] in C.CT: updated["cement_choice"] = parsed["cement_choice"]; msgs.append(f"✅ Parser set Cement Type to **{parsed['cement_choice']}**")
    if "nom_max" in parsed and parsed["nom_max"] in [10, 12.5, 20, 40]: updated["nom_max"] = parsed["nom_max"]; msgs.append(f"✅ Parser set Aggregate Size to **{parsed['nom_max']} mm**")
    if "purpose" in parsed and parsed["purpose"] in C.PP: updated["purpose"] = parsed["purpose"]; msgs.append(f"✅ Parser set Purpose to **{parsed['purpose']}**")
    return updated, msgs, parsed

# ==============================================================================
# PART 5: CORE GENERATION LOGIC (MODULARIZED)
# ==============================================================================

def rgl(i: dict, edf: pd.DataFrame, cdf: pd.DataFrame, ppd: dict, st_p=None):
    try:
        min_g_req, g_order = C.EMG[i["exposure"]], list(C.GS.keys())
        if g_order.index(i["grade"]) < g_order.index(min_g_req):
            st.warning(f"For **{i['exposure']}** exposure, IS 456 recommends a minimum grade of **{min_g_req}**. The grade has been automatically updated.", icon="⚠️")
            i["grade"] = min_g_req; st.session_state.final_inputs["grade"] = min_g_req
        
        ck, purpose = i.get("calibration_kwargs", {}), i.get('purpose', 'General')
        pp = ppd.get(purpose, ppd['General'])
        epc, pw = i.get('enable_purpose_optimization', False), i.get('purpose_weights', ppd['General']['weights'])
        if purpose == 'General': epc = False
        
        fck, S = C.GS[i["grade"]], C.QCSD[i.get("qc_level", "Good")]
        fck_t = fck + 1.65 * S
        
        if st_p: st_p.progress(0.1, text="Running optimization...")
        o_df, o_meta, trace = gm(i["grade"], i["exposure"], i["nom_max"], i["target_slump"], i["agg_shape"], i["fine_zone"], edf, cdf, i["cement_choice"], mp=i["material_props"], ussp=i["use_sp"], oc=i["optimize_cost"], purpose=purpose, pp=pp, pw=pw, epc=epc, st_p=st_p, **ck)
        
        if st_p: st_p.progress(0.95, text="Generating baseline comparison...")
        b_df, b_meta = gb(i["grade"], i["exposure"], i["nom_max"], i["target_slump"], i["agg_shape"], i["fine_zone"], edf, cdf, i["cement_choice"], mp=i["material_props"], ussp=i.get("use_sp", True), purpose=purpose, pp=pp)
        
        if st_p: st_p.empty()

        if o_df is None or b_df is None:
            st.error("Could not find a feasible mix design with the given constraints. Try adjusting the parameters, such as a higher grade or less restrictive exposure condition.", icon="❌")
            st.session_state.results = {"success": False, "trace": trace}
        else:
            if not st.session_state.get("chat_mode", False): st.success(f"Successfully generated mix designs for **{i['grade']}** concrete in **{i['exposure']}** conditions.", icon="✅")
                
            for m in (o_meta, b_meta): m.update({"fck": fck, "fck_target": round(fck_t, 1), "stddev_S": S, "qc_level": i.get("qc_level", "Good"), "agg_shape": i.get("agg_shape"), "fine_zone": i.get("fine_zone")})
            
            st.session_state.results = {"success": True, "opt_df": o_df, "opt_meta": o_meta, "base_df": b_df, "base_meta": b_meta, "trace": trace, "inputs": i, "fck_target": fck_t, "fck": fck, "S": S}
            
    except Exception as e:
        st.error(f"An unexpected error occurred: {e}", icon="💥")
        st.exception(traceback.format_exc())
        st.session_state.results = {"success": False, "trace": None}

# ==============================================================================
# PART 6: STREAMLIT APP (UI Sub-modules)
# ==============================================================================

def _poc(st_c, title, y_l, base_v, opt_v, colors, fmt_str):
    with st_c:
        st.subheader(title)
        c_d = pd.DataFrame({'Mix Type': ['Baseline OPC', 'CivilGPT Optimized'], y_l: [base_v, opt_v]})
        fig, ax = plt.subplots(figsize=(6, 4))
        bars = ax.bar(c_d['Mix Type'], c_d[y_l], color=colors)
        ax.set_ylabel(y_l); ax.bar_label(bars, fmt=fmt_str)
        st.pyplot(fig)

def dmd(title, df, meta, exposure):
    st.header(title)
    purpose = meta.get("purpose", "General")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("💧 Water/Binder Ratio", f"{meta['w_b']:.3f}")
    c2.metric("📦 Total Binder (kg/m³)", f"{meta['cementitious']:.1f}")
    c3.metric("🎯 Target Strength (MPa)", f"{meta['fck_target']:.1f}")
    c4.metric("⚖️ Unit Weight (kg/m³)", f"{df['Quantity (kg/m3)'].sum():.1f}")
    if purpose != "General":
        cp1, cp2, cp3 = st.columns(3)
        cp1.metric("🛠️ Design Purpose", purpose)
        cp2.metric("⚠️ Purpose Penalty", f"{meta.get('purpose_penalty', 0.0):.2f}", help="Penalty for deviation from purpose targets (lower is better).")
        if "composite_score" in meta and not pd.isna(meta["composite_score"]): cp3.metric("🎯 Composite Score", f"{meta.get('composite_score', 0.0):.3f}", help="Normalized score (lower is better).")
    
    st.subheader("Mix Proportions (per m³)")
    st.dataframe(df.style.format({"Quantity (kg/m3)": "{:.2f}", "CO2_Factor(kg_CO2_per_kg)": "{:.3f}", "CO2_Emissions (kg/m3)": "{:.2f}", "Cost(₹/kg)": "₹{:.2f}", "Cost (₹/m3)": "₹{:.2f}"}), use_container_width=True)

    st.subheader("Compliance & Sanity Checks (IS 10262 & IS 456)")
    is_f, fr, warnings, derived, _ = cf(df, meta, exposure)

    if is_f: st.success("✅ This mix design is compliant with IS code requirements.", icon="👍")
    else: st.error(f"❌ This mix fails {len(fr)} IS code compliance check(s): " + ", ".join(fr), icon="🚨")
    for warning in warnings: st.warning(warning, icon="⚠️")
    if purpose != "General" and "purpose_metrics" in meta:
        with st.expander(f"Show Estimated Purpose-Specific Metrics ({purpose})"): st.json(meta["purpose_metrics"])
    with st.expander("Show detailed calculation parameters"):
        derived.pop("purpose_metrics", None); st.json(derived)

def d_c_w(meta):
    st.header("Step-by-Step Calculation Walkthrough")
    st.markdown(f"""This is a summary of how the **Optimized Mix** was designed according to **IS 10262:2019**.
    #### 1. Target Mean Strength
    - **Characteristic Strength (fck):** `{meta['fck']}` MPa (from Grade {meta['grade']})
    - **Assumed Standard Deviation (S):** `{meta['stddev_S']}` MPa (for '{meta.get('qc_level', 'Good')}' quality control)
    - **Target Mean Strength (f'ck):** `fck + 1.65 * S = {meta['fck']} + 1.65 * {meta['stddev_S']} =` **`{meta['fck_target']:.2f}` MPa**
    #### 2. Water Content
    - **Basis:** IS 10262, Table 4, for `{meta['nom_max']}` mm nominal max aggregate size.
    - **Adjustments:** Slump (`{meta['slump']}` mm), aggregate shape ('{meta.get('agg_shape', 'Angular (baseline)')}'), and superplasticizer use.
    - **Final Target Water (SSD basis):** **`{meta['water_target']:.1f}` kg/m³**
    #### 3. Water-Binder (w/b) Ratio
    - **Constraint:** Maximum w/b ratio for `{meta['exposure']}` exposure is `{C.EWL[meta['exposure']]}`.
    - **Optimizer Selection:** Selected w/b Ratio: **`{meta['w_b']:.3f}`**
    #### 4. Binder Content
    - **Initial Binder (from w/b):** `{(meta['water_target']/meta['w_b']):.1f}` kg/m³
    - **Constraints Check:** Min. for `{meta['exposure']}` exposure: `{C.EMC[meta['exposure']]}` kg/m³. Typical range for `{meta['grade']}`: `{meta['binder_range'][0]}` - `{meta['binder_range'][1]}`
    - **Final Adjusted Binder Content:** **`{meta['cementitious']:.1f}` kg/m³**
    #### 5. SCM & Cement Content
    - **Optimizer Goal:** Minimize CO₂/cost. **Selected SCM Fraction:** `{meta['scm_total_frac']*100:.0f}%`
    - **Material Quantities:** **Cement:** `{meta['cement']:.1f}` kg/m³. **Fly Ash:** `{meta['flyash']:.1f}` kg/m³. **GGBS:** `{meta['ggbs']:.1f}` kg/m³
    #### 6. Aggregate Proportioning (IS 10262, Table 5)
    - **Basis:** Volume of coarse aggregate for `{meta['nom_max']}` mm aggregate and fine aggregate `{meta.get('fine_zone', 'Zone II')}`.
    - **Coarse Aggregate Fraction (by volume):** **`{meta['coarse_agg_fraction']:.3f}`**
    #### 7. Final Quantities (with Moisture Correction)
    - **Fine Aggregate (SSD):** `{(meta['fine'] / (1 + meta['material_props']['moisture_fa']/100)):.1f}` kg/m³
    - **Coarse Aggregate (SSD):** `{(meta['coarse'] / (1 + meta['material_props']['moisture_ca']/100)):.1f}` kg/m³
    - **Moisture Correction:** Adjusted for `{meta['material_props']['moisture_fa']}%` free moisture in fine and `{meta['material_props']['moisture_ca']}%` in coarse aggregate.
    - **Final Batch Weights:** **Water:** **`{meta['water_final']:.1f}` kg/m³**. **Fine Aggregate:** **`{meta['fine']:.1f}` kg/m³**. **Coarse Aggregate:** **`{meta['coarse']:.1f}` kg/m³**""")

def rc_i(ppd: dict):
    st.title("💬 CivilGPT Chat Mode")
    st.markdown("Welcome to the conversational interface. Describe your concrete mix needs, and I'll ask for clarifications.")
    
    for msg in st.session_state.chat_history:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])

    if "results" in st.session_state and st.session_state.results.get("success") and not st.session_state.get("chat_results_displayed", False):
        r, o_m, b_m = st.session_state.results, st.session_state.results["opt_meta"], st.session_state.results["base_meta"]
        r = (b_m["co2_total"] - o_m["co2_total"]) / b_m["co2_total"] * 100 if b_m["co2_total"] > 0 else 0.0
        cs = b_m["cost_total"] - o_m["cost_total"]
        s_m = f"""✅ CivilGPT has designed an **{o_m['grade']}** mix for **{o_m['exposure']}** exposure using **{r['inputs']['cement_choice']}**.
        Here's a quick summary:
        - **🌱 CO₂ reduced by {r:.1f}%** (vs. standard OPC mix)
        - **💰 Cost saved ₹{cs:,.0f} / m³**
        - **⚖️ Final w/b ratio:** {o_m['w_b']:.3f}
        - **📦 Total Binder:** {o_m['cementitious']:.1f} kg/m³
        - **♻️ SCM Content:** {o_m['scm_total_frac']*100:.0f}%
        """
        st.session_state.chat_history.append({"role": "assistant", "content": s_m})
        st.session_state.chat_results_displayed = True
        st.rerun()

    if st.session_state.get("chat_results_displayed", False):
        st.info("Your full mix report is ready. You can ask for refinements or open the full report.")
        
        def s_t_m_m():
            st.session_state["chat_mode"], st.session_state["chat_mode_toggle_functional"] = False, False
            st.session_state["active_tab_name"], st.session_state["manual_tabs"] = "📊 **Overview**", "📊 **Overview**"
            st.session_state["chat_results_displayed"] = False
            st.rerun()

        st.button("📊 Open Full Mix Report & Switch to Manual Mode", use_container_width=True, type="primary", on_click=s_t_m_m, key="switch_to_manual_btn")

    if user_prompt := st.chat_input("Ask CivilGPT anything about your concrete mix..."):
        st.session_state.chat_history.append({"role": "user", "content": user_prompt})
        
        parsed_params = pullm(user_prompt)
        
        if parsed_params:
            st.session_state.chat_inputs.update(parsed_params)
            parsed_summary = ", ".join([f"**{k}**: {v}" for k, v in parsed_params.items()])
            st.session_state.chat_history.append({"role": "assistant", "content": f"Got it. Understood: {parsed_summary}"})

        mf = [f for f in C.CHR if st.session_state.chat_inputs.get(f) is None]
        
        if mf:
            f_to_ask = mf[0]
            q = next((q for f, q in {"grade": "What concrete grade do you need (e.g., M20, M25, M30)?", "exposure": f"What is the exposure condition? (e.g., {', '.join(C.EWL.keys())})", "target_slump": "What is the target slump in mm (e.g., 75, 100, 125)?", "nom_max": "What is the nominal maximum aggregate size in mm (e.g., 10, 20, 40)?", "cement_choice": f"Which cement type would you like to use? (e.g., {', '.join(C.CT)})"}.items() if f == f_to_ask), "I'm missing some information. Can you provide more details?")
            st.session_state.chat_history.append({"role": "assistant", "content": q})
        else:
            st.session_state.chat_history.append({"role": "assistant", "content": "✅ Great, I have all your requirements. Generating your sustainable mix design now..."})
            st.session_state.run_chat_generation = True
            st.session_state.chat_results_displayed = False
            if "results" in st.session_state: del st.session_state.results
            
        st.rerun()


def rmi(ppd: dict, mdf: pd.DataFrame, edf: pd.DataFrame, cdf: pd.DataFrame):
    st.title("🧱 CivilGPT: Sustainable Concrete Mix Designer")
    st.markdown("##### An AI-powered tool for creating **IS 10262:2019 compliant** concrete mixes, optimized for low carbon footprint.")

    c1, c2 = st.columns([0.7, 0.3])
    with c1:
        st.text_area("**Describe Your Requirements**", height=100, placeholder="e.g., Design an M30 grade concrete for severe exposure using OPC 43. Target a slump of 125 mm with 20 mm aggregates.", label_visibility="collapsed", key="user_text_input")
    with c2:
        st.write(""); st.write("")
        run_button = st.button("🚀 Generate Mix Design", use_container_width=True, type="primary")

    with st.expander("⚙️ Advanced Manual Input: Detailed Parameters and Libraries", expanded=False):
        st.subheader("Core Mix Requirements")
        c1, c2, c3, c4 = st.columns(4)
        with c1: grade = st.selectbox("Concrete Grade", list(C.GS.keys()), index=4, key="grade")
        with c2: exposure = st.selectbox("Exposure Condition", list(C.EWL.keys()), index=2, key="exposure")
        with c3: target_slump = st.slider("Target Slump (mm)", 25, 180, 100, 5, key="target_slump")
        with c4: cement_choice = st.selectbox("Cement Type", C.CT, index=1, key="cement_choice")
        
        st.markdown("---"); st.subheader("Aggregate Properties & Geometry")
        a1, a2, a3 = st.columns(3)
        with a1: nom_max = st.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=2, key="nom_max")
        with a2: agg_shape = st.selectbox("Coarse Aggregate Shape", list(C.ASWA.keys()), index=0, key="agg_shape")
        with a3: fine_zone = st.selectbox("Fine Aggregate Zone (IS 383)", ["Zone I","Zone II","Zone III","Zone IV"], index=1, key="fine_zone")
        
        st.markdown("---"); st.subheader("Admixtures & Quality Control")
        d1, d2 = st.columns(2)
        with d1: use_sp = st.checkbox("Use Superplasticizer (PCE)", True, key="use_sp")
        with d2: qc_level = st.selectbox("Quality Control Level", list(C.QCSD.keys()), index=0, key="qc_level")

        st.markdown("---"); st.subheader("Optimization Settings")
        o1, o2 = st.columns(2)
        with o1: purpose = st.selectbox("Design Purpose", list(ppd.keys()), index=0, key="purpose_select", help=ppd.get(st.session_state.get("purpose_select", "General"), {}).get("description", "Select the structural element."))
        with o2: optimize_for = st.selectbox("Single-Objective Priority", ["CO₂ Emissions", "Cost"], index=0, key="optimize_for_select")
        optimize_cost = (optimize_for == "Cost")
        enable_purpose_optimization = st.checkbox("Enable Purpose-Based Composite Optimization", value=(purpose != 'General'), key="enable_purpose")
        
        purpose_weights = ppd['General']['weights']
        if enable_purpose_optimization and purpose != 'General':
            with st.expander("Adjust Composite Optimization Weights", expanded=True):
                default_w = ppd.get(purpose, {}).get('weights', ppd['General']['weights'])
                w_co2 = st.slider("🌱 CO₂ Weight", 0.0, 1.0, default_w['co2'], 0.05, key="w_co2")
                w_cost = st.slider("💰 Cost Weight", 0.0, 1.0, default_w['cost'], 0.05, key="w_cost")
                w_purpose = st.slider("🛠️ Purpose-Fit Weight", 0.0, 1.0, default_w['purpose'], 0.05, key="w_purpose")
                total_w = w_co2 + w_cost + w_purpose
                if total_w == 0: st.warning("Weights cannot all be zero. Defaulting to balanced weights."); purpose_weights = {"w_co2": 0.33, "w_cost": 0.33, "w_purpose": 0.34}
                else: purpose_weights = {"w_co2": w_co2 / total_w, "w_cost": w_cost / total_w, "w_purpose": w_purpose / total_w}; st.caption(f"Normalized: CO₂ {purpose_weights['w_co2']:.1%}, Cost {purpose_weights['w_cost']:.1%}, Purpose {purpose_weights['w_purpose']:.1%}")
        elif enable_purpose_optimization and purpose == 'General': enable_purpose_optimization = False

        st.markdown("---"); st.subheader("Material Properties (Manual Override)")
        sg_fa_d, moisture_fa_d, sg_ca_d, moisture_ca_d = 2.65, 1.0, 2.70, 0.5
        if mdf is not None and not mdf.empty:
            try:
                mdf_l = mdf.copy(); mdf_l['Material'] = mdf_l['Material'].str.strip().str.lower()
                fa_r = mdf_l[mdf_l['Material'] == C.NFA_AGG]; ca_r = mdf_l[mdf_l['Material'] == C.NCA_AGG]
                if not fa_r.empty:
                    if 'SpecificGravity' in fa_r: sg_fa_d = float(fa_r['SpecificGravity'].iloc[0])
                    if 'MoistureContent' in fa_r: moisture_fa_d = float(fa_r['MoistureContent'].iloc[0])
                if not ca_r.empty:
                    if 'SpecificGravity' in ca_r: sg_ca_d = float(ca_r['SpecificGravity'].iloc[0])
                    if 'MoistureContent' in ca_r: moisture_ca_d = float(ca_r['MoistureContent'].iloc[0])
                st.info("Material properties auto-loaded from the Shared Library.", icon="📚")
            except Exception as e: st.error(f"Failed to parse materials library: {e}")

        m1, m2 = st.columns(2)
        with m1:
            st.markdown("###### Fine Aggregate")
            sg_fa = st.number_input("Specific Gravity (FA)", 2.0, 3.0, sg_fa_d, 0.01, key="sg_fa_manual")
            moisture_fa = st.number_input("Free Moisture Content % (FA)", -2.0, 5.0, moisture_fa_d, 0.1, key="moisture_fa_manual")
        with m2:
            st.markdown("###### Coarse Aggregate")
            sg_ca = st.number_input("Specific Gravity (CA)", 2.0, 3.0, sg_ca_d, 0.01, key="sg_ca_manual")
            moisture_ca = st.number_input("Free Moisture Content % (CA)", -2.0, 5.0, moisture_ca_d, 0.1, key="moisture_ca_manual")
            
        st.markdown("---"); st.subheader("File Uploads (Sieve Analysis & Lab Data)")
        st.caption("These files are for analysis and optional calibration, not core mix design input.")
        f1, f2, f3 = st.columns(3)
        with f1: fine_csv = st.file_uploader("Fine Aggregate Sieve CSV", type=["csv"], key="fine_csv")
        with f2: coarse_csv = st.file_uploader("Coarse Aggregate Sieve CSV", type=["csv"], key="coarse_csv")
        with f3: lab_csv = st.file_uploader("Lab Calibration Data CSV", type=["csv"], key="lab_csv")

        st.markdown("---")
        with st.expander("Calibration & Tuning (Developer)", expanded=False):
            e_c_o = st.checkbox("Enable calibration overrides", False, key="enable_calibration_overrides")
            c1, c2 = st.columns(2)
            with c1:
                calib_wb_min = st.number_input("W/B search minimum (wb_min)", 0.30, 0.45, 0.35, 0.01, key="calib_wb_min")
                calib_wb_steps = st.slider("W/B search steps (wb_steps)", 3, 15, 6, 1, key="calib_wb_steps")
                calib_fine_fraction = st.slider("Fine Aggregate Fraction (fine_fraction) Override", 0.30, 0.50, 0.40, 0.01, key="calib_fine_fraction")
            with c2:
                calib_max_flyash_frac = st.slider("Max Fly Ash fraction", 0.0, 0.5, 0.30, 0.05, key="calib_max_flyash_frac")
                calib_max_ggbs_frac = st.slider("Max GGBS fraction", 0.0, 0.5, 0.50, 0.05, key="calib_max_ggbs_frac")
                calib_scm_step = st.slider("SCM fraction step (scm_step)", 0.05, 0.25, 0.10, 0.05, key="calib_scm_step")

    grade, exposure, target_slump, cement_choice, nom_max, agg_shape, fine_zone, use_sp, qc_level, purpose = [st.session_state.get(k) for k in ["grade", "exposure", "target_slump", "cement_choice", "nom_max", "agg_shape", "fine_zone", "use_sp", "qc_level", "purpose_select"]]
    optimize_for, sg_fa, moisture_fa, sg_ca, moisture_ca = [st.session_state.get(k) for k in ["optimize_for_select", "sg_fa_manual", "moisture_fa_manual", "sg_ca_manual", "moisture_ca_manual"]]
    
    e_c_o = st.session_state.get("enable_calibration_overrides", False)
    calib_wb_min = st.session_state.get("calib_wb_min", 0.35) if e_c_o else 0.35
    calib_wb_steps = st.session_state.get("calib_wb_steps", 6) if e_c_o else 6
    calib_max_flyash_frac = st.session_state.get("calib_max_flyash_frac", 0.3) if e_c_o else 0.3
    calib_max_ggbs_frac = st.session_state.get("calib_max_ggbs_frac", 0.5) if e_c_o else 0.5
    calib_scm_step = st.session_state.get("calib_scm_step", 0.1) if e_c_o else 0.1
    c_ff = st.session_state.get("calib_fine_fraction", 0.40) if e_c_o else None
    if c_ff == 0.40 and not e_c_o: c_ff = None

    if 'user_text_input' not in st.session_state: st.session_state.user_text_input = ""
    if run_button:
        st.session_state.run_generation_manual = True
        st.session_state.clarification_needed = False
        if 'results' in st.session_state: del st.session_state.results

        mp = {'sg_fa': sg_fa, 'moisture_fa': moisture_fa, 'sg_ca': sg_ca, 'moisture_ca': moisture_ca}
        ck = {}
        if e_c_o:
            ck = {"wb_min": calib_wb_min, "wb_steps": calib_wb_steps, "max_flyash_frac": calib_max_flyash_frac, "max_ggbs_frac": calib_max_ggbs_frac, "scm_step": calib_scm_step, "fine_fraction_override": c_ff}
            st.info("Developer calibration overrides are enabled.", icon="🛠️")
            
        i = {"grade": grade, "exposure": exposure, "cement_choice": cement_choice, "nom_max": nom_max, "agg_shape": agg_shape, "target_slump": target_slump, "use_sp": use_sp, "optimize_cost": optimize_cost, "qc_level": qc_level, "fine_zone": fine_zone, "material_props": mp, "purpose": purpose, "enable_purpose_optimization": enable_purpose_optimization, "purpose_weights": purpose_weights, "optimize_for": optimize_for, "calibration_kwargs": ck}

        if st.session_state.user_text_input.strip():
            with st.spinner("🤖 Parsing your request..."):
                i, msgs, _ = ap(st.session_state.user_text_input, i, ullm=st.session_state.get('use_llm_parser', False))
            if msgs: st.info(" ".join(msgs), icon="💡")
            
            mf = [f for f in C.CHR if i.get(f) is None]
            if mf:
                st.session_state.clarification_needed = True
                st.session_state.final_inputs = i; st.session_state.missing_fields = mf
                st.session_state.run_generation_manual = False
            else:
                st.session_state.run_generation_manual = True
                st.session_state.final_inputs = i
        else:
            st.session_state.run_generation_manual = True
            st.session_state.final_inputs = i

    if st.session_state.get('clarification_needed', False):
        st.markdown("---"); st.warning("Your request is missing some details. Please confirm the following to continue.", icon="🤔")
        with st.form("clarification_form"):
            st.subheader("Please Clarify Your Requirements")
            ci, mf_l = st.session_state.final_inputs, st.session_state.missing_fields
            CLAR_W = {"grade": lambda v: st.selectbox("Concrete Grade", list(C.GS.keys()), index=list(C.GS.keys()).index(v) if v in C.GS else 4), "exposure": lambda v: st.selectbox("Exposure Condition", list(C.EWL.keys()), index=list(C.EWL.keys()).index(v) if v in C.EWL else 2), "target_slump": lambda v: st.slider("Target Slump (mm)", 25, 180, v if isinstance(v, int) else 100, 5), "cement_choice": lambda v: st.selectbox("Cement Type", C.CT, index=C.CT.index(v) if v in C.CT else 1), "nom_max": lambda v: st.selectbox("Nominal Max. Aggregate Size (mm)", [10, 12.5, 20, 40], index=[10, 12.5, 20, 40].index(v) if v in [10, 12.5, 20, 40] else 2)}
            cols = st.columns(min(len(mf_l), 3))
            for i, field in enumerate(mf_l):
                with cols[i % len(cols)]: ci[field] = CLAR_W[field](ci.get(field))

            if st.form_submit_button("✅ Confirm & Continue", use_container_width=True, type="primary"):
                st.session_state.final_inputs, st.session_state.clarification_needed, st.session_state.run_generation_manual = ci, False, True
                if 'results' in st.session_state: del st.session_state.results; st.rerun()

    if st.session_state.get('run_generation_manual', False):
        st.markdown("---"); progress_bar = st.progress(0.0, text="Initializing optimization...")
        rgl(inputs=st.session_state.final_inputs, emissions_df=edf, costs_df=cdf, ppd=ppd, st_p=progress_bar)
        st.session_state.run_generation_manual = False

    if 'results' in st.session_state and st.session_state.results["success"]:
        r, o_df, o_meta, b_df, b_meta, trace, i = st.session_state.results, st.session_state.results["opt_df"], st.session_state.results["opt_meta"], st.session_state.results["base_df"], st.session_state.results["base_meta"], st.session_state.results["trace"], st.session_state.results["inputs"]
        
        tab_names = ["📊 **Overview**", "🌱 **Optimized Mix**", "🏗️ **Baseline Mix**", "⚖️ **Trade-off Explorer**", "📋 **QA/QC & Gradation**", "📥 **Downloads & Reports**", "🔬 **Lab Calibration**"]
        try: default_index = tab_names.index(st.session_state.get("active_tab_name", tab_names[0]))
        except ValueError: default_index = 0
        st.session_state.active_tab_name = st.radio("Mix Report Navigation", options=tab_names, index=default_index, horizontal=True, label_visibility="collapsed", key="manual_tabs")
        
        if st.session_state.active_tab_name == "📊 **Overview**":
            co2_opt, cost_opt, co2_base, cost_base = o_meta["co2_total"], o_meta["cost_total"], b_meta["co2_total"], b_meta["cost_total"]
            reduction = (co2_base - co2_opt) / co2_base * 100 if co2_base > 0 else 0.0
            cost_savings = cost_base - cost_opt
            st.subheader("Performance At a Glance"); c1, c2, c3 = st.columns(3)
            c1.metric("🌱 CO₂ Reduction", f"{reduction:.1f}%", f"{co2_base - co2_opt:.1f} kg/m³ saved")
            c2.metric("💰 Cost Savings", f"₹{cost_savings:,.0f} / m³", f"{cost_savings/cost_base*100 if cost_base>0 else 0:.1f}% cheaper")
            c3.metric("♻️ SCM Content", f"{o_meta['scm_total_frac']*100:.0f}%", f"{b_meta['scm_total_frac']*100:.0f}% in baseline")
            if o_meta.get("purpose", "General") != "General":
                st.markdown("---"); cp1, cp2, cp3 = st.columns(3)
                cp1.metric("🛠️ Design Purpose", o_meta['purpose'])
                cp2.metric("🎯 Composite Score", f"{o_meta.get('composite_score', 0.0):.3f}")
                cp3.metric("⚠️ Purpose Penalty", f"{o_meta.get('purpose_penalty', 0.0):.2f}")
            st.markdown("---"); c1, c2 = st.columns(2)
            _poc(c1, "📊 Embodied Carbon (CO₂e)", "CO₂ (kg/m³)", co2_base, co2_opt, ['#D3D3D3', '#4CAF50'], '{:,.1f}')
            _poc(c2, "💵 Material Cost", "Cost (₹/m³)", cost_base, cost_opt, ['#D3D3D3', '#2196F3'], '₹{:,.0f}')

        elif st.session_state.active_tab_name == "🌱 **Optimized Mix**":
            dmd("🌱 Optimized Low-Carbon Mix Design", o_df, o_meta, i['exposure'])
            if st.toggle("📖 Show Step-by-Step IS Calculation", key="toggle_walkthrough_tab2"): d_c_w(o_meta)

        elif st.session_state.active_tab_name == "🏗️ **Baseline Mix**":
            dmd("🏗️ Standard OPC Baseline Mix Design", b_df, b_meta, i['exposure'])

        elif st.session_state.active_tab_name == "⚖️ **Trade-off Explorer**":
            st.header("Cost vs. Carbon Trade-off Analysis"); st.markdown("This chart displays all IS-code compliant mixes found by the optimizer. The blue line represents the **Pareto Front**—the set of most efficient mixes where you can't improve one objective (e.g., lower CO₂) without worsening the other (e.g., increasing cost).")
            if trace:
                trace_df = pd.DataFrame(trace)
                f_mixes = trace_df[trace_df['feasible']].copy()
                if not f_mixes.empty:
                    p_df = p_f(f_mixes, x_col="cost", y_col="co2")
                    if not p_df.empty:
                        alpha = st.slider("Prioritize Sustainability (CO₂) ↔ Cost", min_value=0.0, max_value=1.0, value=st.session_state.get("pareto_slider_alpha", 0.5), step=0.05, key="pareto_slider_alpha")
                        p_df_n = p_df.copy(); cost_min, cost_max, co2_min, co2_max = p_df_n['cost'].min(), p_df_n['cost'].max(), p_df_n['co2'].min(), p_df_n['co2'].max()
                        p_df_n['norm_cost'] = 0.0 if (cost_max - cost_min) == 0 else (p_df_n['cost'] - cost_min) / (cost_max - cost_min)
                        p_df_n['norm_co2'] = 0.0 if (co2_max - co2_min) == 0 else (p_df_n['co2'] - co2_min) / (co2_max - co2_min)
                        p_df_n['score'] = alpha * p_df_n['norm_co2'] + (1 - alpha) * p_df_n['norm_cost']
                        bcm = p_df_n.loc[p_df_n['score'].idxmin()]

                        fig, ax = plt.subplots(figsize=(10, 6))
                        ax.scatter(f_mixes["cost"], f_mixes["co2"], color='grey', alpha=0.5, label='All Feasible Mixes', zorder=1)
                        p_df_s = p_df.sort_values(by="cost"); ax.plot(p_df_s["cost"], p_df_s["co2"], '-o', color='blue', label='Pareto Front (Efficient Mixes)', linewidth=2, zorder=2)
                        o_l = f"Composite Score ({i['purpose']})" if i.get('enable_purpose_optimization', False) and i.get('purpose', 'General') != 'General' else i.get('optimize_for', 'CO₂ Emissions')
                        ax.plot(o_meta['cost_total'], o_meta['co2_total'], '*', markersize=15, color='red', label=f'Chosen Mix ({o_l})', zorder=3)
                        ax.plot(bcm['cost'], bcm['co2'], 'D', markersize=10, color='green', label='Best Compromise (from slider)', zorder=3)
                        ax.set_xlabel("Material Cost (₹/m³)"); ax.set_ylabel("Embodied Carbon (kg CO₂e / m³)"); ax.set_title("Pareto Front of Feasible Concrete Mixes"); ax.grid(True, linestyle='--', alpha=0.6); ax.legend()
                        st.pyplot(fig)

                        st.markdown("---"); st.subheader("Details of Selected 'Best Compromise' Mix")
                        c1, c2, c3 = st.columns(3)
                        c1.metric("💰 Cost", f"₹{bcm['cost']:.0f} / m³"); c2.metric("🌱 CO₂", f"{bcm['co2']:.1f} kg / m³"); c3.metric("💧 Water/Binder Ratio", f"{bcm['wb']:.3f}")
                        fcm = trace_df[(trace_df['cost'] == bcm['cost']) & (trace_df['co2'] == bcm['co2'])].iloc[0]
                        if 'composite_score' in fcm and not pd.isna(fcm['composite_score']):
                            c4, c5 = st.columns(2); c4.metric("⚠️ Purpose Penalty", f"{fcm['purpose_penalty']:.2f}"); c5.metric("🎯 Composite Score", f"{fcm['composite_score']:.3f}")
                    else: st.info("No Pareto front could be determined from the feasible mixes.", icon="ℹ️")
                else: st.warning("No feasible mixes were found by the optimizer, so no trade-off plot can be generated.", icon="⚠️")
            else: st.error("Optimizer trace data is missing.", icon="❌")

        elif st.session_state.active_tab_name == "📋 **QA/QC & Gradation**":
            st.header("Quality Assurance & Sieve Analysis")
            sfd = "Sieve_mm,PercentPassing\n4.75,95\n2.36,80\n1.18,60\n0.600,40\n0.300,15\n0.150,5"; scd = "Sieve_mm,PercentPassing\n40.0,100\n20.0,98\n10.0,40\n4.75,5"
            f_csv, c_csv = st.session_state.get('fine_csv'), st.session_state.get('coarse_csv')
            col1, col2 = st.columns(2)
            with col1:
                st.subheader("Fine Aggregate Gradation")
                if f_csv is not None:
                    try: f_csv.seek(0); df_f = pd.read_csv(f_csv); ok_fa, msgs_fa = (lambda df, zone: (True, [f"Fine aggregate conforms to IS 383 for {zone}."]) if all(r['PercentPassing'].iloc[0] >= C.FAZL[zone][s][0] and r['PercentPassing'].iloc[0] <= C.FAZL[zone][s][1] for s in C.FAZL[zone] if not (r:=df.loc[df["Sieve_mm"].astype(str) == s]).empty) else (False, [f"Sieve {s} mm: {float(r['PercentPassing'].iloc[0]):.1f}% passing is outside {C.FAZL[zone][s][0]}-{C.FAZL[zone][s][1]}%." for s in C.FAZL[zone] if not (r:=df.loc[df["Sieve_mm"].astype(str) == s]).empty and not (C.FAZL[zone][s][0] <= float(r['PercentPassing'].iloc[0]) <= C.FAZL[zone][s][1])] + [f"Missing sieve size: {s} mm." for s in C.FAZL[zone] if df.loc[df["Sieve_mm"].astype(str) == s].empty]))(df_f, i.get("fine_zone", "Zone II"))
                    except Exception as e: ok_fa, msgs_fa = False, [f"Error processing Fine Aggregate CSV: {e}"]
                    if ok_fa: st.success(msgs_fa[0], icon="✅")
                    else: [st.error(m, icon="❌") for m in msgs_fa]
                    st.dataframe(df_f, use_container_width=True)
                else: st.info("Upload a Fine Aggregate CSV in the advanced input area to perform a gradation check against IS 383.", icon="ℹ️"); st.download_button("Download Sample Fine Agg. CSV", sfd, "sample_fine_aggregate.csv", "text/csv")
            with col2:
                st.subheader("Coarse Aggregate Gradation")
                if c_csv is not None:
                    try: c_csv.seek(0); df_c = pd.read_csv(c_csv); ok_ca, msgs_ca = (lambda df, nm: (True, [f"Coarse aggregate conforms to IS 383 for {nm} mm graded aggregate."]) if all(r['PercentPassing'].iloc[0] >= C.CL[nm][s][0] and r['PercentPassing'].iloc[0] <= C.CL[nm][s][1] for s in C.CL[nm] if not (r:=df.loc[df["Sieve_mm"].astype(str) == s]).empty) else (False, [f"Sieve {s} mm: {float(r['PercentPassing'].iloc[0]):.1f}% passing is outside {C.CL[nm][s][0]}-{C.CL[nm][s][1]}%." for s in C.CL[nm] if not (r:=df.loc[df["Sieve_mm"].astype(str) == s]).empty and not (C.CL[nm][s][0] <= float(r['PercentPassing'].iloc[0]) <= C.CL[nm][s][1])] + [f"Missing sieve size: {s} mm." for s in C.CL[nm] if df.loc[df["Sieve_mm"].astype(str) == s].empty]))(df_c, int(i["nom_max"]))
                    except Exception as e: ok_ca, msgs_ca = False, [f"Error processing Coarse Aggregate CSV: {e}"]
                    if ok_ca: st.success(msgs_ca[0], icon="✅")
                    else: [st.error(m, icon="❌") for m in msgs_ca]
                    st.dataframe(df_c, use_container_width=True)
                else: st.info("Upload a Coarse Aggregate CSV in the advanced input area to perform a gradation check against IS 383.", icon="ℹ️"); st.download_button("Download Sample Coarse Agg. CSV", scd, "sample_coarse_aggregate.csv", "text/csv")
            st.markdown("---")
            with st.expander("📖 View Step-by-Step Calculation Walkthrough"): d_c_w(o_meta)
            with st.expander("🔬 View Optimizer Trace (Advanced)"):
                if trace:
                    tdf = pd.DataFrame(trace); st.dataframe(tdf.style.apply(lambda s: ['background-color: #e8f5e9; color: #155724; text-align: center;' if v else 'background-color: #ffebee; color: #721c24; text-align: center;' for v in s], subset=['feasible']).format({"feasible": lambda v: "✅" if v else "❌", "wb": "{:.3f}", "flyash_frac": "{:.2f}", "ggbs_frac": "{:.2f}", "co2": "{:.1f}", "cost": "{:.1f}", "purpose_penalty": "{:.2f}", "composite_score": "{:.4f}", "norm_co2": "{:.3f}", "norm_cost": "{:.3f}", "norm_purpose": "{:.3f}"}), use_container_width=True)
                    st.markdown("#### CO₂ vs. Cost of All Candidate Mixes")
                    fig, ax = plt.subplots(); ax.scatter(tdf["cost"], tdf["co2"], c=["#4CAF50" if f else "#F44336" for f in tdf["feasible"]], alpha=0.6)
                    ax.set_xlabel("Material Cost (₹/m³)"); ax.set_ylabel("Embodied Carbon (kg CO₂e/m³)"); ax.grid(True, linestyle='--', alpha=0.6); st.pyplot(fig)
                else: st.info("Trace not available.")

        elif st.session_state.active_tab_name == "📥 **Downloads & Reports**":
            st.header("Download Reports"); excel_buffer = BytesIO()
            with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
                o_df.to_excel(writer, sheet_name="Optimized_Mix", index=False); b_df.to_excel(writer, sheet_name="Baseline_Mix", index=False)
                pd.DataFrame([o_meta]).T.to_excel(writer, sheet_name="Optimized_Meta"); pd.DataFrame([b_meta]).T.to_excel(writer, sheet_name="Baseline_Meta")
                if trace: pd.DataFrame(trace).to_excel(writer, sheet_name="Optimizer_Trace", index=False)
            excel_buffer.seek(0)

            pdf_buffer = BytesIO(); doc = SimpleDocTemplate(pdf_buffer, pagesize=(8.5*inch, 11*inch)); styles = getSampleStyleSheet()
            summary_data = [["Metric", "Optimized Mix", "Baseline Mix"], ["CO₂ (kg/m³)", f"{o_meta['co2_total']:.1f}", f"{b_meta['co2_total']:.1f}"], ["Cost (₹/m³)", f"₹{o_meta['cost_total']:,.2f}", f"₹{b_meta['cost_total']:,.2f}"], ["w/b Ratio", f"{o_meta['w_b']:.3f}", f"{b_meta['w_b']:.3f}"], ["Binder (kg/m³)", f"{o_meta['cementitious']:.1f}", f"{b_meta['cementitious']:.1f}"], ["Purpose", f"{o_meta.get('purpose', 'N/A')}", f"{b_meta.get('purpose', 'N/A')}"], ["Composite Score", f"{o_meta.get('composite_score', 'N/A'):.3f}" if 'composite_score' in o_meta and not pd.isna(o_meta['composite_score']) else "N/A", "N/A"]]
            summary_table = Table(summary_data, hAlign='LEFT', colWidths=[2*inch, 1.5*inch, 1.5*inch]); summary_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.lightgrey)]))
            opt_data_pdf = [o_df.columns.values.tolist()] + o_df.applymap(lambda x: f'{x:.2f}' if isinstance(x, float) else x).values.tolist()
            opt_table = Table(opt_data_pdf, hAlign='LEFT'); opt_table.setStyle(TableStyle([('GRID', (0,0), (-1,-1), 1, colors.black), ('BACKGROUND', (0,0), (-1,0), colors.palegreen)]))
            story = [Paragraph("CivilGPT Sustainable Mix Report", styles['h1']), Spacer(1, 0.2*inch), Paragraph(f"Design for <b>{i['grade']} / {i['exposure']} Exposure</b>", styles['h2']), summary_table, Spacer(1, 0.2*inch), Paragraph("Optimized Mix Proportions (kg/m³)", styles['h2']), opt_table]; doc.build(story); pdf_buffer.seek(0)

            d1, d2 = st.columns(2)
            with d1: st.download_button("📄 Download PDF Report", data=pdf_buffer.getvalue(), file_name="CivilGPT_Report.pdf", mime="application/pdf", use_container_width=True); st.download_button("📈 Download Excel Report", data=excel_buffer.getvalue(), file_name="CivilGPT_Mix_Designs.xlsx", mime="application/vnd.ms-excel", use_container_width=True)
            with d2: st.download_button("✔️ Optimized Mix (CSV)", data=o_df.to_csv(index=False).encode("utf-8"), file_name="optimized_mix.csv", mime="text/csv", use_container_width=True); st.download_button("✖️ Baseline Mix (CSV)", data=b_df.to_csv(index=False).encode("utf-8"), file_name="baseline_mix.csv", mime="text/csv", use_container_width=True)

        elif st.session_state.active_tab_name == "🔬 **Lab Calibration**":
            st.header("🔬 Lab Calibration Analysis"); l_csv = st.session_state.get('lab_csv')
            if l_csv is not None:
                try:
                    l_csv.seek(0); l_r_df = pd.read_csv(l_csv); c_df, e_m = rlc(l_r_df)
                    if c_df is not None and not c_df.empty:
                        st.subheader("Error Metrics"); m1, m2, m3 = st.columns(3)
                        m1.metric(label="Mean Absolute Error (MAE)", value=f"{e_m['Mean Absolute Error (MPa)']:.2f} MPa")
                        m2.metric(label="Root Mean Squared Error (RMSE)", value=f"{e_m['Root Mean Squared Error (MPa)']:.2f} MPa")
                        m3.metric(label="Mean Bias (Over/Under-prediction)", value=f"{e_m['Mean Bias (MPa)']:.2f} MPa")
                        st.markdown("---"); st.subheader("Comparison: Lab vs. Predicted Target Strength")
                        st.dataframe(c_df.style.format({"Lab Strength (MPa)": "{:.2f}", "Predicted Target Strength (MPa)": "{:.2f}", "Error (MPa)": "{:+.2f}"}), use_container_width=True)
                        st.subheader("Prediction Accuracy Scatter Plot"); fig, ax = plt.subplots()
                        ax.scatter(c_df["Lab Strength (MPa)"], c_df["Predicted Target Strength (MPa)"], alpha=0.7, label="Data Points")
                        lims = [np.min([ax.get_xlim(), ax.get_ylim()]), np.max([ax.get_xlim(), ax.get_ylim()])]
                        ax.plot(lims, lims, 'r--', alpha=0.75, zorder=0, label="Perfect Prediction (y=x)")
                        ax.set_xlabel("Actual Lab Strength (MPa)"); ax.set_ylabel("Predicted Target Strength (MPa)"); ax.set_title("Lab Strength vs. Predicted Target Strength"); ax.legend(); ax.grid(True); st.pyplot(fig)
                    else: st.warning("Could not process the uploaded lab data CSV. Please check the file format, column names, and ensure it contains valid data.", icon="⚠️")
                except Exception as e: st.error(f"Failed to read or process the lab data CSV file: {e}", icon="💥")
            else: st.info("Upload a lab data CSV in the **Advanced Manual Input** section to automatically compare CivilGPT's target strength calculations against your real-world results.", icon="ℹ️")

    elif not st.session_state.get('clarification_needed'):
        st.info("Enter your concrete requirements in the prompt box above, or expand the **Advanced Manual Input** section to specify parameters.", icon="👆")
        st.markdown("---"); st.subheader("How It Works")
        st.markdown("""
        1. **Input Requirements**: Describe your needs or use manual inputs.
        2. **Select Purpose**: Choose design purpose (e.g., 'Slab') for specific optimization.
        3. **IS Code Compliance**: Generates candidate mixes, adhering to **IS 10262** and **IS 456**.
        4. **Sustainability Optimization**: Calculates CO₂e, cost, and 'Purpose-Fit'.
        5. **Best Mix Selection**: Presents the mix with the best **composite score** (or lowest CO₂/cost) vs. a standard OPC baseline.""")

# ==============================================================================
# PART 7: MAIN APP CONTROLLER
# ==============================================================================

def main():
    st.set_page_config(page_title="CivilGPT - Sustainable Concrete Mix Designer", page_icon="🧱", layout="wide")
    st.markdown("""
    <style>
    .main .block-container { padding-top: 2rem; padding-bottom: 2rem; padding-left: 5rem; padding-right: 5rem; }
    .st-emotion-cache-1y4p8pa { max-width: 100%; }
    .stTextArea [data-baseweb=base-input] { border-color: #4A90E2; box-shadow: 0 0 5px #4A90E2; }
    [data-testid="chat-message-container"] { border-radius: 8px; padding: 0.75rem; margin-bottom: 0.5rem; }
    [data-testid="chat-message-container"] [data-testid="stMarkdown"] p { line-height: 1.6; }
    .mode-card { background-color: #1E1E1E; border-radius: 8px; padding: 15px; margin-bottom: 10px; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.5); border: 1px solid #333333; transition: all 0.3s; }
    .mode-card:hover { box-shadow: 0 6px 12px rgba(0, 0, 0, 0.7); border-color: #4A90E2; }
    .mode-card h4 { color: #FFFFFF; margin-top: 0; margin-bottom: 5px; }
    .mode-card p { color: #CCCCCC; font-size: 0.85em; margin-bottom: 10px; }
    [data-testid="stSidebarContent"] > div:first-child { padding-bottom: 0rem; }
    </style>
    """, unsafe_allow_html=True)

    if "chat_mode" not in st.session_state: st.session_state.chat_mode = False
    if "active_tab_name" not in st.session_state: st.session_state.active_tab_name = "📊 **Overview**"
    if "chat_history" not in st.session_state: st.session_state.chat_history = []
    if "chat_inputs" not in st.session_state: st.session_state.chat_inputs = {}
    if "chat_results_displayed" not in st.session_state: st.session_state.chat_results_displayed = False
    if "run_chat_generation" not in st.session_state: st.session_state.run_chat_generation = False
    if "manual_tabs" not in st.session_state: st.session_state.manual_tabs = "📊 **Overview**"
        
    ppd = lpp()

    st.sidebar.title("Mode Selection")
    if "llm_init_message" in st.session_state:
        msg_type, msg_content = st.session_state.pop("llm_init_message")
        if msg_type == "success": st.sidebar.success(msg_content, icon="🤖")
        elif msg_type == "info": st.sidebar.info(msg_content, icon="ℹ️")
        elif msg_type == "warning": st.sidebar.warning(msg_content, icon="⚠️")

    llm_is_ready = st.session_state.get("llm_enabled", False)
    
    with st.sidebar:
        is_chat_mode = st.session_state.chat_mode
        card_title, card_desc, card_icon = ("🤖 CivilGPT Chat Mode", "Converse with the AI to define mix requirements.", "💬") if is_chat_mode else ("⚙️ Manual/Prompt Mode", "Use the detailed input sections to define your mix.", "📝")
        st.markdown(f"""<div class="mode-card"><h4 style='display: flex; align-items: center;'><span style='font-size: 1.2em; margin-right: 10px;'>{card_icon}</span>{card_title}</h4><p>{card_desc}</p></div>""", unsafe_allow_html=True)
        
        chat_mode = st.toggle(f"Switch to {'Manual' if is_chat_mode else 'Chat'} Mode", value=st.session_state.get("chat_mode") if llm_is_ready else False, key="chat_mode_toggle_functional", help="Toggle to switch between conversational and manual input interfaces." if llm_is_ready else "Chat Mode requires a valid GROQ_API_KEY.", disabled=not llm_is_ready, label_visibility="collapsed")
        st.session_state.chat_mode = chat_mode
        
        if not chat_mode and llm_is_ready:
            st.markdown("---")
            st.checkbox("Use Groq LLM Parser for Text Prompt", value=False, key="use_llm_parser", help="Use the LLM to automatically extract parameters from the text area above.")

    if chat_mode:
        if st.sidebar.button("🧹 Clear Chat History", use_container_width=True):
            st.session_state.chat_history = []; st.session_state.chat_inputs = {}; st.session_state.chat_results_displayed = False
            if "results" in st.session_state: del st.session_state.results; st.rerun()
        st.sidebar.markdown("---")

    m_df, e_df, c_df = ld(st.session_state.get("materials_csv"), st.session_state.get("emissions_csv"), st.session_state.get("cost_csv"))

    if st.session_state.get('run_chat_generation', False):
        st.session_state.run_chat_generation = False
        c_i, mp = st.session_state.chat_inputs, {'sg_fa': 2.65, 'moisture_fa': 1.0, 'sg_ca': 2.70, 'moisture_ca': 0.5}
        i = {"grade": "M30", "exposure": "Severe", "cement_choice": "OPC 43", "nom_max": 20, "agg_shape": "Angular (baseline)", "target_slump": 125, "use_sp": True, "optimize_cost": False, "qc_level": "Good", "fine_zone": "Zone II", "material_props": mp, "purpose": "General", "enable_purpose_optimization": False, "purpose_weights": ppd['General']['weights'], "optimize_for": "CO₂ Emissions", "calibration_kwargs": {}, **c_i}
        i["optimize_cost"] = (i.get("optimize_for") == "Cost"); i["enable_purpose_optimization"] = (i.get("purpose") != 'General')
        if i["enable_purpose_optimization"]: i["purpose_weights"] = ppd.get(i["purpose"], {}).get('weights', ppd['General']['weights'])
        st.session_state.final_inputs = i
        with st.spinner("⚙️ Running IS-code calculations and optimizing..."):
            rgl(inputs=i, emissions_df=e_df, costs_df=c_df, ppd=ppd, st_p=None)

    if chat_mode: rc_i(ppd)
    else: rmi(ppd, m_df, e_df, c_df)


if __name__ == "__main__":
    main()

All functionality preserved, code compressed safely.
