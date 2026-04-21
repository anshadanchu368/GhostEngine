"""File I/O helpers for per-job temporary directories under /dev/shm/ghostfabric/."""

import logging
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

_BASE_DIR = Path("/dev/shm/ghostfabric")


def get_job_dir(job_id: str) -> Path:
    """Return the Path for a job's temporary working directory.

    The directory is not created; use :func:`create_job_dir` for that.

    Args:
        job_id: Unique identifier for the job.

    Returns:
        Path object pointing to /dev/shm/ghostfabric/{job_id}.
    """
    return _BASE_DIR / job_id


def create_job_dir(job_id: str) -> Path:
    """Create the job's temporary directory and return its Path.

    The call is idempotent: if the directory already exists no error is raised.

    Args:
        job_id: Unique identifier for the job.

    Returns:
        Path to the created (or pre-existing) directory.

    Raises:
        OSError: If the directory cannot be created due to a permissions issue
            or other filesystem error.
    """
    job_dir = get_job_dir(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    logger.debug("Job directory ready: %s", job_dir)
    return job_dir


def cleanup_job_dir(job_id: str) -> None:
    """Remove the job's temporary directory tree, silently ignoring missing dirs.

    Args:
        job_id: Unique identifier for the job whose directory should be removed.
    """
    job_dir = get_job_dir(job_id)
    try:
        shutil.rmtree(job_dir)
        logger.debug("Removed job directory: %s", job_dir)
    except FileNotFoundError:
        logger.debug("Job directory not found, nothing to clean: %s", job_dir)
    except Exception as exc:
        logger.error("Failed to remove job directory %s: %s", job_dir, exc)


def get_input_path(job_id: str, filename: str) -> Path:
    """Return the Path for an input file within the job's directory.

    The file is not required to exist yet.

    Args:
        job_id: Unique identifier for the job.
        filename: Name of the input file (basename only).

    Returns:
        Path to /dev/shm/ghostfabric/{job_id}/{filename}.
    """
    return get_job_dir(job_id) / filename


def get_output_path(job_id: str, filename: str) -> Path:
    """Return the Path for an output file within the job's directory.

    The file is not required to exist yet.

    Args:
        job_id: Unique identifier for the job.
        filename: Name of the output file (basename only).

    Returns:
        Path to /dev/shm/ghostfabric/{job_id}/{filename}.
    """
    return get_job_dir(job_id) / filename


def save_upload(job_id: str, filename: str, data: bytes) -> Path:
    """Persist uploaded bytes to the job's input directory.

    Creates the job directory if it does not already exist, then writes
    ``data`` to ``{job_dir}/{filename}``.

    Args:
        job_id: Unique identifier for the job.
        filename: Destination filename within the job directory.
        data: Raw bytes to write.

    Returns:
        Path to the saved file.

    Raises:
        OSError: If the directory cannot be created or the file cannot be
            written.
    """
    create_job_dir(job_id)
    target = get_input_path(job_id, filename)
    target.write_bytes(data)
    logger.debug("Saved upload %s (%d bytes) -> %s", filename, len(data), target)
    return target
