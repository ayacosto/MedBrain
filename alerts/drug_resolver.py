import requests
import re
from functools import lru_cache

RXNORM_API = "https://rxnav.nlm.nih.gov/REST"

@lru_cache(maxsize=10000)
def get_rxcui(drug_str: str) -> str | None:
    """Convert full drug string to RxCUI. Cached."""
    try:
        resp = requests.get(
            f"{RXNORM_API}/rxcui.json",
            params={"name": drug_str, "search": 2},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            ids = data.get("idGroup", {}).get("rxnormId", [])
            if ids:
                return ids[0]
    except Exception as e:
        print(f"⚠️ RxNorm API error for '{drug_str}': {e}")
    return None


@lru_cache(maxsize=10000)
def get_ingredient(rxcui: str) -> str | None:
    """Get base ingredient name from RxCUI."""
    try:
        resp = requests.get(
            f"{RXNORM_API}/rxcui/{rxcui}/related.json",
            params={"tty": "IN"},
            timeout=5
        )
        if resp.status_code == 200:
            data = resp.json()
            groups = data.get("relatedGroup", {}).get("conceptGroup", [])
            for group in groups:
                concepts = group.get("conceptProperties", [])
                if concepts:
                    return concepts[0]["name"].lower()
    except Exception as e:
        print(f"⚠️ RxNorm ingredient error for RxCUI '{rxcui}': {e}")
    return None


def extract_ingredient_local(drug_str: str) -> str:
    """
    Fast local fallback — extract first word(s) before dose info.
    e.g. 'Simvastatin 20 MG Oral Tablet' → 'simvastatin'
         'Acetaminophen 325 MG / HYDROcodone...' → 'acetaminophen'
         '24 HR Metformin hydrochloride 500 MG...' → 'metformin hydrochloride'
    """
    s = drug_str.strip()

    # Remove leading time-release prefix like "24 HR"
    s = re.sub(r'^\d+\s*HR\s+', '', s, flags=re.IGNORECASE)

    # Remove pack notation like "{28 (...) }"
    s = re.sub(r'^\{.*?\}\s*', '', s)

    # Take everything before first number (dose)
    match = re.match(r'^([a-zA-Z /\-]+?)(?:\s+\d)', s)
    if match:
        ingredient = match.group(1).strip().rstrip('/')
        # Take only first ingredient if combo (before ' / ')
        ingredient = ingredient.split(' / ')[0].strip()
        return ingredient.lower()

    # Fallback: just first word
    return s.split()[0].lower()


def resolve_drug(drug_str: str) -> dict:
    """
    Full resolution pipeline:
    1. Try RxNorm API for RxCUI
    2. Get ingredient from RxCUI
    3. Fallback to local extraction
    Returns dict with rxcui, ingredient, original
    """
    ingredient_local = extract_ingredient_local(drug_str)

    rxcui = get_rxcui(drug_str)
    if rxcui:
        ingredient_api = get_ingredient(rxcui)
        if ingredient_api:
            return {
                "original": drug_str,
                "rxcui": rxcui,
                "ingredient": ingredient_api,
                "source": "rxnorm_api"
            }

    # Fallback to local extraction
    return {
        "original": drug_str,
        "rxcui": rxcui,
        "ingredient": ingredient_local,
        "source": "local_parse"
    }


# ── Quick test ───────────────────────────────────────────────
if __name__ == "__main__":
    test_drugs = [
        "Simvastatin 20 MG Oral Tablet",
        "Clopidogrel 75 MG Oral Tablet",
        "Naproxen 500 MG Oral Tablet",
        "24 HR Metformin hydrochloride 500 MG Extended Release Oral Tablet",
        "Acetaminophen 325 MG / HYDROcodone Bitartrate 7.5 MG Oral Tablet",
        "{28 (norethindrone 0.35 MG Oral Tablet) } Pack [Camila 28 Day]",
        "Nitroglycerin 0.4 MG/ACTUAT Mucosal Spray",
    ]

    print("Drug Resolution Test")
    print("=" * 60)
    for drug in test_drugs:
        result = resolve_drug(drug)
        print(f"Input:      {drug[:50]}")
        print(f"Ingredient: {result['ingredient']} (via {result['source']})")
        print(f"RxCUI:      {result['rxcui']}")
        print("-" * 60)