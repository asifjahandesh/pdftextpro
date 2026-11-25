import os
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
_BACKEND_ENV = Path(__file__).resolve().parents[1] / ".env"
if _BACKEND_ENV.is_file():
    load_dotenv(_BACKEND_ENV, override=True)

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND", "").strip().lower()
R2_ENDPOINT_URL = os.getenv("R2_ENDPOINT_URL", "").strip()
R2_ACCESS_KEY_ID = os.getenv("R2_ACCESS_KEY_ID", "").strip()
R2_SECRET_ACCESS_KEY = os.getenv("R2_SECRET_ACCESS_KEY", "").strip()
R2_BUCKET = os.getenv("R2_BUCKET", "").strip()


def r2_enabled() -> bool:
    if STORAGE_BACKEND == "local":
        return False
    if STORAGE_BACKEND == "r2":
        if not (R2_ENDPOINT_URL and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET):
            raise RuntimeError(
                "STORAGE_BACKEND=r2 requires R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, "
                "R2_SECRET_ACCESS_KEY, and R2_BUCKET."
            )
        return True
    return bool(R2_ENDPOINT_URL and R2_ACCESS_KEY_ID and R2_SECRET_ACCESS_KEY and R2_BUCKET)


def _r2_client():
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT_URL,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )


def test_r2_connection() -> bool:
    """Verify R2 bucket connectivity using head_bucket."""
    if not r2_enabled():
        return False
    _r2_client().head_bucket(Bucket=R2_BUCKET)
    return True


def upload_to_r2_if_enabled(local_path: Path, object_key: str) -> str:
    """Upload local_path to R2 if configured and return 'r2://<key>'; otherwise return local_path."""
    if not r2_enabled():
        return str(local_path)
    _r2_client().upload_file(
        str(local_path),
        R2_BUCKET,
        object_key,
        ExtraArgs={"ContentType": "application/pdf"},
    )
    local_path.unlink(missing_ok=True)
    return f"r2://{object_key}"


def download_for_processing(stored_path: str) -> tuple[str, bool]:
    """Return (local_file_path, is_temp) for PyMuPDF processing."""
    if stored_path.startswith("r2://"):
        key = stored_path[5:]
        tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False)
        tmp.close()
        _r2_client().download_file(R2_BUCKET, key, tmp.name)
        return tmp.name, True
    if not os.path.isfile(stored_path):
        raise FileNotFoundError(f"Stored PDF file not found or inaccessible: {stored_path}")
    return stored_path, False


def delete_stored_file(stored_path: str) -> None:
    if not stored_path:
        return
    if stored_path.startswith("r2://"):
        if r2_enabled():
            _r2_client().delete_object(Bucket=R2_BUCKET, Key=stored_path[5:])
        return
    try:
        Path(stored_path).unlink(missing_ok=True)
    except OSError:
        pass
