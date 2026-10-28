# Trained risk models (generated, gitignored)

`Backend/scripts/train_risk_model.py` writes here:

- `ibtracs_training.csv` — auditable labeled training rows (real IBTrACS fixes)
- `<leader-model>.zip` — the H2O AutoML leader model directory/file
- `model_card.json` — model id, metrics, label definition, provenance

Point `H2O_MODEL_PATH` at the saved model to enable severity-probability
scoring in `disaster_intelligence`. Without it, the API honestly reports
the probability as unavailable.
