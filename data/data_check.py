import glob, pandas as pd

for f in sorted(glob.glob("data/synthetic/**/*.*", recursive=True)):
    if f.endswith(".csv"):
        df = pd.read_csv(f)
        print(f"{f} | rows={len(df)} | cols={list(df.columns)}")
    else:
        print(f"{f} (non-CSV)")