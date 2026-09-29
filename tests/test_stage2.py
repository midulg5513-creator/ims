# -*- coding: utf-8 -*-
from __future__ import annotations

import csv
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf

from build_stage2_data import prior_features
from econometric_stage2 import MAIN, covariance
from prospective_study import build_t0_snapshot, proportional_sample
from stage2_common import (
    canonical_snapshots, cohen_kappa, ensure_csv, load_config, quota_available,
    within_window,
)


class Stage2Tests(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.created = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

    def test_snapshot_boundaries(self):
        valid, delta = within_window(
            datetime(2026, 9, 21, 2, 0, tzinfo=timezone.utc),
            self.created, "T24H", self.config,
        )
        self.assertTrue(valid)
        self.assertEqual(delta, 2.0)
        invalid, _ = within_window(
            datetime(2026, 9, 21, 2, 0, 1, tzinfo=timezone.utc),
            self.created, "T24H", self.config,
        )
        self.assertFalse(invalid)

    def test_canonical_prefers_closest_valid_success(self):
        rows = [
            {"post_id": "1", "scheduled_window": "T24H", "request_status": "error",
             "within_tolerance": "0", "delta_hours": "0.0", "observed_at": "a"},
            {"post_id": "1", "scheduled_window": "T24H", "request_status": "success",
             "within_tolerance": "1", "delta_hours": "1.5", "observed_at": "b"},
            {"post_id": "1", "scheduled_window": "T24H", "request_status": "success",
             "within_tolerance": "1", "delta_hours": "0.2", "observed_at": "c"},
        ]
        selected = canonical_snapshots(rows)
        self.assertEqual(selected[("1", "T24H")]["observed_at"], "c")

    def test_t0_keeps_real_zero_counts(self):
        row = build_t0_snapshot(
            "p", "2026-09-20T00:00:00Z", "2026-09-20T01:00:00Z", 0, 0, 0,
            self.config,
        )
        self.assertEqual(row["request_status"], "success")
        self.assertEqual(row["reposts_count"], 0)
        self.assertEqual(row["within_tolerance"], 1)

    def test_quota_is_not_silently_substituted(self):
        included = [
            {"industry": "beauty", "account_type": "media_other", "status": "included"}
            for _ in range(20)
        ]
        self.assertFalse(quota_available("beauty", "media_other", included, self.config))
        self.assertTrue(quota_available("beauty", "brand_official", included, self.config))

    def test_formal_sampling_mode_is_keyword_quota(self):
        self.assertEqual(self.config["study"]["sampling_mode"], "keyword_quota_fast24h")
        self.assertEqual(
            sum(self.config["account_type_targets_per_industry"].values()), 100
        )

    def test_history_excludes_target_and_future(self):
        rows = [
            {"created_at": "2026-09-19T00:00:00Z", "reposts": "2", "comments": "3",
             "attitudes": "5", "ad_tag": "0", "kol_kw": "0", "has_link": "0",
             "has_video": "0"},
            {"created_at": "2026-09-20T00:00:00Z", "reposts": "100", "comments": "100",
             "attitudes": "100", "ad_tag": "1", "kol_kw": "0", "has_link": "0",
             "has_video": "0"},
            {"created_at": "2026-09-21T00:00:00Z", "reposts": "100", "comments": "100",
             "attitudes": "100", "ad_tag": "1", "kol_kw": "0", "has_link": "0",
             "has_video": "0"},
        ]
        result = prior_features(rows, self.created)
        self.assertEqual(result["hist_prior_n"], 1)
        self.assertEqual(result["prior_nonad_n"], 1)

    def test_kappa_and_deterministic_sample(self):
        self.assertAlmostEqual(cohen_kappa(["1", "0", "1"], ["1", "0", "1"]), 1.0)
        rows = [
            {"post_id": str(i), "industry": "beauty" if i < 5 else "food",
             "account_type": "brand_official"} for i in range(10)
        ]
        first = proportional_sample(rows, 6, 20260920)
        second = proportional_sample(rows, 6, 20260920)
        self.assertEqual([r["post_id"] for r in first], [r["post_id"] for r in second])

    def test_schema_init_does_not_overwrite_existing_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "data.csv"
            ensure_csv(path, ["id", "value"])
            with path.open("a", encoding="utf-8-sig", newline="") as f:
                csv.writer(f).writerow(["1", "kept"])
            ensure_csv(path, ["id", "value"])
            with path.open(encoding="utf-8-sig", newline="") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows, [{"id": "1", "value": "kept"}])

    def test_stage2_primary_formulas_fit(self):
        rng = np.random.default_rng(20260920)
        n = 180
        d = pd.DataFrame({
            "author_id": [f"a{i}" for i in range(n)],
            "log_followers": rng.normal(9, 1, n),
            "hist_prior": rng.normal(3, 0.5, n),
            "has_prior_hist": rng.integers(0, 2, n),
            "text_len_100": rng.uniform(0.2, 3.0, n),
            "n_images": rng.integers(0, 10, n),
            "is_video": rng.integers(0, 2, n),
            "is_lottery": rng.integers(0, 2, n),
            "hard_ad": rng.integers(0, 2, n),
            "promo_density_100": rng.uniform(0, 3, n),
            "brand_density_100": rng.uniform(0, 3, n),
            "has_ext_link": rng.integers(0, 2, n),
            "log_age_hours_24h": rng.normal(np.log1p(24), 0.01, n),
            "industry": rng.choice(["beauty", "food", "electronics"], n),
            "account_type": rng.choice(["brand_official", "kol_verified", "media_other"], n),
            "pub_dow": np.arange(n) % 7,
            "source_group": rng.choice(["client", "web", "other"], n),
            "appeal_family": rng.choice(["welfare", "content", "hard_ad", "other"], n),
        })
        d["text_len_100_sq"] = d["text_len_100"] ** 2
        mu = np.exp(-2 + 0.22 * d["log_followers"] + 0.15 * d["is_lottery"])
        d["reposts_24h"] = rng.poisson(mu)
        d["ln_repost_24h"] = np.log1p(d["reposts_24h"])
        glm = smf.glm("reposts_24h ~ " + MAIN, data=d, family=sm.families.Poisson()).fit(
            cov_type="HC3"
        )
        self.assertTrue(np.isfinite(glm.params).all())
        hetero = smf.ols(
            "ln_repost_24h ~ " + MAIN + " + C(appeal_family) + "
            "C(appeal_family):(log_followers + text_len_100 + n_images + is_video + is_lottery)",
            data=d,
        ).fit(cov_type="HC3")
        self.assertTrue(any("appeal_family" in term for term in hetero.params.index))
        self.assertEqual(covariance(d)[2], "HC3")


if __name__ == "__main__":
    unittest.main()
