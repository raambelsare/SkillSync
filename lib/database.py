import os
import warnings
warnings.filterwarnings("ignore")
import httpx
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from supabase import create_client, Client

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=_env_path, override=True)

def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    client = create_client(url, key)
    # Ensure Gotrue auth client has adequate timeout (default 5.0s is too short for slower connections)
    if hasattr(client, "auth") and hasattr(client.auth, "_http_client"):
        client.auth._http_client.timeout = httpx.Timeout(30.0)
    return client

supabase = get_supabase()

