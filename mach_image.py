"""Custom machine image for the detailed equipment information block.

Mirrors the cust_logo upload pattern: a file upload lands as
``mach_image.png`` in the job dir; when the quote state has
``mach_image_enabled``, rendering swaps the listing-scraped
``equipment_details[0].image_url`` for the uploaded image (inline as a
DATA URI, so the headless PDF renderer needs no auth or network).

Unlike logos, the photo is NOT darkened/trimmed — it is a machine photo
and must display exactly like the listing image does.
"""

import base64
import os

MAX_DIM = 900  # keep the data URI reasonable for HTML/PDF embedding


def image_path(job_dir):
    return os.path.join(job_dir, "mach_image.png")


def save_image(data: bytes, job_dir):
    """Normalize a user-uploaded photo and save it as the job's mach_image.png."""
    from io import BytesIO

    from PIL import Image

    img = Image.open(BytesIO(data))
    img.load()
    if img.width > MAX_DIM or img.height > MAX_DIM:
        scale = MAX_DIM / max(img.width, img.height)
        img = img.resize(
            (max(1, int(img.width * scale)), max(1, int(img.height * scale))),
            getattr(Image, "Resampling", Image).LANCZOS,
        )
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGB")
    path = image_path(job_dir)
    img.save(path, "PNG")
    return path


def save_data_uri(data_uri: str, job_dir):
    """Decode a data: URI from the intake UI and save it."""
    _, _, payload = data_uri.partition(",")
    if not payload:
        raise ValueError("bad data_uri")
    return save_image(base64.b64decode(payload), job_dir)


def apply(data, job_dir):
    """If enabled and the file exists, replace the scraped equipment image
    with the uploaded one (DATA URI) so the markup stays identical."""
    if not data.get("mach_image_enabled"):
        return False
    p = image_path(job_dir)
    if not os.path.isfile(p):
        return False
    if data.get("equipment_details") is None:
        data["equipment_details"] = [{}]
    details = data["equipment_details"]
    if not details:
        details.append({})
    with open(p, "rb") as f:
        details[0]["image_url"] = "data:image/png;base64," + base64.b64encode(f.read()).decode("ascii")
    return True
