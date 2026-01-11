import logging
from http import HTTPStatus
from typing import TypedDict

from fastapi import APIRouter, HTTPException

from src.worker import job_queue, get_job_average_duration_seconds

PlanningGenerationAcknowledgement = TypedDict(
    "PlanningGenerationAcknowledgement",
    {
        "positionInQueue": int,
        "averageDurationSeconds": float | str
    }
)

_logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/planning/{planning_id}/generate", status_code=HTTPStatus.ACCEPTED)
async def generate_planning(planning_id: str) -> PlanningGenerationAcknowledgement:
    try:
        await job_queue.put({"planning_id": planning_id})
    except Exception as e:
        _logger.error(f"Error while queuing planning generation for ID {planning_id}: {e}")
        raise HTTPException(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            detail="Failed to queue planning generation."
        ) from e

    return {
        "positionInQueue": job_queue.qsize(),
        "averageDurationSeconds": get_job_average_duration_seconds() or "N/A"
    }
