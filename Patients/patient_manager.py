import json
import os
from pathlib import Path


FHIR_DIR = Path("Patients/output/fhir")
OUTPUT_FILE = Path("Patients/patient_profiles.json")


def extract_patient_profile(bundle: dict) -> dict:
    profile = {
        "patient_id": None,
        "name": None,
        "birthDate": None,
        "gender": None,
        "address": None,
        "phone": None,
        "maritalStatus": None,
        "medications": [],
        "allergies": [],
        "conditions": []
    }

    for entry in bundle.get("entry", []):
        resource = entry.get("resource", {})
        resource_type = resource.get("resourceType")

        # ── PATIENT ──────────────────────────────────────────
        if resource_type == "Patient":
            profile["patient_id"] = resource.get("id")
            profile["birthDate"] = resource.get("birthDate")
            profile["gender"] = resource.get("gender")

            # Name
            names = resource.get("name", [])
            if names:
                n = names[0]
                given = " ".join(n.get("given", []))
                family = n.get("family", "")
                profile["name"] = f"{given} {family}".strip()

            # Address
            addresses = resource.get("address", [])
            if addresses:
                a = addresses[0]
                profile["address"] = {
                    "line": a.get("line", [""]),
                    "city": a.get("city"),
                    "state": a.get("state"),
                    "country": a.get("country")
                }

            # Phone
            telecoms = resource.get("telecom", [])
            for t in telecoms:
                if t.get("system") == "phone":
                    profile["phone"] = t.get("value")

            # Marital status
            marital = resource.get("maritalStatus", {})
            profile["maritalStatus"] = marital.get("text")

        # ── MEDICATIONS ──────────────────────────────────────
        elif resource_type == "MedicationRequest":
            med = resource.get("medicationCodeableConcept", {})
            med_name = med.get("text")
            if med_name and med_name not in profile["medications"]:
                profile["medications"].append(med_name)

        # ── ALLERGIES ────────────────────────────────────────
        elif resource_type == "AllergyIntolerance":
            code = resource.get("code", {})
            allergy_name = code.get("text")
            if allergy_name and allergy_name not in profile["allergies"]:
                profile["allergies"].append(allergy_name)

        # ── CONDITIONS ───────────────────────────────────────
        elif resource_type == "Condition":
            code = resource.get("code", {})
            condition_name = code.get("text")
            status = resource.get("clinicalStatus", {}).get("coding", [{}])[0].get("code")
            if condition_name and condition_name not in profile["conditions"]:
                profile["conditions"].append({
                    "name": condition_name,
                    "status": status
                })

    return profile


def parse_all_patients():
    all_profiles = []

    fhir_files = list(FHIR_DIR.glob("*.json"))
    print(f"Found {len(fhir_files)} FHIR files")

    for fhir_file in fhir_files:
        print(f"Parsing: {fhir_file.name}")
        try:
            # Check file size first (skip truly empty files)
            if fhir_file.stat().st_size == 0:
                print(f"  ⏭️ Skipping empty file: {fhir_file.name}")
                continue
                
            with open(fhir_file, "r", encoding="utf-8") as f:
                bundle = json.load(f)

            # Skip if not valid JSON or empty bundle
            if not bundle or not isinstance(bundle, dict):
                print(f"  ⏭️ Skipping invalid/empty JSON: {fhir_file.name}")
                continue

            profile = extract_patient_profile(bundle)
            if profile["patient_id"]:
                all_profiles.append(profile)
            else:
                print(f"  ⏭️ Skipping no patient ID: {fhir_file.name}")
                
        except json.JSONDecodeError:
            print(f"  ⏭️ Skipping invalid JSON: {fhir_file.name}")
            continue
        except Exception as e:
            print(f"  ⚠️ Error parsing {fhir_file.name}: {str(e)}")
            continue

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(all_profiles, f, indent=2, ensure_ascii=False)

    print(f"\n✅ Done! {len(all_profiles)} patients saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    parse_all_patients()
