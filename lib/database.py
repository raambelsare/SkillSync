import os
import warnings
warnings.filterwarnings("ignore")
from dotenv import load_dotenv
# pyrefly: ignore [missing-import]
from supabase import create_client, Client

_env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
load_dotenv(dotenv_path=_env_path, override=True)

def get_supabase() -> Client:
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    return create_client(url, key)

supabase = get_supabase()

