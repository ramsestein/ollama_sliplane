# Evaluation

Pukara's anonymization engine is the detection pipeline of carmina3, a Spanish
clinical-text de-identification suite that combines:

- **BERT** (`bsc-bio-ehr-es-carmen-anon`) — multiclass token classification.
- **Regex rules** — dates, times, phones, names, addresses, etc.

Its calibrated strategy was evaluated on the **CARMEN** test set
(2,000 documents).

## Word level (PHI vs non-PHI)

| Dataset | Documents | Precision | Recall | F1 |
|---|---|---|---|---|
| MedDocAn (validation) | 100 | 0.875 | 0.940 | 0.906 |
| **CARMEN (test)** | **2000** | **0.930** | **0.919** | **0.924** |

## Document level (CARMEN test)

- **Macro F1** (mean per document): **0.724**.
- **Leakage**: documents with at least one missed PHI among critical tags
  (`EMAIL`, `FAMILY`, `NAME`, `ID`, `PHONE`, `URL`, `PROFESSIONAL`):
  **49 / 2000 (2.5%)**.

## Throughput

- CARMEN (2,000 documents): **5 min 04 s** of processing (detection +
  substitution), without parallelization.

## Notes

- The evaluation is binary at word level (PHI vs non-PHI); the concrete label
  is assigned by BERT.
