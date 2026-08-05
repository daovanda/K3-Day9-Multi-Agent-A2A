from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT_DIR / "data"
INPUT_DIR = ROOT_DIR / "input"
OUTPUT_DIR = ROOT_DIR / "output"
LOGGING_DIR = ROOT_DIR / "logging"

# The lab requires the model name to be declared in source code, not .env.
MODEL_NAME = "gpt-4o-mini"
MODEL_PARAMETER_SIZE = "not publicly disclosed by OpenAI"
DECISION_CONFIDENCE = 0.99
POLICY_VERSION = "EC_POLICY_V1"
CURRENCY = "BRL"
PAYMENT_TOLERANCE_BRL = "0.10"
