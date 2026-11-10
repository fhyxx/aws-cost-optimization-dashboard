# Dashboard screenshots

These four PNGs are supplied captures of the running Streamlit application using synthetic demonstration data. Each image is 1366 × 768 and represents a desktop viewport.

- `dashboard-overview.png` shows the executive dashboard overview.
- `spend-trends.png` shows monthly spend trends and service mix.
- `anomaly-review.png` shows the anomaly review section. It predates the current anomaly-ranking correction, so it does not demonstrate the current anomaly/recommendation selection logic.
- `recommendations.png` shows optimization recommendations and export controls.

Mobile visual review was completed on 10 November 2026 using four user-supplied phone screenshots of the deployed app. The phone captures are not included in this repository; the four PNGs listed above remain desktop-only evidence.

In the supplied desktop anomaly-review and recommendations captures, the wide data tables extend beyond the right edge of the viewport, so some columns are not visible. The mobile review also found that long anomaly/recommendation tables require horizontal scrolling and can initially show truncated columns; this is a known usability limitation, not a data-calculation defect. The anomaly-review screenshot also predates the current distinction between `change_usd` and `anomaly_increase_usd`; it is historical visual evidence, not proof of the current anomaly ranking or current table contents. The overview and spend-trend charts are readable in the captured area; lower content in the overview continues below the viewport.
