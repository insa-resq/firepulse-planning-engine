import asyncio
import logging
import sys
import time
from typing import Optional

_logger = logging.getLogger(__name__)

_average_duration_seconds: Optional[float] = None

job_queue = asyncio.Queue()

def get_job_average_duration_seconds() -> Optional[float]:
    return _average_duration_seconds

async def worker_processor() -> None:
    """
    This background loop runs forever inside the FastAPI app.
    It waits for jobs in the queue and runs the subprocess.
    """
    _logger.info("Worker processor started.")

    while True:
        _logger.info("Waiting for next job...")

        job_payload = await job_queue.get()

        # Validate the payload ({"planning_id": planning_id})
        if not isinstance(job_payload, dict) or "planning_id" not in job_payload:
            _logger.error(f"Invalid job payload: {job_payload}")
            job_queue.task_done()
            continue

        planning_id = job_payload["planning_id"]

        try:
            _logger.info(f"Starting worker for planning ID: {planning_id}")

            start_time = time.time()

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "src.solver",
                planning_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await process.communicate()

            duration = time.time() - start_time

            if process.returncode == 0:
                global _average_duration_seconds

                if _average_duration_seconds is None:
                    _average_duration_seconds = duration
                else:
                    # Update the moving average (simple exponential moving average with alpha=0.1)
                    _average_duration_seconds = (_average_duration_seconds * 9 + duration) / 10

                _logger.info(f"Worker completed in {duration:.2f} seconds.")
                _logger.info(f"Worker stdout:\n{stdout.decode().strip()}")
            else:
                _logger.error(f"Worker failed after {duration:.2f} seconds with return code {process.returncode}.")
                _logger.error(f"Failed worker stderr: {stderr.decode().strip()}")
        except Exception as e:
            _logger.error(f"Error launching worker: {e}")
        finally:
            job_queue.task_done()
