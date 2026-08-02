import sys
from pathlib import Path

# evals/ sits next to sieve_agent/, not inside it — make both importable when
# running `pytest evals` from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
