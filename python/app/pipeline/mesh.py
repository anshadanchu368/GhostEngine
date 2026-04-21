"""TripoSR FP16 3D mesh generation pipeline stage.

Stage 3 of 3: SAM -> Stable Diffusion -> TripoSR

Accepts an inpainted garment image (from Stage 2) and produces a .glb mesh
file using TripoSR at FP16 precision to minimise VRAM consumption.
"""

import gc
import logging
from pathlib import Path

import torch
from PIL import Image

from app.utils import file_io

logger = logging.getLogger(__name__)

_TRIPOSR_MODEL_ID = "stabilityai/TripoSR"
_TRIPOSR_CONFIG = "config.yaml"
_TRIPOSR_WEIGHTS = "model.ckpt"
_MESH_RESOLUTION = 256


class MeshGenerationError(Exception):
    """Raised when the TripoSR 3D mesh generation stage fails."""


class MeshGenerator:
    """Generates a 3D .glb mesh from an inpainted garment image using TripoSR.

    The generator is stateless: each call to :meth:`generate` independently
    loads the model, runs FP16 inference, exports the mesh, and immediately
    releases GPU resources so the caller regains full VRAM headroom.
    """

    def generate(self, image_path: Path, job_id: str) -> Path:
        """Generate a .glb mesh from *image_path* and save it to the job dir.

        VRAM lifecycle (strict order, covered by a single try/finally):
            1. Load TripoSR model.
            2. Cast to FP16 and move to CUDA.
            3. Run inference.
            4. Extract and export the .glb mesh.
            5. ``del model`` (delete reference).
            6. ``torch.cuda.empty_cache()``
            7. ``gc.collect()``

        Args:
            image_path: Absolute path to the inpainted garment image (PNG/JPEG).
            job_id: Unique job identifier used to derive the output directory.

        Returns:
            Path to the saved .glb mesh at
            ``/dev/shm/ghostfabric/{job_id}/output.glb``.

        Raises:
            MeshGenerationError: If any step of mesh generation fails.
        """
        from tsr.system import TSR

        model = None
        try:
            logger.info(
                "Starting mesh generation | job=%s | image=%s", job_id, image_path
            )

            model = TSR.from_pretrained(
                _TRIPOSR_MODEL_ID,
                config_name=_TRIPOSR_CONFIG,
                weight_name=_TRIPOSR_WEIGHTS,
            )
            model.half()
            model.to("cuda")
            model.eval()

            image = Image.open(image_path).convert("RGBA")

            with torch.no_grad():
                scene_codes = model([image], device="cuda")

            meshes = model.extract_mesh(scene_codes, resolution=_MESH_RESOLUTION)
            mesh = meshes[0]

            output_path = file_io.get_output_path(job_id, "output.glb")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            mesh.export(str(output_path))

            logger.info(
                "Mesh generation complete | job=%s | output=%s", job_id, output_path
            )
            return output_path
        except MeshGenerationError:
            logger.error("Mesh generation failed", exc_info=True)
            raise
        except Exception as exc:
            logger.error("Mesh generation failed", exc_info=True)
            raise MeshGenerationError(
                f"Mesh generation failed for job {job_id!r}"
            ) from exc
        finally:
            if model is not None:
                del model
            torch.cuda.empty_cache()
            gc.collect()
