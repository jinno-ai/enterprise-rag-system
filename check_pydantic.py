from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional

class Settings(BaseSettings):
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

try:
    settings = Settings(_env_file=None)
    print("Settings initialized")
except Exception as e:
    print(f"Error: {e}")
