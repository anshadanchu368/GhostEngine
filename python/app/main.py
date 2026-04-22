import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, Response

from app.pipeline.runner import PipelineRunner
from app.utils import file_io, vram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="GhostFabric ML Bridge", version="1.0.0")

_runner = PipelineRunner()

_ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png"}
_MAX_FILE_SIZE_BYTES = 50 * 1024 * 1024


@app.post("/process")
async def process_image(image: UploadFile = File(...)) -> JSONResponse:
    if image.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail="Unsupported media type. Use image/jpeg or image/png.",
        )

    content: bytes = await image.read()

    if len(content) > _MAX_FILE_SIZE_BYTES:
        raise HTTPException(
            status_code=413,
            detail="File too large. Maximum 50MB.",
        )

    job_id: str = str(uuid.uuid4())
    image_path: Path = file_io.save_upload(
        job_id, image.filename or f"{job_id}.jpg", content
    )

    logger.info("Job received", extra={"job_id": job_id})

    result = _runner.run(job_id, image_path)

    if result["status"] != "completed":
        return JSONResponse(content=result, status_code=200)

    glb_path = Path(result["glb_path"])
    glb_bytes = glb_path.read_bytes()
    shutil.rmtree(glb_path.parent, ignore_errors=True)
    return Response(content=glb_bytes, media_type="model/gltf-binary")


@app.get("/health")
async def health_check() -> dict:
    return {
        "status": "ok",
        "gpu_available": vram.is_gpu_available(),
        "vram_free_gb": round(vram.get_vram_free_gb(), 2),
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, workers=1)
