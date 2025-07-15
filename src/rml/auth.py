import asyncio
from functools import wraps
from typing import Optional

from dotenv import dotenv_values
from httpx import AsyncClient, Response
from rich.console import Console

from rml.datatypes import (
    AuthResult,
    AuthStatus,
)
from rml.package_config import (
    ENV_FILE_PATH,
    HOST,
    OAUTH_APP_CLIENT_ID,
    RECURSE_API_KEY_NAME,
    SKIP_AUTH,
)
from rml.ui import display_auth_instructions, render_auth_result


async def get_device_code() -> dict:
    """Request device code from GitHub"""
    async with AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/device/code",
            data={
                "client_id": OAUTH_APP_CLIENT_ID,
                "scope": "read:user",
            },
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get device code: {response.status_code}")

        return response.json()


async def poll_for_token(device_code: str, interval: int = 1) -> str:
    """Poll GitHub until user completes authentication

    Args:
        device_code: The device code to use for authentication
        interval: The interval in seconds to poll GitHub

    Returns:
        The access token on success, None on failure
    """
    access_token = None

    async with AsyncClient() as client:
        while access_token is None:
            response = await client.post(
                "https://github.com/login/oauth/access_token",
                data={
                    "client_id": OAUTH_APP_CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                },
                headers={"Accept": "application/json"},
            )

            if response.status_code != 200:
                raise Exception(f"Token request failed: {response.status_code}")

            data = response.json()

            if data.get("access_token"):
                access_token = data["access_token"]
            elif data.get("error") == "authorization_pending":
                await asyncio.sleep(interval)
                continue
            elif data.get("error") == "slow_down":
                interval += 3
                await asyncio.sleep(interval)
                continue
            elif data.get("error") == "expired_token":
                raise Exception("Device code has expired. Please try again.")
            elif data.get("error") == "access_denied":
                raise Exception("User denied authorization request.")
            else:
                raise Exception(
                    f"Unexpected error: {data.get('error', 'Unknown error')}"
                )

        return access_token


async def send_auth_data_to_backend(access_token: str, user_id: int) -> Response:
    """Send auth data to FastAPI backend"""
    async with AsyncClient(timeout=10.0) as client:
        response = await client.post(
            f"{HOST}/api/auth/verify",
            headers={"Authorization": f"Bearer {access_token}"},
            data={"user_id": user_id},
        )
        return response


async def get_user_id(access_token: str) -> int:
    """Get user ID from GitHub using access token"""
    async with AsyncClient(timeout=10.0) as client:
        response = await client.get(
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/vnd.github.v3+json",
            },
        )

        if response.status_code != 200:
            raise Exception(f"Failed to get user ID: {response.status_code}")

        user_data = response.json()
        return user_data["id"]


def store_env_data(data: dict[str, str]):
    """Store key-value pairs in .env.rml file"""
    env_data = dotenv_values(ENV_FILE_PATH)
    env_data = {k: v or "" for k, v in env_data.items()}
    env_data.update(data)
    ENV_FILE_PATH.write_text(
        "\n".join(f"{key}={value}" for key, value in env_data.items())
    )


def get_env_value(key: str) -> Optional[str]:
    """Read a specific value from .env.rml file"""
    env_data = dotenv_values(ENV_FILE_PATH)
    return env_data.get(key)


def is_authenticated() -> bool:
    """Check if user has a stored API key"""
    return get_env_value(RECURSE_API_KEY_NAME) is not None


async def authenticate_with_github(console: Console) -> AuthResult:
    """Main authentication flow with OAuth Device Flow (https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow)"""
    try:
        # Step 1: Get device code
        device_code = await get_device_code()

        # Step 2: User manually completes auth in browser
        display_auth_instructions(
            device_code["verification_uri"],
            device_code["user_code"],
            console=console,
        )

        # Step 3: Poll for access token
        access_token = await poll_for_token(
            device_code["device_code"],
            interval=device_code["interval"],
        )

        # Step 4: Get user ID from GitHub
        user_id = await get_user_id(access_token)

        # Step 5: Send to backend
        console.print("⏳ Syncing with backend ...")
        backend_response = await send_auth_data_to_backend(access_token, user_id)
        if backend_response.status_code == 402:
            return AuthResult(status=AuthStatus.PLAN_REQUIRED)
        elif backend_response.status_code != 200:
            return AuthResult(
                status=AuthStatus.ERROR,
                message="Failed to sync with backend",
            )

        # Step 6: Store API key locally
        response_data = backend_response.json()
        api_key = response_data.get("api_key")
        if not api_key:
            raise Exception("No API key received from backend")

        store_env_data({RECURSE_API_KEY_NAME: api_key})

        return AuthResult(status=AuthStatus.SUCCESS)

    except Exception as e:
        return AuthResult(status=AuthStatus.ERROR, message=str(e))


def require_auth(f):
    """Decorator to ensure user is authenticated before command execution"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        console = Console()

        if not (SKIP_AUTH or is_authenticated()):
            auth_result = asyncio.run(authenticate_with_github(console=console))
            render_auth_result(auth_result, console=console)
            """ TODO (Armin): Uncomment this on 21/07/2025
            if auth_result.status != AuthStatus.SUCCESS:
                sys.exit(1)
            """

        return f(*args, **kwargs)

    return wrapper
