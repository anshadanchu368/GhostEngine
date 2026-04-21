"""SAM 2.1 garment segmentation pipeline stage.

Stage 1 of 3: SAM -> Stable Diffusion -> TripoSR

Accepts a garment image and returns a binary mask PNG identifying the
dominant foreground garment using Segment Anything Model 2 (SAM 2.1).
"""

import gc
import logging
import os
from pathlib import Path

import numpy as np
from PIL import Image
import torch

from app.utils import file_io

logger = logging.getLogger(__name__)

_SAM2_CHECKPOINT_ENV = "SAM2_CHECKPOINT_PATH"
_MAX_SIDE_PX = int(os.environ.get("SAM2_MAX_IMAGE_SIDE", 1024))
_DEFAULT_SAM2_MODEL_ID = "facebook/sam2.1-hiera-tiny"


class SegmentationError(Exception):
    """Raised when the garment segmentation stage fails."""


class GarmentSegmenter:
    """Segments the dominant garment from a product image using SAM 2.1.

    The segmenter is stateless: each call to :meth:`segment` independently
    loads the model, runs inference, and immediately releases GPU resources
    so that subsequent pipeline stages have maximum VRAM headroom.
    """

    def segment(self, image_path: Path, job_id: str) -> Path:
        """Segment the garment in *image_path* and save a mask PNG.

        VRAM lifecycle (strict order):
            1. Load SAM 2 model to GPU.
            2. Run automatic mask generation.
            3. ``del`` the model reference.
            4. ``torch.cuda.empty_cache()``
            5. ``gc.collect()``

        Args:
            image_path: Absolute path to the input garment image (JPEG/PNG).
            job_id: Unique job identifier used to derive the output directory.

        Returns:
            Path to the saved mask PNG at
            ``/dev/shm/ghostfabric/{job_id}/mask.png``.

        Raises:
            SegmentationError: If any step of segmentation fails.
        """
        try:
            return self._run_segmentation(image_path, job_id)
        except SegmentationError:
            logger.error("Segmentation failed", exc_info=True)
            raise
        except Exception as exc:
            logger.error("Segmentation failed", exc_info=True)
            raise SegmentationError(
                f"Segmentation failed for job {job_id!r} on image {image_path}"
            ) from exc

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _run_segmentation(self, image_path: Path, job_id: str) -> Path:
        """Internal implementation — called by :meth:`segment`."""
        logger.info(
            "Starting segmentation | job=%s | image=%s", job_id, image_path
        )

        image_array = self._load_image(image_path)

        mask_array = self._generate_mask(image_array, job_id)

        output_path = file_io.get_output_path(job_id, "mask.png")
        self._save_mask(mask_array, output_path)

        logger.info(
            "Segmentation complete | job=%s | mask=%s", job_id, output_path
        )
        return output_path

    def _load_image(self, image_path: Path) -> np.ndarray:
        """Load *image_path*, downscale if needed, and return an RGB uint8 numpy array."""
        try:
            image = Image.open(image_path).convert("RGB")
            w, h = image.size
            if max(w, h) > _MAX_SIDE_PX:
                scale = _MAX_SIDE_PX / max(w, h)
                new_size = (int(w * scale), int(h * scale))
                image = image.resize(new_size, Image.LANCZOS)
                logger.info(
                    "Resized image from %dx%d to %dx%d for VRAM budget",
                    w, h, new_size[0], new_size[1],
                )
            return np.array(image, dtype=np.uint8)
        except Exception as exc:
            raise SegmentationError(
                f"Failed to load image {image_path}: {exc}"
            ) from exc

    def _resolve_checkpoint(self) -> str:
        """Return the SAM 2 checkpoint path or HuggingFace model ID."""
        local_path = os.environ.get(_SAM2_CHECKPOINT_ENV, "").strip()
        if local_path:
            resolved = Path(local_path)
            if not resolved.exists():
                raise SegmentationError(
                    f"SAM2 checkpoint not found at {resolved} "
                    f"(set by {_SAM2_CHECKPOINT_ENV!r})"
                )
            logger.debug("Using local SAM2 checkpoint: %s", resolved)
            return str(resolved)
        logger.debug("Using HuggingFace model ID: %s", _DEFAULT_SAM2_MODEL_ID)
        return _DEFAULT_SAM2_MODEL_ID

    def _generate_mask(self, image_array: np.ndarray, job_id: str) -> np.ndarray:
        """Run SAM 2 automatic mask generation and return the largest mask.

        Args:
            image_array: RGB uint8 numpy array of the garment image.
            job_id: Used only for log context.

        Returns:
            Binary mask as a boolean numpy array with the same H x W as the
            input image, where ``True`` marks the garment region.
        """
        from sam2.build_sam import build_sam2_hf
        from sam2.automatic_mask_generator import SAM2AutomaticMaskGenerator

        checkpoint = self._resolve_checkpoint()
        device = "cuda" if torch.cuda.is_available() else "cpu"

        logger.info(
            "Loading SAM2 model | job=%s | checkpoint=%s | device=%s",
            job_id,
            checkpoint,
            device,
        )

        try:
            sam2_model = build_sam2_hf(checkpoint, device=device)
        except Exception as exc:
            raise SegmentationError(
                f"Failed to load SAM2 model from {checkpoint!r}: {exc}"
            ) from exc

        try:
            mask_generator = SAM2AutomaticMaskGenerator(
                model=sam2_model,
                points_per_side=16,
                points_per_batch=32,
                pred_iou_thresh=0.88,
                stability_score_thresh=0.95,
                crop_n_layers=0,
                min_mask_region_area=500,
            )

            logger.debug("Running mask generation | job=%s", job_id)
            masks = mask_generator.generate(image_array)
        except Exception as exc:
            raise SegmentationError(
                f"SAM2 mask generation failed for job {job_id!r}: {exc}"
            ) from exc
        finally:
            # Strict VRAM teardown — always runs even on exception.
            del sam2_model
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            gc.collect()
            logger.debug("VRAM released after SAM2 inference | job=%s", job_id)

        if not masks:
            raise SegmentationError(
                f"SAM2 returned no masks for job {job_id!r}. "
                "Ensure the image contains a visible garment."
            )

        largest = self._select_largest_mask(masks)
        logger.debug(
            "Selected garment mask | job=%s | area=%d px",
            job_id,
            int(largest["area"]),
        )
        return largest["segmentation"]

    @staticmethod
    def _select_largest_mask(masks: list[dict]) -> dict:
        """Return the mask annotation dict with the greatest pixel area."""
        return max(masks, key=lambda m: m["area"])

    @staticmethod
    def _save_mask(mask_array: np.ndarray, output_path: Path) -> None:
        """Convert *mask_array* to a binary PNG and write to *output_path*.

        Args:
            mask_array: Boolean or uint8 H x W array where truthy values mark
                the garment region.
            output_path: Destination file path (parent directory must exist).

        Raises:
            SegmentationError: If the file cannot be written.
        """
        try:
            binary = (mask_array.astype(np.uint8)) * 255
            mask_image = Image.fromarray(binary, mode="L")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            mask_image.save(output_path, format="PNG")
            logger.debug("Mask saved: %s", output_path)
        except Exception as exc:
            raise SegmentationError(
                f"Failed to save mask to {output_path}: {exc}"
            ) from exc
