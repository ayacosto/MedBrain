# snomed_lookup.py
# Synthea uses consistent SNOMED CT codes — this covers the most common conditions
# Source: Synthea condition modules + SNOMED CT browser
# Extend this dict as you encounter new conditions in your patient data

SNOMED_CONDITIONS = {
    # ── Cardiovascular ───────────────────────────────────────
    "ischemic heart disease (disorder)":                    "414545008",
    "myocardial infarction (disorder)":                     "22298006",
    "acute st segment elevation myocardial infarction (disorder)": "401303003",
    "history of myocardial infarction (situation)":         "399211009",
    "essential hypertension (disorder)":                    "59621000",
    "heart failure (disorder)":                             "84114007",
    "atrial fibrillation (disorder)":                       "49436004",
    "abnormal findings diagnostic imaging heart+coronary circulat (finding)": "428661000",
    "history of coronary artery bypass grafting (situation)":"399261000",

    # ── Metabolic ─────────────────────────────────────────────
    "diabetes mellitus type 2 (disorder)":                  "44054006",
    "diabetes mellitus type 1 (disorder)":                  "46635009",
    "prediabetes (finding)":                                "15777000",
    "hyperglycemia (disorder)":                             "80394007",
    "hyperlipidemia (disorder)":                            "55822004",
    "hypertriglyceridemia (disorder)":                      "302870006",
    "metabolic syndrome x (disorder)":                      "237602007",
    "obesity (disorder)":                                   "414916001",
    "body mass index 30+ - obesity (finding)":              "162864005",

    # ── Kidney ────────────────────────────────────────────────
    "chronic kidney disease stage 1 (disorder)":            "431855005",
    "chronic kidney disease stage 2 (disorder)":            "431856006",
    "chronic kidney disease stage 3 (disorder)":            "433144002",
    "chronic kidney disease stage 4 (disorder)":            "431857002",
    "end-stage renal disease (disorder)":                   "46177005",
    "disorder of kidney due to diabetes mellitus (disorder)":"127013003",
    "microalbuminuria due to type 2 diabetes mellitus (disorder)": "90781000119102",
    "proteinuria due to type 2 diabetes mellitus (disorder)":"90771000119100",
    "history of renal transplant (situation)":              "416940007",

    # ── Respiratory ───────────────────────────────────────────
    "childhood asthma (disorder)":                          "233678006",
    "asthma (disorder)":                                    "195967001",
    "chronic obstructive lung disease (disorder)":          "13645005",
    "non-small cell lung cancer (disorder)":                "254637007",
    "chronic sinusitis (disorder)":                         "40055000",

    # ── Neurological ─────────────────────────────────────────
    "seizure disorder (disorder)":                          "84757009",
    "history of seizure (situation)":                       "703151001",
    "chronic intractable migraine without aura (disorder)": "230461009",
    "chronic pain (finding)":                               "82423001",
    "chronic low back pain (finding)":                      "279039007",

    # ── Musculoskeletal ───────────────────────────────────────
    "osteoarthritis of knee (disorder)":                    "57773001",
    "rheumatoid arthritis (disorder)":                      "69896004",
    "fibromyalgia (disorder)":                              "95417003",

    # ── Cancer ───────────────────────────────────────────────
    "suspected lung cancer (situation)":                    "162573006",
    "non-small cell carcinoma of lung, tnm stage 1 (disorder)": "423121009",
    "malignant neoplasm of tonsil, unspecified":            "363353009",

    # ── Other ─────────────────────────────────────────────────
    "anemia (disorder)":                                    "271737000",
    "sepsis (disorder)":                                    "91302008",
    "sleep apnea (disorder)":                               "73430006",
    "dependent drug abuse (disorder)":                      "66590003",
}

# Conditions that are CONTRAINDICATED with specific drug classes
# Format: snomed_code → list of drug ingredient keywords to flag
CONTRAINDICATED_PAIRS = {
    # NSAIDs contraindicated in advanced kidney disease
    "431857002": ["naproxen", "ibuprofen", "indomethacin", "celecoxib"],  # CKD stage 4
    "46177005":  ["naproxen", "ibuprofen", "indomethacin", "celecoxib"],  # ESRD

    # NSAIDs increase CV risk — contraindicated post-MI
    "22298006":  ["naproxen", "ibuprofen", "indomethacin"],               # MI
    "401303003": ["naproxen", "ibuprofen", "indomethacin"],               # STEMI

    # Seizure threshold lowering drugs
    "84757009":  ["tramadol", "bupropion", "meperidine"],                 # Seizure disorder

    # Metformin contraindicated in severe kidney disease
    "431857002": ["metformin"],                                            # CKD stage 4
    "46177005":  ["metformin"],                                            # ESRD
}

# Conditions where a drug is an EXPECTED treatment (never flag these)
EXPECTED_TREATMENTS = {
    "414545008": [  # Ischemic heart disease
        "simvastatin", "atorvastatin", "rosuvastatin",
        "aspirin", "clopidogrel", "prasugrel", "ticagrelor",
        "metoprolol", "carvedilol", "bisoprolol",
        "lisinopril", "ramipril", "enalapril",
        "amlodipine", "diltiazem",
        "nitroglycerin", "isosorbide",
    ],
    "59621000": [   # Essential hypertension
        "lisinopril", "amlodipine", "hydrochlorothiazide",
        "metoprolol", "losartan", "valsartan",
    ],
    "44054006": [   # Type 2 diabetes
        "metformin", "insulin", "sitagliptin",
        "glipizide", "glimepiride", "empagliflozin",
    ],
    "22298006": [   # Myocardial infarction
        "aspirin", "clopidogrel", "prasugrel",
        "metoprolol", "lisinopril", "simvastatin", "atorvastatin",
        "nitroglycerin",
    ],
    "55822004": [   # Hyperlipidemia
        "simvastatin", "atorvastatin", "rosuvastatin",
        "pravastatin", "lovastatin",
    ],
    "302870006": [  # Hypertriglyceridemia
        "simvastatin", "atorvastatin", "fenofibrate",
    ],
}


def get_snomed_code(condition_text: str) -> str | None:
    """Get SNOMED code from condition text. Exact match first, then partial."""
    key = condition_text.lower().strip()

    # Exact match
    if key in SNOMED_CONDITIONS:
        return SNOMED_CONDITIONS[key]

    # Partial match — condition text contains a known key
    for known, code in SNOMED_CONDITIONS.items():
        if known in key or key in known:
            return code

    return None


def is_expected_treatment(ingredient: str, snomed_codes: list[str]) -> bool:
    """Return True if drug is a known treatment for any of the patient's conditions."""
    for code in snomed_codes:
        expected = EXPECTED_TREATMENTS.get(code, [])
        if any(exp in ingredient for exp in expected):
            return True
    return False


def get_contraindications(ingredient: str, snomed_codes: list[str]) -> list[str]:
    """Return list of condition SNOMED codes where this drug is contraindicated."""
    flagged = []
    for code in snomed_codes:
        contra_drugs = CONTRAINDICATED_PAIRS.get(code, [])
        if any(drug in ingredient for drug in contra_drugs):
            flagged.append(code)
    return flagged


# Reverse lookup: SNOMED code → condition name
SNOMED_REVERSE = {v: k for k, v in SNOMED_CONDITIONS.items()}

def get_condition_name(snomed_code: str) -> str:
    return SNOMED_REVERSE.get(snomed_code, snomed_code)


# ── Quick test ───────────────────────────────────────────────
if __name__ == "__main__":
    test_conditions = [
        "Ischemic heart disease (disorder)",
        "Diabetes mellitus type 2 (disorder)",
        "Essential hypertension (disorder)",
        "Chronic kidney disease stage 4 (disorder)",
        "Seizure disorder (disorder)",
    ]

    print("SNOMED Lookup Test")
    print("=" * 60)
    for c in test_conditions:
        code = get_snomed_code(c)
        print(f"{c[:50]} → {code}")

    print("\nExpected Treatment Test")
    print("=" * 60)
    test_pairs = [
        ("simvastatin", ["414545008"]),   # statin + IHD → expected
        ("naproxen",    ["414545008"]),   # NSAID + IHD → NOT expected
        ("metformin",   ["44054006"]),    # metformin + T2DM → expected
    ]
    for drug, codes in test_pairs:
        result = is_expected_treatment(drug, codes)
        print(f"{drug} for {codes} → {'✅ Expected treatment' if result else '⚠️ Not expected'}")