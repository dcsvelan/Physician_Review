# app.py — FULL MERGED VERSION WITH SEPSIS BUNDLE MODULE + CLINICIAN APPROVAL
# PART 1 / 7 — Imports, Environment Setup, Drive Init, Auth System, Header

import streamlit as st
import requests
import random
import pytesseract
from PIL import Image
import io
import re
import concurrent.futures
import json
import os
import streamlit.components.v1 as components
from dotenv import load_dotenv
from langchain_groq import ChatGroq
import speech_recognition as sr
from deep_translator import GoogleTranslator
import datetime

# Load environment variables
load_dotenv()
os.environ["GROQ_API_KEY"] = os.getenv("GROQ_API_KEY")

# Create LLM Object (your exact original configuration)
llm = ChatGroq(
    model="qwen/qwen3-32b",
    temperature=0
)

###############################################
# GOOGLE DRIVE INTEGRATION (your original code)
###############################################
from pydrive.auth import GoogleAuth
from pydrive.drive import GoogleDrive

def init_drive():
    gauth = GoogleAuth()
    gauth.LoadCredentialsFile("mycreds.txt")
    if gauth.credentials is None:
        gauth.LocalWebserverAuth()
    elif gauth.access_token_expired:
        gauth.Refresh()
    else:
        gauth.Authorize()
    gauth.SaveCredentialsFile("mycreds.txt")
    return GoogleDrive(gauth)

drive = init_drive()

USERS_JSON_FILE_ID = st.secrets.get("users_json_file_id", None)
APPROVALS_JSON_FILE_ID = st.secrets.get("approvals_json_file_id", None)

USER_DATA_FILE = "users.json"
APPROVALS_FILE = "approvals.json"

###############################################
# USER / APPROVAL LOADING + SAVING
###############################################
def load_users():
    global USERS_JSON_FILE_ID
    try:
        if USERS_JSON_FILE_ID:
            file = drive.CreateFile({'id': USERS_JSON_FILE_ID})
            file.GetContentFile(USER_DATA_FILE)
        elif os.path.exists(USER_DATA_FILE):
            pass
        else:
            return {}
        with open(USER_DATA_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        st.error(f"Error loading users.json: {e}")
        return {}

def save_users(users):
    global USERS_JSON_FILE_ID
    with open(USER_DATA_FILE, "w") as f:
        json.dump(users, f, indent=4)
    try:
        if USERS_JSON_FILE_ID:
            file_drive = drive.CreateFile({'id': USERS_JSON_FILE_ID})
        else:
            file_list = drive.ListFile({
                'q': f"title='{USER_DATA_FILE}' and trashed=false"
            }).GetList()
            if file_list:
                file_drive = file_list[0]
                USERS_JSON_FILE_ID = file_drive['id']
            else:
                file_drive = drive.CreateFile({'title': USER_DATA_FILE})
        file_drive.SetContentFile(USER_DATA_FILE)
        file_drive.Upload()
        st.success("User data saved.")
    except Exception as e:
        st.error(f"Error saving user data: {e}")

def load_approvals():
    global APPROVALS_JSON_FILE_ID
    try:
        if APPROVALS_JSON_FILE_ID:
            file = drive.CreateFile({'id': APPROVALS_JSON_FILE_ID})
            file.GetContentFile(APPROVALS_FILE)
        elif os.path.exists(APPROVALS_FILE):
            pass
        else:
            return []
        with open(APPROVALS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        st.warning(f"Approvals load warning: {e}")
        return []

def save_approval_record(record):
    global APPROVALS_JSON_FILE_ID
    approvals = load_approvals() or []
    approvals.append(record)

    with open(APPROVALS_FILE, "w") as f:
        json.dump(approvals, f, indent=2)

    try:
        if APPROVALS_JSON_FILE_ID:
            file_drive = drive.CreateFile({'id': APPROVALS_JSON_FILE_ID})
        else:
            file_list = drive.ListFile({
                'q': f"title='{APPROVALS_FILE}' and trashed=false"
            }).GetList()
            if file_list:
                file_drive = file_list[0]
                APPROVALS_JSON_FILE_ID = file_drive['id']
            else:
                file_drive = drive.CreateFile({'title': APPROVALS_FILE})

        file_drive.SetContentFile(APPROVALS_FILE)
        file_drive.Upload()
        st.success("Approval recorded and uploaded.")
    except Exception as e:
        st.warning(f"Could not upload approvals to Drive: {e}")

###############################################
# VALIDATION HELPERS (original code)
###############################################
def is_valid_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email)

def is_valid_phone(phone):
    pattern = r'^\+\d{10,15}$'
    return re.match(pattern, phone)

def is_valid_address(address):
    if ',' not in address:
        return False
    parts = address.split(',')
    if len(parts) < 2:
        return False
    city = parts[0].strip()
    country = parts[1].strip()
    return bool(city) and bool(country)

###############################################
# AUTHENTICATION (original code)
###############################################
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
    st.session_state.login_attempted = False

def force_refresh_users_from_drive():
    global USERS_JSON_FILE_ID
    try:
        if USERS_JSON_FILE_ID:
            file = drive.CreateFile({'id': USERS_JSON_FILE_ID})
            if os.path.exists(USER_DATA_FILE):
                os.remove(USER_DATA_FILE)
            file.GetContentFile(USER_DATA_FILE)
            with open(USER_DATA_FILE, "r") as f:
                return json.load(f)
        else:
            file_list = drive.ListFile({
                'q': f"title='{USER_DATA_FILE}' and trashed=false"
            }).GetList()
            if file_list:
                file_drive = file_list[0]
                USERS_JSON_FILE_ID = file_drive['id']
                if os.path.exists(USER_DATA_FILE):
                    os.remove(USER_DATA_FILE)
                file_drive.GetContentFile(USER_DATA_FILE)
                with open(USER_DATA_FILE, "r") as f:
                    return json.load(f)
    except:
        pass

    try:
        if os.path.exists(USER_DATA_FILE):
            with open(USER_DATA_FILE, "r") as f:
                return json.load(f)
    except:
        pass

    return {}

def attempt_auto_login():
    current_users = force_refresh_users_from_drive()
    default_username = "dcs1"
    default_password = "DCS1"
    st.sidebar.write(f"Debug - Available users: {list(current_users.keys())}")
    if default_username not in current_users:
        st.sidebar.error("🚫 User 'dcs1' not found.")
        return False
    if current_users[default_username]["password"] == default_password:
        st.session_state.authenticated = True
        st.session_state.username = default_username
        return True
    else:
        st.sidebar.error("🚫 Invalid credentials!")
        return False

def register():
    st.sidebar.title("📝 User Registration")
    new_username = st.sidebar.text_input("Username", key="register_username")
    new_password = st.sidebar.text_input("Password", type="password", key="register_password")
    new_occupation = st.sidebar.text_input("Occupation", key="register_occupation")
    new_email = st.sidebar.text_input("Email", key="register_email")
    new_phone = st.sidebar.text_input("Phone (+91)", key="register_phone")
    new_address = st.sidebar.text_area("Address (City, Country)", key="register_address")

    if st.sidebar.button("Register"):
        current_users = force_refresh_users_from_drive()

        if not new_username or not new_password or not new_email or not new_phone or not new_address:
            st.sidebar.error("All fields required!")
            return

        if new_username in current_users:
            st.sidebar.error("Username exists.")
            return

        if not is_valid_email(new_email):
            st.sidebar.error("Invalid email.")
            return

        if not is_valid_phone(new_phone):
            st.sidebar.error("Invalid phone number (use +xxxxxxxx).")
            return

        if not is_valid_address(new_address):
            st.sidebar.error("Address must be 'City, Country'.")
            return

        current_users[new_username] = {
            "password": new_password,
            "occupation": new_occupation,
            "email": new_email,
            "phone": new_phone,
            "address": new_address
        }
        save_users(current_users)
        st.sidebar.success("Registration successful!")

def login():
    st.sidebar.title("🔐 User Login")
    username = st.sidebar.text_input("Username", value="dcs1")
    password = st.sidebar.text_input("Password", value="DCS1", type="password")

    if not st.session_state.login_attempted:
        st.session_state.login_attempted = True
        current_users = force_refresh_users_from_drive()
        if username not in current_users:
            st.sidebar.error("User not found.")
        elif current_users[username]["password"] == password:
            st.session_state.authenticated = True
            st.session_state.username = username
        else:
            st.sidebar.error("Invalid credentials.")
    elif st.sidebar.button("Login"):
        current_users = force_refresh_users_from_drive()
        if username not in current_users:
            st.sidebar.error("User not found.")
        elif current_users[username]["password"] == password:
            st.session_state.authenticated = True
            st.session_state.username = username
        else:
            st.sidebar.error("Invalid credentials.")

def logout():
    st.session_state.authenticated = False
    st.session_state.login_attempted = False
    st.sidebar.warning("Logged out. Refresh page.")

# Auto login attempt
if not st.session_state.authenticated:
    if not st.session_state.login_attempted:
        attempt_auto_login()
    if not st.session_state.authenticated:
        register()
        login()
        st.stop()

# Hide sidebar on login
st.markdown("""
<style>
[data-testid="stSidebar"] {display: none;}
</style>
""", unsafe_allow_html=True)

###############################################
# HEADER (your original UI)
###############################################
st.markdown("""
<div style='display: flex; justify-content: space-between; align-items: center;'>
    <span style='font-weight: bold; font-size: 14px;'>nrtyasri@gmail.com</span>
    <span style='font-weight: bold; font-size: 14px;'>dr.pathmini md coimbatore</span>
</div>
""", unsafe_allow_html=True)

###############################################
# >>> INSERTION POINT REACHED <<<
# NEXT: PART 2 WILL CONTAIN THE SEPSIS MODULE (FULL)
###############################################
# -------------------------
# PART 2 / 7 — SEPSIS BUNDLE TRIGGER MODULE
# Inserted immediately after header / auth (A1 placement)
# -------------------------

# Sepsis detection and High-Validity LLM prompt builder

def detect_sepsis_rule(vitals, labs, infection_flag):
    """
    Deterministic sepsis detection using high-validity rules:
    qSOFA, lactate, MAP, urine output, suspected infection.
    Returns (sepsis_suspected: bool, qsofa: int, reasons: list)
    """
    reasons = []
    rr = vitals.get("rr")
    sbp = vitals.get("sbp")
    dbp = vitals.get("dbp")
    gcs = vitals.get("gcs")
    urine_hr = labs.get("urine_output_hourly")
    lactate = labs.get("lactate")
    map_val = None
    if sbp is not None and dbp is not None:
        map_val = (sbp + 2 * dbp) / 3

    qsofa = 0
    if rr is not None and rr >= 22:
        qsofa += 1
        reasons.append(f"RR >=22 ({rr})")
    if sbp is not None and sbp <= 100:
        qsofa += 1
        reasons.append(f"SBP <=100 ({sbp})")
    if gcs is not None and gcs < 15:
        qsofa += 1
        reasons.append(f"GCS <15 ({gcs})")
    if lactate is not None and lactate >= 2:
        reasons.append(f"Lactate >=2 mmol/L ({lactate})")
    if map_val is not None and map_val < 65:
        reasons.append(f"MAP <65 ({map_val:.1f})")
    if urine_hr is not None and urine_hr < 0.5:
        reasons.append(f"Urine output <0.5 mL/kg/hr (reported {urine_hr})")

    sepsis_suspected = False
    # Criteria (sensitive, aligns with SSC high-validity triggers)
    if infection_flag and (qsofa >= 2 or (lactate is not None and lactate >= 2) or (map_val is not None and map_val < 65) or (urine_hr is not None and urine_hr < 0.5)):
        sepsis_suspected = True

    return sepsis_suspected, qsofa, reasons

def build_high_validity_prompt(snapshot, time_zero_iso):
    """
    Build the restricted Level-1 evidence prompt (minimal, precise) for the LLM.
    Returns a single string prompt.
    """
    prompt = f"""
You are an evidence-focused ICU consultant. Use ONLY high-validity Surviving Sepsis domains (SSC 2021 and Grade-1 evidence).
Do NOT provide speculative or low-evidence suggestions.

Patient snapshot (DO NOT invent values):
TIME_ZERO: {time_zero_iso}
Clinical snapshot: {json.dumps(snapshot, indent=0)}

Task:
1) State in one line: SEPSIS SUSPECTED: TRUE/FALSE and the primary reasons (qSOFA, lactate, MAP, urine).
2) Produce an ordered Hour-1 Bundle Plan (checklist) with explicit timestamps relative to TIME_ZERO for:
   - Culture collection (blood 2 sets, urine, ET if intubated, catheter tip if relevant) BEFORE antibiotics.
   - STAT lactate order + repeat lactate schedule (2-4 hours).
   - Immediate empirical antibiotic strategy tailored to MDR-risk (provide recommended regimen options and clear statement: 'Require clinician approval before ordering').
   - Fluid resuscitation plan (30 mL/kg crystalloid within 1 hour OR titration strategy for CKD/heart failure; give ml/kg and aliquot plan).
   - Vasopressor initiation strategy (norepinephrine first-line, MAP target >=65; when to add vasopressin/dobutamine).
   - Source control urgency and target (within 12 hours for obstructive urosepsis/abscesses; specify recommended action).
   - Monitoring & escalation criteria (lactate clearance failure, persistent MAP <65, urine <0.5, rising vasopressor need) with explicit triggers.

3) For each checklist item provide brief evidence tags (e.g., "SSC 2021; Level 1A" or "IDSA Grade 1A") — two words max.

4) Output format: Plain text human-readable plan followed by a compact JSON block marked by lines:
---JSON-OUTPUT-START---
{{
 "sepsisSuspected": <true|false>,
 "timeZero": "{time_zero_iso}",
 "qsofa": <int>,
 "reasons": [...],
 "priorityActions": [ "action 1", "action 2", ... ],
 "recommendedEmpiricAntibiotics": [ "option 1", "option 2" ],
 "fluidsPlan": "text",
 "lactatePlan": "text",
 "vasopressorPlan": "text",
 "sourceControl": "text",
 "clinicianActions": [ "Approve antibiotics", "Order source-control within 12h", ... ]
}}
---JSON-OUTPUT-END---

Constraints:
- Keep the human-readable checklist concise (max 14 lines).
- JSON must be valid.
- Emphasize "cultures before antibiotics" clearly and early.
- Include a single-line clinician safety sentence: "All antibiotic orders require clinician approval."
End.
"""
    return prompt

# UI: render top-of-page sepsis module
def render_sepsis_module():
    st.header("🧭 Sepsis Bundle Trigger — Hour-1 (High-Validity)")
    st.caption("Use this tool at bedside to create an evidence-tagged Hour-1 plan. LLM suggestions require clinician approval.")

    with st.form(key="sepsis_form"):
        st.subheader("Patient basic snapshot")
        patient_id = st.text_input("Patient ID / MRN", value="")
        age = st.number_input("Age (years)", value=65, min_value=0, max_value=120, step=1)
        weight = st.number_input("Weight (kg)", value=70.0, min_value=20.0, max_value=300.0, step=0.5)
        infection_flag = st.checkbox("Suspected infection (clinical)", value=True)

        st.markdown("**Vitals**")
        col1, col2, col3 = st.columns(3)
        with col1:
            rr = st.number_input("Respiratory rate (breaths/min)", value=24)
            sbp = st.number_input("Systolic BP (mmHg)", value=90)
            dbp = st.number_input("Diastolic BP (mmHg)", value=60)
        with col2:
            hr = st.number_input("Heart rate (bpm)", value=110)
            gcs = st.number_input("GCS", value=13, min_value=3, max_value=15, step=1)
            spo2 = st.number_input("SpO2 (%)", value=92)
        with col3:
            temp = st.number_input("Temperature (°C)", value=38.0)
            urine_output = st.number_input("Urine output (mL/hour)", value=20.0)
        st.markdown("**Labs / Key parameters**")
        lactate = st.number_input("Lactate (mmol/L) - if available", value=2.5, step=0.1, format="%.2f")
        creat = st.number_input("Serum creatinine (mg/dL)", value=2.0, step=0.1, format="%.2f")
        fungal_risk = st.checkbox("High fungal risk (e.g., prolonged antibiotics/ICU)", value=False)
        mdr_risk = st.checkbox("High MDR/PDR risk (recent hospital, known colonization)", value=True)
        suspected_source = st.selectbox("Suspected source", ["Urinary (urosepsis)", "Lung / VAP", "Abdomen", "Line/CLABSI", "Unknown", "Other"])

        submit = st.form_submit_button("Run Sepsis Detection & Generate Hour-1 Plan")

    # On submit, run detection and LLM
    if submit:
        # Build structured snapshot
        vitals = {
            "rr": rr,
            "sbp": sbp,
            "dbp": dbp,
            "hr": hr,
            "gcs": gcs,
            "spo2": spo2,
            "temp": temp
        }
        # Estimate MAP if possible
        map_val = (sbp + 2 * dbp) / 3 if (sbp is not None and dbp is not None) else None
        labs = {
            "lactate": lactate,
            "creatinine": creat,
            "urine_output_hourly": (urine_output / weight) if weight and urine_output is not None else None
        }
        sepsis_suspected, qsofa, reasons = detect_sepsis_rule(vitals, labs, infection_flag)

        time_zero = datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

        # Render deterministic detection result
        st.markdown("### Detection Summary")
        st.write(f"- **Sepsis suspected:** {'YES' if sepsis_suspected else 'NO'}")
        st.write(f"- **qSOFA:** {qsofa}  {'; '.join(reasons) if reasons else ''}")
        if sepsis_suspected:
            st.warning("Sepsis suspected — generating Hour-1 evidence-based plan. Review and approve actions at bedside.")
        else:
            st.info("Sepsis not strongly suspected by high-validity rules. If clinical concern remains, follow local protocols.")

        # Build snapshot for LLM
        snapshot = {
            "patient_id": patient_id,
            "age": age,
            "weight": weight,
            "vitals": vitals,
            "map": map_val,
            "labs": labs,
            "suspected_source": suspected_source,
            "fungal_risk": fungal_risk,
            "mdr_risk": mdr_risk,
            "infection_flag": infection_flag
        }

        # Only call LLM if sepsis suspected
        if sepsis_suspected:
            with st.spinner("Generating Hour-1 bundle plan (LLM) — this may take a few seconds..."):
                prompt = build_high_validity_prompt(snapshot, time_zero)
                try:
                    # Use the same LLM invocation style used elsewhere in your app
                    llm_resp = llm.invoke([
                        {"role": "system", "content": "You are an evidence-based ICU consultant. Answer concisely and follow format."},
                        {"role": "user", "content": prompt}
                    ])
                    plan_text = llm_resp.content.strip()
                except Exception as e:
                    st.error(f"LLM invocation failed: {e}")
                    plan_text = "LLM invocation failed. Please run again or consult senior clinician."

            # Display human-readable plan and parse JSON block if present
            st.markdown("### Hour-1 Bundle — Human Readable Plan")
            st.code(plan_text, language="text")

            # Attempt to extract JSON block between markers
            json_block = None
            try:
                start_marker = "---JSON-OUTPUT-START---"
                end_marker = "---JSON-OUTPUT-END---"
                if start_marker in plan_text and end_marker in plan_text:
                    jtxt = plan_text.split(start_marker, 1)[1].split(end_marker, 1)[0].strip()
                    json_block = json.loads(jtxt)
                else:
                    # Try to find a JSON object in the tail
                    possible = plan_text.strip().splitlines()[-20:]
                    possible_txt = "\n".join(possible)
                    import re
                    m = re.search(r"\{[\s\S]*\}", possible_txt)
                    if m:
                        json_block = json.loads(m.group(0))
            except Exception as e:
                st.warning(f"Could not parse JSON from LLM output: {e}")

            # Buttons to download the plan and JSON
            download_txt = f"TIME_ZERO: {time_zero}\n\n{plan_text}"
            st.download_button("📥 Download Plan (text)", data=download_txt, file_name=f"sepsis_plan_{patient_id or 'patient'}_{time_zero}.txt")
            if json_block:
                st.download_button("📥 Download Plan (JSON)", data=json.dumps(json_block, indent=2), file_name=f"sepsis_plan_{patient_id or 'patient'}_{time_zero}.json", mime="application/json")
            else:
                # Offer to download the raw plan as .json fallback
                st.download_button("📥 Download Raw Plan (for audit)", data=json.dumps({"raw_plan": plan_text}), file_name=f"sepsis_plan_raw_{patient_id or 'patient'}_{time_zero}.json", mime="application/json")

            # Safety / clinician action checklist (explicit)
            st.markdown("### Clinician Safety Actions (REQUIRED)")
            st.markdown("- **DO NOT** auto-order restricted antibiotics from this UI. Review recommended empiric options and click the appropriate order in your EHR after clinician approval.")
            st.markdown("- **Obtain cultures BEFORE antibiotics** (blood 2 sets, urine, ET if intubated, catheter tip if applicable).")
            st.markdown("- **Order STAT lactate** and schedule recheck in 2–4 hours.")
            st.markdown("- **If source control required (e.g., obstructive urosepsis) contact relevant team for intervention within 12 hours.**")
            st.markdown("- Document TIME_ZERO in the medical record and the name of the clinician who approved the plan.")

            # Quick action links / copy-to-clipboard helpers
            try:
                import pyperclip
                can_copy = True
            except Exception:
                can_copy = False

            if can_copy and st.button("Copy checklist to clipboard"):
                try:
                    pyperclip.copy(download_txt)
                    st.success("Checklist copied to clipboard.")
                except Exception:
                    st.info("Copy to clipboard unavailable on server. Use Download Plan button.")

        else:
            st.info("No LLM plan generated since sepsis was not suspected by the high-validity rules. Use local judgment if clinical concern persists.")

# Immediately render the sepsis module at the top/home
render_sepsis_module()

# -------------------------
# End of PART 2 / 7
# -------------------------
# -------------------------
# PART 3 / 7 — Helper functions: RxNav, FDA lookups, OCR, translation, chat logic
# -------------------------

# ---------- RXNAV / DRUG INFO FETCHERS ----------
# Simple wrappers to query RxNav (open APIs) and FDA drug label endpoints.
# Replace base URLs / API keys as needed.

RXNAV_BASE = "https://rxnav.nlm.nih.gov/REST"
FDA_DRUG_LABEL_BASE = "https://api.fda.gov/drug/label.json"

def fetch_rxnav_by_name(drug_name):
    """
    Query RxNav to find concept unique identifiers (rxcui) given a drug name,
    then fetch medication information. Returns dict or None on failure.
    """
    try:
        # search for rxcui
        r = requests.get(f"{RXNAV_BASE}/rxcui.json", params={"name": drug_name, "search": 1}, timeout=10)
        data = r.json()
        if "idGroup" in data and "rxnormId" in data["idGroup"]:
            rxcui = data["idGroup"]["rxnormId"][0]
            # fetch properties
            r2 = requests.get(f"{RXNAV_BASE}/rxcui/{rxcui}/properties.json", timeout=10)
            props = r2.json().get("properties", {})
            return {"rxcui": rxcui, "properties": props}
        else:
            return None
    except Exception as e:
        st.warning(f"RxNav lookup failed: {e}")
        return None

def fetch_fda_label_by_drug(drug_name, limit=1):
    """
    Query openFDA drug label endpoint for adverse events / indications.
    (This uses the public openFDA API which has rate limits.)
    """
    try:
        params = {"search": f"openfda.brand_name:{drug_name}", "limit": limit}
        r = requests.get(FDA_DRUG_LABEL_BASE, params=params, timeout=10)
        j = r.json()
        results = j.get("results", [])
        if results:
            return results[0]
        return None
    except Exception as e:
        st.warning(f"FDA label fetch failed: {e}")
        return None

# ---------- OCR for image-based drug labels / prescriptions ----------
# Uses pytesseract (must be installed in environment).
def ocr_image_to_text(pil_image):
    """
    Convert PIL image to text using pytesseract.
    Returns text string.
    """
    try:
        text = pytesseract.image_to_string(pil_image)
        return text
    except Exception as e:
        st.warning(f"OCR failed: {e}")
        return ""

def extract_text_from_uploaded_file(uploaded_file):
    """
    If the user uploads an image or PDF, extract text.
    For PDFs we will attempt to read as image per page (simple approach).
    """
    try:
        content_type = uploaded_file.type
        if "image" in content_type:
            image = Image.open(uploaded_file)
            text = ocr_image_to_text(image)
            return text
        elif uploaded_file.name.lower().endswith(".pdf"):
            # rudimentary: convert first page to image via PIL (requires pdf2image in production)
            st.info("PDF uploaded — extracting first page text (simple).")
            try:
                from pdf2image import convert_from_bytes
                pages = convert_from_bytes(uploaded_file.read(), first_page=1, last_page=1)
                if pages:
                    return ocr_image_to_text(pages[0])
            except Exception as e:
                st.warning(f"PDF to image extraction requires pdf2image: {e}")
                return ""
        else:
            # assume text file
            raw = uploaded_file.getvalue().decode("utf-8", errors="ignore")
            return raw
    except Exception as e:
        st.warning(f"Failed reading uploaded file: {e}")
        return ""

# ---------- Translation (deep_translator) ----------
def translate_text_to_english(text, src_lang="auto"):
    """
    Uses deep_translator / GoogleTranslator wrapper to translate to English.
    """
    try:
        translated = GoogleTranslator(source=src_lang, target="english").translate(text)
        return translated
    except Exception as e:
        st.warning(f"Translation failed: {e}")
        return text

# ---------- Chat Assistant Core (wrap around your LLM) ----------
# The app earlier used a ChatGroq llm.invoke([...]) pattern.
# We'll provide a robust wrapper to call the LLM and cache results locally.

LLM_CACHE = {}

def call_llm_system_user(system_prompt, user_prompt, cache_key=None, max_tokens=2048):
    """
    Call the ChatGroq LLM in a simple wrapper using system and user roles.
    Returns the content text.
    """
    global LLM_CACHE
    try:
        if cache_key and cache_key in LLM_CACHE:
            return LLM_CACHE[cache_key]

        resp = llm.invoke([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ])
        content = getattr(resp, "content", "") or str(resp)
        if cache_key:
            LLM_CACHE[cache_key] = content
        return content
    except Exception as e:
        st.error(f"LLM call failed: {e}")
        return "LLM error: " + str(e)

# ---------- Chat history helper ----------
def append_chat_history(user, message, role="user"):
    """
    Append to a session chat history (simple list). Used by chat UI.
    """
    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []
    st.session_state["chat_history"].append({
        "time": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "user": user,
        "role": role,
        "message": message
    })

# ---------- Simple medication summary extractor ----------
def extract_medications_from_text(text):
    """
    Try to extract medication names using a naive regex heuristic.
    Returns list of candidate drug names.
    """
    # Very simple approach: capitalized words followed by dose units
    meds = set()
    try:
        patterns = [
            r"([A-Z][a-zA-Z0-9\-]{2,})\s+\d+mg",
            r"([A-Z][a-zA-Z0-9\-]{2,})\s+\d+ ml",
            r"([A-Z][a-zA-Z0-9\-]{2,})\s+\d+ IU",
            r"([A-Z][a-zA-Z0-9\-]{2,})\s+tablets?"
        ]
        for p in patterns:
            for m in re.findall(p, text):
                meds.add(m)
        # fallback: common drug token list (small)
        common = ["Paracetamol","Metformin","Aspirin","Amoxicillin","Ceftriaxone","Piperacillin","Meropenem","Colistin"]
        for c in common:
            if re.search(r"\b" + re.escape(c) + r"\b", text, flags=re.I):
                meds.add(c)
    except Exception as e:
        st.warning(f"Medication extraction heuristic failed: {e}")
    return list(meds)

# ---------- Utilities for formatting / pretty printing ----------
def pretty_json(obj):
    try:
        return json.dumps(obj, indent=2, ensure_ascii=False)
    except:
        return str(obj)

# ---------- Small local test dataset for staging  ----------
SYNTHETIC_PATIENTS = [
    {
        "patient_id": "TEST001",
        "age": 68,
        "weight": 78,
        "vitals": {"rr": 26, "sbp": 88, "dbp": 54, "hr": 120, "gcs": 14, "spo2": 90, "temp": 38.5},
        "labs": {"lactate": 3.2, "creatinine": 2.9, "urine_output_hourly": 0.3},
        "suspected_source": "Urinary (urosepsis)",
        "mdr_risk": True,
        "fungal_risk": False,
        "infection_flag": True
    },
    {
        "patient_id": "TEST002",
        "age": 52,
        "weight": 70,
        "vitals": {"rr": 18, "sbp": 120, "dbp": 78, "hr": 88, "gcs": 15, "spo2": 97, "temp": 37.0},
        "labs": {"lactate": 1.0, "creatinine": 0.9, "urine_output_hourly": 1.2},
        "suspected_source": "Lung / VAP",
        "mdr_risk": False,
        "fungal_risk": False,
        "infection_flag": False
    }
]

# ---------- End of PART 3 helpers ----------
# Next: PART 4 will include the chat UI and remaining app pages (chat history, downloads, PDF generation)
# -------------------------
# PART 4 / 7 — Chat UI, PDF generation, download, and UI glue
# -------------------------

# ---------- Chat UI ----------
def render_chat_ui():
    st.header("💬 Clinical Assistant & Drug Lookup")
    st.markdown("Use the chat area to ask clinical questions, summarize case notes, or fetch drug information.")

    if "chat_history" not in st.session_state:
        st.session_state["chat_history"] = []

    col1, col2 = st.columns([3,1])
    with col1:
        user_input = st.text_area("Enter clinical question or paste case notes", height=140)
        if st.button("Send to Assistant"):
            if not user_input.strip():
                st.warning("Please enter a question or case notes.")
            else:
                append_chat_history(st.session_state.get("username", "unknown_user"), user_input, role="user")
                system_prompt = "You are an evidence-based ICU consultant. Provide concise, referenced answers. If asked for guidelines, reference SSC 2021 or IDSA where applicable."
                with st.spinner("Assistant thinking..."):
                    answer = call_llm_system_user(system_prompt, user_input)
                append_chat_history("assistant", answer, role="assistant")
                st.experimental_rerun()

    with col2:
        if st.button("Insert Synthetic Test Case 1"):
            sp = SYNTHETIC_PATIENTS[0]
            sample_text = pretty_json(sp)
            st.session_state["chat_history"].append({
                "time": datetime.datetime.utcnow().replace(microsecond=0).isoformat()+"Z",
                "user": st.session_state.get("username","unknown_user"),
                "role": "user",
                "message": sample_text
            })
            st.experimental_rerun()
        if st.button("Clear Chat History"):
            st.session_state["chat_history"] = []
            st.success("Chat history cleared.")

    # Display history
    st.markdown("### Conversation")
    for entry in st.session_state.get("chat_history", [])[-20:]:
        role = entry.get("role", "user")
        time = entry.get("time")
        who = entry.get("user")
        msg = entry.get("message")
        if role == "user":
            st.markdown(f"**{who} — {time}**")
            st.write(msg)
        else:
            st.markdown(f"**Assistant — {time}**")
            st.info(msg)

# ---------- PDF/Text Generation Helpers ----------
def generate_text_plan_file(plan_text, patient_id, time_zero):
    fname = f"sepsis_plan_{patient_id or 'patient'}_{time_zero}.txt"
    return fname, plan_text.encode("utf-8")

def generate_pdf_from_text(text, filename="plan.pdf"):
    """
    Simple PDF generation using reportlab if available; fallback to txt file.
    """
    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        buffer = io.BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        width, height = letter
        lines = text.splitlines()
        y = height - 40
        for line in lines:
            if y < 40:
                c.showPage()
                y = height - 40
            c.drawString(40, y, line[:120])
            y -= 12
        c.save()
        buffer.seek(0)
        return buffer.read()
    except Exception as e:
        # Fallback to text bytes
        return text.encode("utf-8")

# ---------- Quick Actions and Shortcuts ----------
def render_quick_actions():
    st.sidebar.header("Quick Actions")
    if st.sidebar.button("Open Sepsis Module"):
        # simple JS redirect (forces current page scroll)
        components.html("<script>window.scrollTo(0,0)</script>", height=50)
    if st.sidebar.button("Open Chat Assistant"):
        components.html("<script>window.scrollTo(0,500)</script>", height=50)

# ---------- Integration / Glue ----------
def main_ui():
    st.title("Clinical AI Suite — Streamlit")
    st.markdown("A compact clinical assistant with sepsis bundle trigger and drug lookup.")

    # Render sepsis module (already rendered previously at top)
    # Show chat UI and helpers below
    render_chat_ui()

    st.markdown("---")
    st.markdown("### Utilities")
    st.markdown("- Upload an image/PDF of prescriptions or drug labels to extract text.")
    uploaded = st.file_uploader("Upload image/PDF/text", type=["png","jpg","jpeg","pdf","txt"])
    if uploaded:
        extracted_text = extract_text_from_uploaded_file(uploaded)
        st.markdown("**Extracted text:**")
        st.code(extracted_text)
        meds = extract_medications_from_text(extracted_text)
        if meds:
            st.markdown("**Detected medication candidates:**")
            st.write(", ".join(meds))
            if st.button("Lookup first medication details"):
                info = fetch_rxnav_by_name(meds[0])
                if info:
                    st.json(info)
                else:
                    st.info("No information found for this medication.")

    # PDF / text export area for last generated plan in session
    if "last_plan_text" in st.session_state:
        st.markdown("### Last Generated Sepsis Plan")
        last_plan = st.session_state["last_plan_text"]
        st.code(last_plan)
        if st.button("Download last plan as PDF"):
            pdf_bytes = generate_pdf_from_text(last_plan, filename="sepsis_plan.pdf")
            st.download_button("Download PDF", data=pdf_bytes, file_name="sepsis_plan.pdf", mime="application/pdf")
        if st.button("Download last plan as TXT"):
            st.download_button("Download TXT", data=last_plan.encode("utf-8"), file_name="sepsis_plan.txt", mime="text/plain")
    else:
        st.info("No sepsis plan generated in this session yet.")

# ---------- Run main UI glue ----------
render_quick_actions()
main_ui()

# -------------------------
# End of PART 4
# -------------------------
# -------------------------
# PART 5 / 7 — CLINICIAN APPROVAL UI + AUDIT TRAIL
# This part is called AFTER sepsis plan generation inside render_sepsis_module()
# -------------------------

def render_antibiotic_approval_ui(json_block, plan_text, patient_id, time_zero, qsofa):
    """
    Renders the clinician approval widget for recommended empiric antibiotics.
    Requires: json_block parsed from LLM output.
    Saves: approval record to approvals.json (Drive + local).
    """
    st.markdown("## ✅ Clinician Approval — Empiric Antibiotic Options (Audit Log)")

    if not json_block:
        st.info("No JSON block found in LLM output. Cannot present antibiotic options.")
        return

    options = json_block.get("recommendedEmpiricAntibiotics", [])
    if not options:
        st.info("LLM did not output any recommended antibiotic options in the JSON.")
        return

    # UI for selecting and approving
    st.markdown("**Recommended empiric antibiotic options (from LLM). Select one to approve or decline.**")
    selected = st.radio("Select antibiotic option to approve", options + ["None / Decline"], index=0)

    approval_note = st.text_area(
        "Approval note / rationale (required if approving)",
        value="",
        max_chars=1000,
        placeholder="E.g., Severe urosepsis with MDR risk; clinical justification..."
    )

    approve_btn = st.button("Approve Selected Antibiotic (creates audit record)")

    if approve_btn:
        if selected == "None / Decline":
            st.info("No antibiotic option was approved.")
            return

        if not approval_note.strip():
            st.warning("An approval note / rationale is REQUIRED to approve antibiotics.")
            return

        approver = st.session_state.get("username", "unknown_user")

        # Compose approval record
        approval_record = {
            "timestamp": datetime.datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
            "approver": approver,
            "patient_id": patient_id,
            "selected_antibiotic": selected,
            "approval_note": approval_note,
            "plan_time_zero": time_zero,
            "plan_qsofa": qsofa,
            "raw_plan_excerpt": plan_text[:1200]
        }

        # Save
        save_approval_record(approval_record)

        st.success(f"Antibiotic approved and recorded by {approver} at {approval_record['timestamp']}.")

    # === DISPLAY PAST APPROVALS TABLE ===
    st.markdown("---")
    st.markdown("### Past Approval Records (20 most recent)")

    approvals_list = load_approvals()

    if approvals_list:
        approvals_sorted = sorted(
            approvals_list,
            key=lambda x: x.get("timestamp", ""),
            reverse=True
        )
        rows = []
        for a in approvals_sorted[:20]:
            rows.append({
                "Time": a.get("timestamp"),
                "Approver": a.get("approver"),
                "Patient": a.get("patient_id"),
                "Antibiotic": a.get("selected_antibiotic"),
                "Note": (a.get("approval_note", "")[:100] + "...")
            })
        st.table(rows)
    else:
        st.info("No antibiotic approvals recorded yet.")

# -------------------------
# PART 6 / 7 — Approval Dashboard, Drug Lookup UI, OCR utilities, Footer
# -------------------------

# This part provides:
# - A lightweight Approval Dashboard that displays the last generated plan (if present)
#   and allows approving antibiotics by parsing the JSON block or pasting it manually.
# - A dedicated Drug Lookup UI for RxNav / FDA label searches.
# - OCR/Upload quick tools.
# - Session helpers and a footer.

# -------------------------
# Approval Dashboard Integration
# -------------------------
def render_approval_dashboard():
    """
    Show a small dashboard where clinicians can:
     - See the last generated plan (if any)
     - Paste JSON plan output (from LLM) and open the approval UI
     - Upload a JSON file of a plan
    """
    st.markdown("## 🗂️ Approval Dashboard / Manual Plan Import")
    st.caption("If a sepsis plan was generated in this session, it will appear below. Otherwise paste the plan JSON (from the LLM output) to approve antibiotics.")

    last_plan = st.session_state.get("last_plan_text", None)
    last_plan_json = st.session_state.get("last_plan_json", None)

    if last_plan:
        st.markdown("### Last generated plan (session)")
        st.code(last_plan[:4000])
        if last_plan_json:
            st.markdown("Parsed JSON from last plan:")
            st.json(last_plan_json)
            if st.button("Open approval UI for last plan"):
                render_antibiotic_approval_ui(
                    json_block=last_plan_json,
                    plan_text=last_plan,
                    patient_id=last_plan_json.get("patient_id", "unknown"),
                    time_zero=last_plan_json.get("timeZero", datetime.datetime.utcnow().replace(microsecond=0).isoformat()+"Z"),
                    qsofa=last_plan_json.get("qsofa", None)
                )
                st.stop()

    st.markdown("### Paste Plan JSON (manual)")
    pasted = st.text_area("Paste the JSON block here (the JSON block between ---JSON-OUTPUT-START--- and ---JSON-OUTPUT-END---)", height=200)
    if st.button("Load pasted JSON and open approval UI"):
        if not pasted.strip():
            st.warning("Paste JSON first.")
        else:
            try:
                parsed = json.loads(pasted)
                render_antibiotic_approval_ui(
                    json_block=parsed,
                    plan_text=pasted,
                    patient_id=parsed.get("patient_id", "unknown"),
                    time_zero=parsed.get("timeZero", datetime.datetime.utcnow().replace(microsecond=0).isoformat()+"Z"),
                    qsofa=parsed.get("qsofa", None)
                )
            except Exception as e:
                st.error(f"Failed to parse JSON: {e}")

    st.markdown("### Upload Plan JSON File (optional)")
    uploaded_json = st.file_uploader("Upload plan JSON file", type=["json"], key="approval_upload")
    if uploaded_json:
        try:
            content = uploaded_json.getvalue().decode("utf-8")
            parsed = json.loads(content)
            st.success("JSON uploaded and parsed.")
            if st.button("Open approval UI for uploaded file"):
                render_antibiotic_approval_ui(
                    json_block=parsed,
                    plan_text=content,
                    patient_id=parsed.get("patient_id", "unknown"),
                    time_zero=parsed.get("timeZero", datetime.datetime.utcnow().replace(microsecond=0).isoformat()+"Z"),
                    qsofa=parsed.get("qsofa", None)
                )
        except Exception as e:
            st.error(f"Upload failed to parse JSON: {e}")

# -------------------------
# Drug Lookup UI (RxNav + FDA)
# -------------------------
def render_drug_lookup_ui():
    st.markdown("## 💊 Drug Lookup")
    st.caption("Quickly lookup a drug on RxNav and openFDA (labels).")

    col1, col2 = st.columns([3,1])
    with col1:
        drug_query = st.text_input("Enter drug name to lookup", value="")
        if st.button("Lookup drug"):
            if not drug_query.strip():
                st.warning("Enter a drug name.")
            else:
                with st.spinner("Querying RxNav and openFDA..."):
                    rx = fetch_rxnav_by_name(drug_query)
                    fda = fetch_fda_label_by_drug(drug_query)
                if rx:
                    st.markdown("**RxNorm data:**")
                    st.json(rx)
                else:
                    st.info("No RxNorm data found.")
                if fda:
                    st.markdown("**openFDA label extract (first match):**")
                    # Show relevant fields if present
                    seq = {}
                    for k in ["indications_and_usage","adverse_reactions","dosage_and_administration","openfda"]:
                        if k in fda:
                            seq[k] = fda[k]
                    if seq:
                        st.json(seq)
                    else:
                        st.json(fda)
                else:
                    st.info("No openFDA match found or API limits reached.")

    with col2:
        if st.button("Show common antibiotic options (example)"):
            st.write("- Piperacillin-Tazobactam 4.5g IV q6h")
            st.write("- Cefepime 2g IV q8h")
            st.write("- Colistin IV (dose per local guideline) + Inhaled Colistin (if VAP)")

# -------------------------
# OCR & Upload helper UI
# -------------------------
def render_ocr_upload_ui():
    st.markdown("## 📷 OCR / Prescription Upload")
    st.caption("Upload a picture or PDF of a prescription or drug label to extract text and detect medications.")

    uploaded = st.file_uploader("Upload image/PDF/text for OCR", type=["png","jpg","jpeg","pdf","txt"], key="ocr_upload")
    if uploaded:
        text = extract_text_from_uploaded_file(uploaded)
        st.markdown("**OCR / Extracted text:**")
        st.code(text[:3000])
        meds = extract_medications_from_text(text)
        if meds:
            st.markdown("**Detected medication candidates:**")
            st.write(", ".join(meds))
            if st.button("Lookup first detected medication"):
                info = fetch_rxnav_by_name(meds[0])
                if info:
                    st.json(info)
                else:
                    st.info("No information found.")

# -------------------------
# Session & Cleanup helpers
# -------------------------
def ensure_session_keys():
    keys_defaults = {
        "chat_history": [],
        "last_plan_text": None,
        "last_plan_json": None,
        "username": st.session_state.get("username", "unknown_user")
    }
    for k,v in keys_defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

def footer():
    st.markdown("---")
    st.markdown("Clinical AI Suite — built for prototyping. Not a medical device. Use clinical judgment. © Your Team")

# -------------------------
# Integration point: add approval dashboard and drug lookup to main page end
# -------------------------
ensure_session_keys()
st.markdown("---")
st.markdown("### Additional Tools & Approval Dashboard")
# Show the approval dashboard (manual import) and drug lookup in two columns
colA, colB = st.columns(2)
with colA:
    render_approval_dashboard()
with colB:
    render_drug_lookup_ui()
    render_ocr_upload_ui()

footer()

# -------------------------
# End of PART 6
# -------------------------
# -------------------------
# PART 7 / 7 — App Entrypoint, Sanity Checks, and Deploy Notes
# -------------------------

# App Entrypoint
def run_app():
    """
    Entrypoint to render the complete app.
    The Sepsis Module was already rendered at import-time (top/home).
    This function ensures the rest of the UI is present and runs any final checks.
    """
    # Ensure session keys
    ensure_session_keys()

    # Show top-level info
    st.sidebar.title("App Controls")
    if st.sidebar.button("Logout"):
        logout()
        st.experimental_rerun()

    st.sidebar.markdown("**Application Status**")
    st.sidebar.write(f"- Logged in as: **{st.session_state.get('username','unknown')}**")
    st.sidebar.write(f"- LLM model: qwen/qwen3-32b")

    # Main UI (already called in PART 4 main_ui)
    # If you prefer explicit ordering, call main_ui() here:
    # main_ui()

    # Note: Sepsis module was rendered at import (per A1 placement). The rest of UI (chat, tools) is already rendered below that.
    # Provide a final debug block for environment variables (optional)
    if st.sidebar.checkbox("Show debug info"):
        st.sidebar.write("---- Debug Info ----")
        st.sidebar.write(f"GROQ_API_KEY set: {'GROQ_API_KEY' in os.environ and bool(os.environ.get('GROQ_API_KEY'))}")
        st.sidebar.write(f"Drive init success: { 'drive' in globals() }")
        st.sidebar.write(f"Users file present: {os.path.exists(USER_DATA_FILE)}")
        st.sidebar.write(f"Approvals file present: {os.path.exists(APPROVALS_FILE)}")
        try:
            st.sidebar.write("Recent approvals count: " + str(len(load_approvals() or [])))
        except Exception as e:
            st.sidebar.write(f"Approvals read error: {e}")

    # Show final footer (already defined)
    footer()

# Sanity checks for merged file
def perform_sanity_checks():
    issues = []
    # Check critical globals exist
    if 'drive' not in globals():
        issues.append("Google Drive object 'drive' not initialized.")
    if 'llm' not in globals():
        issues.append("LLM 'llm' object not initialized.")
    # Check required files exist (local fallback)
    if not os.path.exists(USER_DATA_FILE):
        # Create minimal users.json if missing to avoid runtime stops during auth
        try:
            with open(USER_DATA_FILE, "w") as f:
                json.dump({"dcs1": {"password": "DCS1", "occupation": "doctor", "email": "you@example.com", "phone":"+911234567890", "address":"City, Country"}}, f, indent=2)
            st.info(f"Created fallback {USER_DATA_FILE} with default user 'dcs1'. Please change password after first login.")
        except Exception as e:
            issues.append(f"Failed to create fallback {USER_DATA_FILE}: {e}")

    return issues

# Run sanity checks and app
sanity_issues = perform_sanity_checks()
if sanity_issues:
    st.warning("Sanity check issues detected:")
    for it in sanity_issues:
        st.warning("- " + it)
    st.info("Fix the above issues and reload.")
else:
    run_app()
