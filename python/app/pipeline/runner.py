import logging
import time
from pathlib import Path

from app.pipeline.segmentation import GarmentSegmenter, SegmentationError
from app.pipeline.inpainting import GhostInpainter, InpaintingError
from app.pipeline.mesh import MeshGenerator, MeshGenerationError
from app.utils import file_io

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(self) -> None:
        self._segmenter = GarmentSegmenter()
        self._inpainter = GhostInpainter()
        self._mesh_generator = MeshGenerator()

    def run(self, job_id: str, image_path: Path) -> dict:
        start = time.monotonic()

        try:
            logger.info("Stage segmentation start", extra={"job_id": job_id})
            mask_path = self._segmenter.segment(image_path, job_id)
        except SegmentationError as e:
            return self._error_result(job_id, "failed:segmentation", e, start)

        try:
            logger.info("Stage inpainting start", extra={"job_id": job_id})
            inpainted_path = self._inpainter.inpaint(image_path, mask_path, job_id)
        except InpaintingError as e:
            return self._error_result(job_id, "failed:inpainting", e, start)

        try:
            logger.info("Stage mesh start", extra={"job_id": job_id})
            glb_path = self._mesh_generator.generate(inpainted_path, job_id)
        except MeshGenerationError as e:
            return self._error_result(job_id, "failed:mesh_generation", e, start)

        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.info("Pipeline complete", extra={"job_id": job_id, "duration_ms": elapsed_ms})
        return {
            "job_id": job_id,
            "status": "completed",
            "glb_path": str(glb_path),
            "duration_ms": elapsed_ms,
        }

    def _error_result(self, job_id: str, status: str, exc: Exception, start: float) -> dict:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        logger.error("Pipeline failed | status=%s", status, extra={"job_id": job_id}, exc_info=True)
        return {
            "job_id": job_id,
            "status": status,
            "error": str(exc),
            "duration_ms": elapsed_ms,
        }
