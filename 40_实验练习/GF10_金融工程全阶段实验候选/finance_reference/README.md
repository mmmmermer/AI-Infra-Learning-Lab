# Finance Reference

Verified reference code for the corrected F02, GF05, and GF07 experiments. The
development lock also pins scikit-learn for the executable GF07 classification
path; the current suite contains nine tests.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.lock
python -m pip install -e .
python -m pytest -q
```

This is an AI-assisted reference implementation. It is not learner-owned work and does not provide investment advice.
