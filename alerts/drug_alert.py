"""
drug_alert.py — Hospital-grade drug alert engine
─────────────────────────────────────────────────
Architecture:
  Drug name → RxNorm API → ingredient
  Condition text → SNOMED lookup → coded pairs
  Drug-Condition → SNOMED contraindication rules (no keyword matching)
  Drug-Drug → DDInter structured CSV lookup
  Allergy → drug_allergy_rules.csv + allergy_map.csv (exact class matching, zero false positives)
"""

import json
import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import Optional

# Local modules
import sys
sys.path.append(str(Path(__file__).parent))

from drug_resolver import resolve_drug
from ddinter_checker import check_all_interactions
from snomed_lookup import (
    get_snomed_code,
    is_expected_treatment,
    get_contraindications,
    get_condition_name,
    SNOMED_CONDITIONS
)

PATIENT_PROFILES = Path("Patients/patient_profiles.json")
ALLERGY_CSV      = Path("knowledge_base/drug_allergy/drug_allergy_rules.csv")
ALLERGY_MAP_CSV  = Path("knowledge_base/drug_allergy/allergy_map.csv")

SEVERITY_RANK = {
    "Major":    3,
    "Moderate": 2,
    "Minor":    1,
}


# ── Load patients ────────────────────────────────────────────
def load_patients():
    with open(PATIENT_PROFILES, "r", encoding="utf-8") as f:
        return json.load(f)

def get_patient(patient_id: str) -> Optional[dict]:
    for p in load_patients():
        if p["patient_id"] == patient_id:
            return p
    return None


# ── Load allergy CSV (once at startup) ──────────────────────
_allergy_df: Optional[pd.DataFrame] = None

def get_allergy_df() -> pd.DataFrame:
    global _allergy_df
    if _allergy_df is None:
        df = pd.read_csv(ALLERGY_CSV)
        df["ingredient"]        = df["ingredient"].str.lower().str.strip()
        df["allergy_class"]     = df["allergy_class"].str.lower().str.strip()
        df["cross_react_class"] = df["cross_react_class"].str.lower().str.strip()
        _allergy_df = df
        print(f"✅ Allergy rules loaded: {len(df):,} rows")
    return _allergy_df


# ── Load allergy map (once at startup) ──────────────────────
_allergy_map: Optional[dict] = None

def get_allergy_map() -> dict:
    """Returns dict: patient_allergy_text (lowercase) → allergy_class"""
    global _allergy_map
    if _allergy_map is None:
        df = pd.read_csv(ALLERGY_MAP_CSV)
        df["patient_allergy_text"] = df["patient_allergy_text"].str.lower().str.strip()
        df["allergy_class"]        = df["allergy_class"].str.lower().str.strip()
        _allergy_map = dict(zip(df["patient_allergy_text"], df["allergy_class"]))
        print(f"✅ Allergy map loaded: {len(_allergy_map):,} entries")
    return _allergy_map


def allergy_to_class(allergy_text: str) -> Optional[str]:
    """
    Map patient allergy text → coded allergy class.
    'Penicillin (substance)' → 'penicillin'
    'Bee Venom (substance)'  → 'bee-venom'
    Returns None if not mapped (unknown allergy — skip, don't guess).
    """
    key = allergy_text.lower().strip()
    result = get_allergy_map().get(key)
    if result == "skip":
        return None
    return result


# ── Allergy check — exact class matching, zero false positives ──
def check_allergies(ingredient: str, patient_allergies: list[str]) -> list[dict]:
    """
    Check drug against patient allergies.
    Step 1: Drug ingredient → allergy_class from CSV
    Step 2: Patient allergy text → allergy_class from allergy_map
    Step 3: Exact class intersection — no text matching, no guessing
    """
    alerts = []
    df = get_allergy_df()

    # 1. Get all drug classes from CSV
    drug_rows = df[df["ingredient"] == ingredient.lower().strip()]
    if drug_rows.empty:
        return alerts

    drug_classes = set(drug_rows["allergy_class"].tolist())

    # 2. Map patient allergies to coded classes
    patient_classes = set()
    patient_class_map = {}  # class → original allergy text (for alert message)
    for allergy in patient_allergies:
        coded_class = allergy_to_class(allergy)
        if coded_class:
            patient_classes.add(coded_class)
            patient_class_map[coded_class] = allergy

    # 3. Exact class intersection only
    conflicts = drug_classes & patient_classes

    for conflict_class in conflicts:
        # Get the row for this conflict to pull severity + source
        conflict_row = drug_rows[drug_rows["allergy_class"] == conflict_class].iloc[0]
        severity = conflict_row["severity"]
        source   = conflict_row["clinical_source"]
        original_allergy = patient_class_map.get(conflict_class, conflict_class)

        alerts.append({
            "alert_type":    "ALLERGY_CONFLICT",
            "severity":      "HIGH",
            "severity_rank": SEVERITY_RANK.get(severity, 3),
            "drug":          ingredient,
            "trigger":       original_allergy,
            "allergy_class": conflict_class,
            "message":       f"⚠️ {ingredient.upper()} conflicts with patient allergy: {original_allergy} "
                             f"(class: {conflict_class})",
            "detail":        f"Severity: {severity}",
            "source":        source,
            "timestamp":     datetime.now().isoformat()
        })

    return alerts


def check_conditions(ingredient: str, snomed_codes: list[str], condition_names: list[str]) -> list[dict]:
    """
    Check drug against patient conditions using SNOMED-coded rules.
    No keyword matching — pure coded lookup.
    """
    alerts = []

    # Skip entirely if this is an expected treatment
    if is_expected_treatment(ingredient, snomed_codes):
        return alerts

    # Get contraindicated condition codes for this drug
    flagged_codes = get_contraindications(ingredient, snomed_codes)

    for code in flagged_codes:
        condition_name = get_condition_name(code)
        alerts.append({
            "alert_type":    "CONTRAINDICATION",
            "severity":      "HIGH",
            "severity_rank": 3,
            "drug":          ingredient,
            "trigger":       condition_name,
            "snomed_code":   code,
            "message":       f"⚠️ {ingredient.upper()} is contraindicated with {condition_name}",
            "source":        "SNOMED_rules",
            "timestamp":     datetime.now().isoformat()
        })

    return alerts


def check_drug_drug(resolved_meds: list[dict]) -> list[dict]:
    """
    Check all drug pairs using DDInter structured CSV.
    Only returns Major + Moderate interactions.
    """
    ingredients = [m["ingredient"] for m in resolved_meds if m["ingredient"]]
    raw_interactions = check_all_interactions(ingredients)

    alerts = []
    for interaction in raw_interactions:
        # Skip Minor and Unknown interactions — too noisy for clinical use
        if interaction["severity"] in ("Minor", "Unknown"):
            continue

        severity_rank = interaction["severity_rank"]
        alerts.append({
            "alert_type":    "DRUG_DRUG_INTERACTION",
            "severity":      interaction["severity"],
            "severity_rank": severity_rank,
            "drug":          interaction["drug_a"],
            "interacts_with":interaction["drug_b"],
            "message":       f"⚠️ {interaction['drug_a'].upper()} + {interaction['drug_b'].upper()} — {interaction['severity']} interaction",
            "source":        "DDInter",
            "timestamp":     datetime.now().isoformat()
        })

    return alerts


def dedup_alerts(alerts: list[dict]) -> list[dict]:
    """Remove duplicate alerts."""
    seen = set()
    unique = []
    for alert in alerts:
        key = (
            alert["alert_type"],
            alert["drug"],
            alert.get("trigger", alert.get("interacts_with", ""))
        )
        if key not in seen:
            seen.add(key)
            unique.append(alert)
    return unique


def sort_alerts(alerts: list[dict]) -> list[dict]:
    """Sort alerts by severity — HIGH first."""
    return sorted(alerts, key=lambda x: x.get("severity_rank", 0), reverse=True)


# ── Core check function ──────────────────────────────────────
def check_patient(patient: dict, new_medication: str = None) -> dict:
    """
    Full alert check for a patient.
    If new_medication provided: check only that drug.
    If not: check all existing medications.
    """
    medications = patient.get("medications", [])
    allergies   = patient.get("allergies", [])
    conditions  = [c for c in patient.get("conditions", []) if c.get("status") == "active"]

    # Resolve SNOMED codes for active conditions
    snomed_codes = []
    condition_names = []
    for c in conditions:
        code = get_snomed_code(c["name"])
        if code:
            snomed_codes.append(code)
        condition_names.append(c["name"].lower())

    # Decide which meds to check
    if new_medication:
        meds_to_check = [new_medication]
        # Include existing meds for drug-drug check
        all_meds_for_ddi = medications + [new_medication]
    else:
        meds_to_check = medications
        all_meds_for_ddi = medications

    # Resolve all drug names to ingredients
    resolved_check = [resolve_drug(m) for m in meds_to_check]
    resolved_all   = [resolve_drug(m) for m in all_meds_for_ddi]

    all_alerts = []

    # 1. Allergy + Condition checks per drug
    for resolved in resolved_check:
        ingredient = resolved["ingredient"]
        if not ingredient:
            continue

        # Allergy checks — exact class matching, zero false positives
        allergy_alerts = check_allergies(ingredient, allergies)
        all_alerts.extend(allergy_alerts)

        # Condition checks (SNOMED coded rules)
        condition_alerts = check_conditions(ingredient, snomed_codes, condition_names)
        all_alerts.extend(condition_alerts)

    # 2. Drug-drug interaction checks (DDInter)
    ddi_alerts = check_drug_drug(resolved_all)
    all_alerts.extend(ddi_alerts)

    # Clean up
    all_alerts = dedup_alerts(all_alerts)
    all_alerts = sort_alerts(all_alerts)

    return all_alerts


# ── 3 TRIGGERS ───────────────────────────────────────────────

def scan_patient_on_load(patient_id: str) -> dict:
    """TRIGGER 1 — Scan all meds when doctor opens patient chart."""
    patient = get_patient(patient_id)
    if not patient:
        return {"error": "Patient not found"}

    alerts = check_patient(patient)

    return {
        "patient_id":   patient_id,
        "patient_name": patient["name"],
        "trigger":      "PATIENT_LOAD",
        "total_alerts": len(alerts),
        "alerts":       alerts
    }


def check_new_medication(patient_id: str, new_medication: str) -> dict:
    """TRIGGER 2 — Check new prescription before saving."""
    patient = get_patient(patient_id)
    if not patient:
        return {"error": "Patient not found"}

    alerts = check_patient(patient, new_medication=new_medication)

    return {
        "patient_id":     patient_id,
        "patient_name":   patient["name"],
        "trigger":        "NEW_PRESCRIPTION",
        "new_medication": new_medication,
        "safe":           len(alerts) == 0,
        "total_alerts":   len(alerts),
        "alerts":         alerts
    }


def nightly_scan() -> dict:
    """TRIGGER 3 — Nightly scan of all patients."""
    patients = load_patients()
    report = {
        "scan_time":              datetime.now().isoformat(),
        "trigger":                "NIGHTLY_SCAN",
        "total_patients_scanned": len(patients),
        "patients_with_alerts":   0,
        "results":                []
    }

    for patient in patients:
        result = scan_patient_on_load(patient["patient_id"])
        if result.get("total_alerts", 0) > 0:
            report["patients_with_alerts"] += 1
            report["results"].append(result)

    return report


# ── Tests ─────────────────────────────────────────────────────
if __name__ == "__main__":
    
  print("\n" + "="*50)
print("TEST 3 — Nightly scan ALL patients")
print("="*50)
result3 = nightly_scan()
print(f"Total patients scanned: {result3['total_patients_scanned']}")
print(f"Patients with alerts: {result3['patients_with_alerts']}")
for patient_result in result3['results']:
    print(f"\n👤 {patient_result['patient_name']}")
    print(f"   Total alerts: {patient_result['total_alerts']}")
    for alert in patient_result['alerts']:
        print(f"   {'🔴' if alert['severity'] in ['HIGH', 'Major'] else '🟡'} {alert['alert_type']}: {alert['message']}")