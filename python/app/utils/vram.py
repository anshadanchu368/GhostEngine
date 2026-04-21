"""VRAM monitoring utilities for GPU memory management."""

import gc
import logging

logger = logging.getLogger(__name__)


def is_gpu_available() -> bool:
    """Return True if a CUDA-capable GPU is available, False otherwise."""
    try:
        import torch
        return torch.cuda.is_available()
    except ImportError:
        logger.warning("torch not installed; GPU unavailable")
        return False


def get_vram_free_gb() -> float:
    """Return free VRAM in gigabytes for the current CUDA device.

    Returns 0.0 if CUDA is unavailable or an error occurs.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        free_bytes, _ = torch.cuda.mem_get_info()
        return free_bytes / (1024 ** 3)
    except Exception as exc:
        logger.error("Failed to query free VRAM: %s", exc)
        return 0.0


def get_vram_total_gb() -> float:
    """Return total VRAM in gigabytes for the current CUDA device.

    Returns 0.0 if CUDA is unavailable or an error occurs.
    """
    try:
        import torch
        if not torch.cuda.is_available():
            return 0.0
        _, total_bytes = torch.cuda.mem_get_info()
        return total_bytes / (1024 ** 3)
    except Exception as exc:
        logger.error("Failed to query total VRAM: %s", exc)
        return 0.0


def flush_vram() -> None:
    """Release cached GPU memory and trigger a Python garbage collection cycle."""
    try:
        import torch
        if torch.cuda.is_available():
            torch.cuda.empty_cache()
            logger.debug("CUDA cache cleared")
    except ImportError:
        logger.warning("torch not installed; skipping CUDA cache clear")
    except Exception as exc:
        logger.error("Failed to flush VRAM: %s", exc)
    finally:
        gc.collect()
        logger.debug("Python garbage collection completed")


def vram_stats() -> dict:
    """Return a snapshot of GPU availability and VRAM usage.

    Returns:
        dict with keys:
            - gpu_available (bool): whether a CUDA GPU is accessible
            - vram_free_gb (float): free VRAM in GB (0.0 if unavailable)
            - vram_total_gb (float): total VRAM in GB (0.0 if unavailable)
    """
    return {
        "gpu_available": is_gpu_available(),
        "vram_free_gb": get_vram_free_gb(),
        "vram_total_gb": get_vram_total_gb(),
    }
