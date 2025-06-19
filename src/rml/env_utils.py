import os
from pathlib import Path

from dotenv import dotenv_values

REQUIRED_ENV_VARS = [
    "RECURSE_INSTALL_URL",
    "VERSION_CHECK_URL",
    "BACKEND_URL",
    "OAUTH_APP_CLIENT_ID",
    "RML_ENV_FILE",
    "RML_LOG_LEVEL",
]


def validate_envs() -> None:
    missing = [var for var in REQUIRED_ENV_VARS if not os.getenv(var)]
    if missing:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(missing)}"
        )


def get_rml_env_path() -> Path:
    env_file = os.getenv("RML_ENV_FILE", ".env.rml")
    return Path(env_file).resolve()


def update_rml_env(data: dict[str, str]):
    """Updates key-value pairs in the environment file defined by RML_ENV_FILE

    Args:
        data: A dictionary containing key-value pairs to update in the environment file.
    """
    env_path = get_rml_env_path()
    env_data = dotenv_values(env_path)
    env_data = {k: v or "" for k, v in env_data.items()}
    env_data.update(data)
    env_path.write_text("\n".join(f"{key}={value}" for key, value in env_data.items()))


def get_rml_env_value(key: str) -> str | None:
    """Gets the value of a key from the environment file defined by RML_ENV_FILE

    Args:
        key: The key to retrieve the value for.

    Returns:
        The value associated with the key, or None if the key does not exist.
    """
    env_path = get_rml_env_path()
    env_data = dotenv_values(env_path)
    return env_data.get(key, None)
