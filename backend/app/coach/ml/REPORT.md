# Learned marathon predictor: evaluation

Data: BMClab long-distance running dataset, 25263 marathons from 16778 runners. 5-fold cross-validation grouped by runner. Errors in minutes.

| Method | MAE | Median abs. error | MAE on common races | Races |
| --- | --- | --- | --- | --- |
| GBM | 14.4 | 10.4 | 14.4 | 25263 |
| Ridge | 15.2 | 11.2 | 15.2 | 25263 |
| Riegel | 16.5 | 11.2 | 16.5 | 25263 |
| VDOT | 16.7 | 11.3 | 16.7 | 25263 |
| Tanda | 19.5 | 14.2 | 19.5 | 25263 |

10th–90th percentile range: covers 77% of real times (target 80%), 42 minutes wide on average.

Chosen: **GBM**. It beats the best formula (Riegel) on the same races.

Reproduce: `python -m app.coach.ml.train --data run_ww_2019_d.parquet run_ww_2020_d.parquet` (seeded, so the numbers match).

Data: Afonseca, L., Watanabe, R. N. & Duarte, M. (2021). *A public dataset on long-distance running training in 2019 and 2020.* figshare. https://doi.org/10.6084/m9.figshare.16620238.v5 (CC BY 4.0).
