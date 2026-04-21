"""Stable Diffusion 1.5 ghost mannequin inpainting pipeline stage.

Stage 2 of 3: SAM -> Stable Diffusion -> TripoSR

Accepts a garment image and a binary mask (from Stage 1) and produces an
inpainted "ghost mannequin" image where the masked region is filled with
clean product-photography content using the SD 1.5 inpainting model.
"""

import gc
import logging
from pathlib import Path

import torch
from PIL import Image

from app.utils import file_io

logger = logging.getLogger(__name__)

_MODEL_ID = "Uminosachi/realisticVisionV51_v51VAE-inpainting"
_POSITIVE_PROMPT = (
    "ghost mannequin, empty garment, no person, clean product photography"
)
_NEGATIVE_PROMPT = (
    "person, human, body, mannequin, model, shadow, wrinkle, background clutter"
)
_INFERENCE_STEPS = 30
_GUIDANCE_SCALE = 7.5
_IMAGE_SIZE = (512, 512)


class InpaintingError(Exception):
    """Raised when the ghost mannequin inpainting stage fails."""


class GhostInpainter:
    """Inpaints a masked garment region using Stable Diffusion 1.5.

    The inpainter is stateless: each call to :meth:`inpaint` independently
    loads the diffusion pipeline, runs inference, and immediately releases GPU
    resources so that subsequent pipeline stages have maximum VRAM headroom.
    """

    def inpaint(self, image_path: Path, mask_path: Path, job_id: str) -> Path:
        """Inpaint the masked region of *image_path* and save the result.

        VRAM lifecycle (strict order, covered by a single try/finally):
            1. Load SD 1.5 inpainting pipeline to GPU.
            2. Run inference.
            3. ``del pipe`` (delete reference).
            4. ``torch.cuda.empty_cache()``
            5. ``gc.collect()``

        Args:
            image_path: Absolute path to the original garment image (JPEG/PNG).
            mask_path: Absolute path to the binary mask PNG produced by Stage 1.
            job_id: Unique job identifier used to derive the output directory.

        Returns:
            Path to the saved inpainted PNG at
            ``/dev/shm/ghostfabric/{job_id}/inpainted.png``.

        Raises:
            InpaintingError: If any step of the inpainting process fails.
        """
        from diffusers import StableDiffusionInpaintPipeline

        pipe = None
        try:
            image = self._load_image(image_path)
            mask = self._load_mask(mask_path)
            pipe = StableDiffusionInpaintPipeline.from_pretrained(
                _MODEL_ID, torch_dtype=torch.float16
            ).to("cuda")
            pipe.enable_attention_slicing()
            result = pipe(
                prompt=_POSITIVE_PROMPT,
                negative_prompt=_NEGATIVE_PROMPT,
                image=image,
                mask_image=mask,
                num_inference_steps=_INFERENCE_STEPS,
                guidance_scale=_GUIDANCE_SCALE,
            ).images[0]
            return self._save_result(result, job_id)
        except InpaintingError:
            logger.error("Inpainting failed", exc_info=True)
            raise
        except Exception as exc:
            logger.error("Inpainting failed", exc_info=True)
            raise InpaintingError(f"Inpainting failed for job {job_id!r}") from exc
        finally:
            if pipe is not None:
                del pipe
            torch.cuda.empty_cache()
            gc.collect()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_image(self, image_path: Path) -> Image.Image:
        """Load *image_path* as an RGB PIL Image resized to 512x512."""
        image = Image.open(image_path).convert("RGB")
        return image.resize(_IMAGE_SIZE)

    def _load_mask(self, mask_path: Path) -> Image.Image:
        """Load *mask_path* as a grayscale PIL Image resized to 512x512."""
        mask = Image.open(mask_path).convert("L")
        return mask.resize(_IMAGE_SIZE)

    def _save_result(self, result: Image.Image, job_id: str) -> Path:
        """Save *result* as a PNG via file_io and return its path.

        Args:
            result: Inpainted PIL Image to persist.
            job_id: Unique job identifier used to derive the output directory.

        Returns:
            Path to the saved inpainted PNG.
        """
        output_path = file_io.get_output_path(job_id, "inpainted.png")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        result.save(output_path, format="PNG")
        return output_path
