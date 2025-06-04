import asyncio
import time
from functools import wraps
from typing import Optional

import click
import httpx
from dotenv import dotenv_values
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from rml.datatypes import (
    AuthResult,
    AuthStatus,
)
from rml.package_config import (
    ENV_FILE_PATH,
    GITHUB_ACCESS_TOKEN_KEYNAME,
    GITHUB_USER_ID_KEYNAME,
    HOST,
    OAUTH_APP_CLIENT_ID,
)

console = Console()


async def get_device_code() -> Optional[dict]:
    """Request device code from GitHub"""
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://github.com/login/device/code",
            data={
                "client_id": OAUTH_APP_CLIENT_ID,
                "scope": "read:user",
            },
            headers={"Accept": "application/json"},
        )

        if response.status_code != 200:
            error_msg = f"Failed to get device code: {response.status_code}"
            console.print(f"[bold red]❌ {error_msg}[/bold red]")
            return None

        return response.json()


def display_user_instructions(verification_uri: str, user_code: str) -> None:
    """Show user what to do with Rich formatting"""
    panel = Panel(
        f"[bold blue]GitHub Authentication Required[/bold blue]\n\n"
        f"1. Open this link in your browser: [link]{verification_uri}[/link]\n"
        f"2. Enter this code: [bold green]{user_code}[/bold green]\n"
        f"[dim]Waiting for authorization...[/dim]",
        title="🔐 Authentication",
        border_style="blue",
    )
    console.print(panel)


async def poll_for_token(device_code: str, interval: int = 3) -> Optional[str]:
    """Poll GitHub until user completes authentication

    Args:
        device_code: The device code to use for authentication
        interval: The interval in seconds to poll GitHub

    Returns:
        The access token on success, None on failure
    """
    start_time = time.time()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Waiting for GitHub authorization...", total=None)

        async with httpx.AsyncClient() as client:
            while True:
                elapsed = int(time.time() - start_time)
                progress.update(
                    task,
                    description=f"Waiting for GitHub authorization... ({elapsed}s)",
                )

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
                    error_msg = f"Token request failed: {response.status_code}"
                    console.print(f"[bold red]❌ {error_msg}[/bold red]")
                    return None

                data = response.json()

                if data.get("access_token"):
                    return data["access_token"]
                elif data.get("error") == "authorization_pending":
                    await asyncio.sleep(interval)
                    continue
                elif data.get("error") == "slow_down":
                    interval += 5
                    await asyncio.sleep(interval)
                    continue
                elif data.get("error") == "expired_token":
                    error_msg = "Device code has expired. Please try again."
                    console.print(f"[bold red]❌ {error_msg}[/bold red]")
                    return None
                elif data.get("error") == "access_denied":
                    error_msg = "User denied authorization request."
                    console.print(f"[bold red]❌ {error_msg}[/bold red]")
                    return None
                else:
                    error_msg = (
                        f"Unexpected error: {data.get('error', 'Unknown error')}"
                    )
                    console.print(f"[bold red]❌ {error_msg}[/bold red]")
                    return None


async def send_to_backend(access_token: str, user_id: str) -> bool:
    """Send auth data to FastAPI backend"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{HOST}/api/v1/auth/github/store",
                json={"user_id": user_id},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {access_token}",
                },
            )
            return response.status_code == 200
    except Exception as e:
        console.print(f"[yellow]Backend communication failed: {e}[/yellow]")
        return False


async def get_user_id(access_token: str) -> Optional[str]:
    """Get user ID from GitHub using access token"""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "https://api.github.com/user",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/vnd.github.v3+json",
                },
            )

            if response.status_code != 200:
                console.print(
                    f"[red]Failed to get user info: {response.status_code}[/red]"
                )
                return None

            user_data = response.json()
            return str(user_data.get("id"))

    except Exception as e:
        console.print(f"[yellow]Failed to get user ID: {e}[/yellow]")
        return None


def store_env_data(data: dict[str, str]):
    """Store key-value pairs in .env.rml file"""
    env_data = dotenv_values(ENV_FILE_PATH)
    env_data = {k: v or "" for k, v in env_data.items()}
    env_data.update(data)
    ENV_FILE_PATH.write_text(
        "\n".join(f"{key}={value}" for key, value in env_data.items())
    )


def get_env_data() -> dict[str, str]:
    """Read all data from .env.rml file"""
    env_data = dotenv_values(ENV_FILE_PATH)
    return {k: v or "" for k, v in env_data.items() if v}


def get_env_value(key: str) -> Optional[str]:
    """Read a specific value from .env.rml file"""
    env_data = dotenv_values(ENV_FILE_PATH)
    return env_data.get(key)


def clear_env_data(keys: Optional[list[str]] = None):
    """Remove specified keys from .env.rml file, or clear all if no keys specified"""
    env_data = dotenv_values(ENV_FILE_PATH)
    env_data = {k: v or "" for k, v in env_data.items()}

    if keys is None:
        env_data.clear()
    else:
        for key in keys:
            env_data.pop(key, None)

    ENV_FILE_PATH.write_text(
        "\n".join(f"{key}={value}" for key, value in env_data.items())
    )


def is_authenticated() -> bool:
    """Check if user has a stored token"""
    return get_env_value(GITHUB_ACCESS_TOKEN_KEYNAME) is not None


async def authenticate_with_github() -> AuthResult:
    """Main authentication flow with OAuth Device Flow (https://docs.github.com/en/apps/oauth-apps/building-oauth-apps/authorizing-oauth-apps#device-flow)"""
    try:
        existing_token = get_env_value(GITHUB_ACCESS_TOKEN_KEYNAME)
        if existing_token:
            console.print("[yellow]⚠️  You already have stored credentials.[/yellow]")
            if not click.confirm(
                "Proceeding will overwrite your existing credentials. Continue?",
                default=False,
            ):
                return AuthResult(
                    status=AuthStatus.CANCELLED,
                    error_message="Authentication cancelled - existing credentials preserved",
                )

        # Step 1: Get device code
        device_code = await get_device_code()
        if not device_code:
            return AuthResult(
                status=AuthStatus.ERROR, error_message="Failed to get device code"
            )

        # Step 2: Display user instructions
        display_user_instructions(
            device_code["verification_uri"], device_code["user_code"]
        )

        # Step 3: Poll for access token
        access_token = await poll_for_token(
            device_code["device_code"], device_code["interval"]
        )
        if not access_token:
            return AuthResult(
                status=AuthStatus.ERROR, error_message="Failed to get access token"
            )

        # Step 4: Get user ID from GitHub
        user_id = await get_user_id(access_token)
        if not user_id:
            return AuthResult(
                status=AuthStatus.ERROR, error_message="Failed to get user ID"
            )

        # Step 5: Send to backend
        backend_success = await send_to_backend(access_token, user_id)
        if not backend_success:
            error_msg = "Failed to sync with backend - authentication failed"
            console.print(f"[bold red]❌ {error_msg}[/bold red]")
            return AuthResult(status=AuthStatus.ERROR, error_message=error_msg)

        # Step 6: Store locally
        store_env_data(
            {GITHUB_ACCESS_TOKEN_KEYNAME: access_token, GITHUB_USER_ID_KEYNAME: user_id}
        )

        console.print("[bold green]✅ Authentication successful![/bold green]")
        return AuthResult(status=AuthStatus.SUCCESS, access_token=access_token)

    except Exception as e:
        error_msg = f"Authentication failed: {str(e)}"
        console.print(f"[bold red]❌ {error_msg}[/bold red]")
        return AuthResult(status=AuthStatus.ERROR, error_message=error_msg)


def require_auth(f):
    """Decorator to ensure user is authenticated before command execution"""

    @wraps(f)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            click.echo("Authentication required. Running login flow...")
            result = asyncio.run(authenticate_with_github())
            if result.status != AuthStatus.SUCCESS:
                click.echo("Authentication failed.", err=True)
                raise click.Abort()
        return f(*args, **kwargs)

    return wrapper
