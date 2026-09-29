# -*- coding: utf-8 -*-
import numpy as np, pandas as pd, sys
sys.path.insert(0, r"d:\AI\爬虫")

df = pd.read_csv(r"d:\AI\爬虫\stata_ads3.csv", encoding="utf-8")
print("shape:", df.shape)
for c in ["ln_repost", "reposts", "ln_followers", "text_len", "n_pics", "is_lottery",
          "has_prior_hist", "hist_prior_lnengage0", "ln_age_hours"]:
    if c in df.columns:
        s = df[c]
        print(f"{c:<24} dtype={str(s.dtype):<8} n={s.notna().sum():<4} "
              f"mean={s.mean():.6f} std={s.std(ddof=1):.6f} min={s.min()} max={s.max()} uniq={s.nunique()}")
    else:
        print(f"{c:<24} *** MISSING ***")
print()
print("columns:", list(df.columns))
print()
# 手工 M0 规格，看列是否被丢
cont = ["ln_followers", "text_len", "n_pics", "is_lottery"]
Xraw = np.column_stack([np.ones(len(df))] + [df[c].to_numpy(float) for c in cont])
names = ["_cons"] + cont
print("Xraw shape:", Xraw.shape)
for i, n in enumerate(names):
    print(f"  {i} {n:<16} std={Xraw[:, i].std():.6f}")
