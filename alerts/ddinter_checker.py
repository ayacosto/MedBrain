import pandas as pd
from pathlib import Path
from functools import lru_cache
from typing import Optional

DDINTER_DIR = Path("knowledge_base/ddinter")

# Severity ranking for sorting
SEVERITY_RANK = {
    "Major": 3,
    "Moderate": 2,
    "Minor": 1,
    "Unknown": 0
}


def load_ddinter() -> pd.DataFrame:
    """Load and merge all DDInter CSV files into one DataFrame."""
    csv_files = list(DDINTER_DIR.glob("ddinter_downloads_code_*.csv"))

    if not csv_files:
        raise FileNotFoundError(
            f"No DDInter CSV files found in {DDINTER_DIR}. "
            "Download from https://ddinter.scbdd.com/download/"
        )

    print(f"📂 Loading {len(csv_files)} DDInter files...")
    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, usecols=["Drug_A", "Drug_B", "Level"])
            dfs.append(df)
        except Exception as e:
            print(f"⚠️ Could not load {f.name}: {e}")

    merged = pd.concat(dfs, ignore_index=True)

    # Normalize drug names to lowercase for matching
    merged["Drug_A_lower"] = merged["Drug_A"].str.lower().str.strip()
    merged["Drug_B_lower"] = merged["Drug_B"].str.lower().str.strip()

    # Drop duplicates
    merged = merged.drop_duplicates(subset=["Drug_A_lower", "Drug_B_lower"])

    print(f"✅ DDInter loaded: {len(merged):,} interaction pairs")
    return merged


# Global — loaded once at startup
_ddinter_df: Optional[pd.DataFrame] = None

def get_ddinter() -> pd.DataFrame:
    global _ddinter_df
    if _ddinter_df is None:
        _ddinter_df = load_ddinter()
    return _ddinter_df


def check_interaction(drug_a: str, drug_b: str) -> Optional[dict]:
    """
    Check if two drugs interact in DDInter.
    drug_a, drug_b should be ingredient names (lowercase).
    Returns interaction dict or None.
    """
    df = get_ddinter()

    # Check both directions
    mask = (
        ((df["Drug_A_lower"] == drug_a) & (df["Drug_B_lower"] == drug_b)) |
        ((df["Drug_A_lower"] == drug_b) & (df["Drug_B_lower"] == drug_a))
    )

    matches = df[mask]
    if matches.empty:
        return None

    # Return highest severity if multiple matches
    matches = matches.copy()
    matches["rank"] = matches["Level"].map(SEVERITY_RANK).fillna(0)
    best = matches.sort_values("rank", ascending=False).iloc[0]

    return {
        "drug_a": drug_a,
        "drug_b": drug_b,
        "severity": best["Level"],
        "severity_rank": int(best["rank"])
    }


def check_all_interactions(ingredients: list[str]) -> list[dict]:
    """
    Check all drug pairs for a patient's medication list.
    ingredients: list of lowercase ingredient names
    Returns list of interactions found, sorted by severity.
    """
    interactions = []
    seen_pairs = set()

    for i in range(len(ingredients)):
        for j in range(i + 1, len(ingredients)):
            a = ingredients[i]
            b = ingredients[j]

            # Skip if same ingredient
            if a == b:
                continue

            # Skip already checked pairs
            pair = tuple(sorted([a, b]))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)

            result = check_interaction(a, b)
            if result:
                interactions.append(result)

    # Sort by severity (highest first)
    interactions.sort(key=lambda x: x["severity_rank"], reverse=True)
    return interactions


# ── Quick test ───────────────────────────────────────────────
if __name__ == "__main__":
    # Test with known interactions from Lou594's meds
    test_pairs = [
        ("clopidogrel", "naproxen"),       # should be Major/Moderate
        ("simvastatin", "amlodipine"),     # should be Moderate
        ("naproxen", "lisinopril"),        # should be Moderate
        ("acetaminophen", "warfarin"),     # should be Moderate
        ("simvastatin", "clopidogrel"),    # should be none/minor
    ]

    print("DDInter Interaction Check Test")
    print("=" * 60)
    for a, b in test_pairs:
        result = check_interaction(a, b)
        if result:
            print(f"✅ {a} + {b} → {result['severity']}")
        else:
            print(f"⬜ {a} + {b} → No interaction found")