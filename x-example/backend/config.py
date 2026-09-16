import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")


GEE_PROJECT_ID = os.getenv("GEE_PROJECT_ID", "ee-jeli0026")


def parse_cors_origins():
    raw = os.getenv(
        "CORS_ORIGINS",
        "http://127.0.0.1:5500,http://localhost:5500"
    )

    return [
        origin.strip()
        for origin in raw.split(",")
        if origin.strip()
    ]


CORS_ORIGINS = parse_cors_origins()