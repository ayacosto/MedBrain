import json
from pathlib import Path
from collections import Counter

fhir_files = list(Path("Patients/output/fhir").glob("*.json"))
counter = Counter()

for f in fhir_files:
    bundle = json.load(open(f, encoding="utf-8"))
    for entry in bundle.get("entry", []):
        rt = entry.get("resource", {}).get("resourceType")
        if rt:
            counter[rt] += 1

for rt, count in counter.most_common():
    print(f"{rt}: {count}")