"""Create the synthetic campaign file data/campaign.csv (30 days x 6 ad sets).

Run once:  python data/make_campaign.py      (seed 42, so the output is identical every time)

Each ad set has a "true" daily budget, cost per 1,000 impressions (CPM), click rate (CTR),
conversion rate (CVR) and average order value. Daily numbers are drawn around those values
with random noise. The six ad sets are designed to be clearly different:

- vitc-ar-stories      clearly good (high return on ad spend)
- vitc-en-igfeed       good
- spf-en-fbfeed-broad  clearly bad (broad audience, few purchases)
- nightcream-fr-retarget  good at first, then the click rate falls (ad fatigue)
- cleanser-ar-fbfeed-lal  weak (below break-even)
- eyepatch-en-reels-test  small test budget: too few purchases to judge

All numbers are invented. Lumi Skin is a fictional shop. Currency: AED.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
START = date(2026, 9, 8)
DAYS = 30

AD_SETS = [
    # ctr_start -> ctr_end: the click rate moves linearly between these values,
    # starting on day `decline_from` (0 = from the first day).
    dict(ad_set_id="vitc-ar-stories", ad_set_name="Vitamin C Serum | Arabic | Stories",
         product="Vitamin C Brightening Serum", language="ar", placement="stories",
         audience="Women 25-44, UAE", budget=300, cpm=24, ctr_start=0.016, ctr_end=0.019,
         decline_from=0, cvr=0.035, order_value=190),
    dict(ad_set_id="vitc-en-igfeed", ad_set_name="Vitamin C Serum | English | IG Feed",
         product="Vitamin C Brightening Serum", language="en", placement="instagram_feed",
         audience="Women 25-44, UAE", budget=250, cpm=30, ctr_start=0.014, ctr_end=0.014,
         decline_from=0, cvr=0.04, order_value=185),
    dict(ad_set_id="spf-en-fbfeed-broad", ad_set_name="Sun Stick SPF 50+ | English | FB Feed",
         product="Sun Stick SPF 50+", language="en", placement="facebook_feed",
         audience="Broad 18-65, UAE", budget=350, cpm=14, ctr_start=0.006, ctr_end=0.006,
         decline_from=0, cvr=0.012, order_value=95),
    dict(ad_set_id="nightcream-fr-retarget",
         ad_set_name="Squalane Night Cream | French | Retargeting",
         product="Squalane Night Cream", language="fr", placement="instagram_feed",
         audience="Site visitors (30 days)", budget=120, cpm=35, ctr_start=0.024, ctr_end=0.010,
         decline_from=14, cvr=0.05, order_value=160),
    dict(ad_set_id="cleanser-ar-fbfeed-lal", ad_set_name="Gentle Foam Cleanser | Arabic | FB Feed",
         product="Gentle Foam Cleanser", language="ar", placement="facebook_feed",
         audience="Lookalike 1% of buyers, UAE", budget=200, cpm=16, ctr_start=0.009,
         ctr_end=0.009, decline_from=0, cvr=0.025, order_value=75),
    dict(ad_set_id="eyepatch-en-reels-test", ad_set_name="Hydrogel Eye Patches | English | Reels",
         product="Hydrogel Eye Patches (30 pairs)", language="en", placement="reels",
         audience="Interest test: travel, UAE", budget=20, cpm=12, ctr_start=0.012,
         ctr_end=0.012, decline_from=0, cvr=0.02, order_value=150),
]


def click_rate(ad_set: dict, day: int) -> float:
    start, end, from_day = ad_set["ctr_start"], ad_set["ctr_end"], ad_set["decline_from"]
    if day < from_day:
        return start
    progress = (day - from_day) / (DAYS - 1 - from_day)
    return start + (end - start) * progress


def make_rows(rng: np.random.Generator) -> list[dict]:
    rows = []
    for day in range(DAYS):
        for ad_set in AD_SETS:
            spend = ad_set["budget"] * rng.uniform(0.92, 1.03)
            impressions = int(spend / ad_set["cpm"] * 1000 * rng.lognormal(0, 0.08))
            clicks = int(rng.binomial(impressions, click_rate(ad_set, day)))
            purchases = int(rng.binomial(clicks, ad_set["cvr"]))
            mean_value = ad_set["order_value"]
            order_values = rng.normal(mean_value, mean_value * 0.15, purchases)
            rows.append(
                {
                    "date": (START + timedelta(days=day)).isoformat(),
                    "ad_set_id": ad_set["ad_set_id"],
                    "ad_set_name": ad_set["ad_set_name"],
                    "product": ad_set["product"],
                    "language": ad_set["language"],
                    "placement": ad_set["placement"],
                    "audience": ad_set["audience"],
                    "spend_aed": round(spend, 2),
                    "impressions": impressions,
                    "clicks": clicks,
                    "purchases": purchases,
                    "revenue_aed": round(float(order_values.clip(min=0).sum()), 2),
                }
            )
    return rows


def main() -> None:
    rng = np.random.default_rng(SEED)
    frame = pd.DataFrame(make_rows(rng))
    out = Path(__file__).parent / "campaign.csv"
    frame.to_csv(out, index=False)
    print(f"Wrote {len(frame)} rows to {out}")


if __name__ == "__main__":
    main()
