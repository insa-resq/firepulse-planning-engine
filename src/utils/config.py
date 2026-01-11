import os

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv(dotenv_path=".env")

class _Settings(BaseSettings):
    APP_NAME: str = "Firepulse Planning Engine API"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 9000

    REMOTE_API_BASE_URL: str = os.getenv("REMOTE_API_BASE_URL")
    REMOTE_API_EMAIL: str = os.getenv("REMOTE_API_EMAIL")
    REMOTE_API_PASSWORD: str = os.getenv("REMOTE_API_PASSWORD")

    REMOTE_API_AUTH_TOKEN_REFRESH_INTERVAL_SECONDS: int = 5 * 60 * 60 # 5 hours

settings = _Settings()
