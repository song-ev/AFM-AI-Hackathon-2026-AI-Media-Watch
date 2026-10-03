import logging

from celery import shared_task

from deepanalysis.services.transcription import check_dynamic_dictionary_promotion
from learning.training import train_risk_model

logger = logging.getLogger("aimw")


@shared_task
def weekly_finetuning_cycle():
    """Celery-beat task: the weekly Stage-4 self-learning cycle.

    Two real, auditable steps:
    1. Promote repeated neutral terms from confirmed incidents into the dynamic
       code-word dictionary (pending analyst review).
    2. Train a fresh risk classifier on the analysts' labelled decisions,
       validate it, and deploy it only if it does not regress precision versus
       the deployed model (see ``learning.training.train_risk_model``).
    """
    logger.info("Starting weekly self-learning cycle.")

    check_dynamic_dictionary_promotion()
    run = train_risk_model()

    logger.info(
        "Weekly self-learning cycle finished. Run #%s status=%s examples=%s",
        run.id, run.status, run.training_examples_count,
    )
    return {
        "run_id": run.id,
        "status": run.status,
        "training_examples_count": run.training_examples_count,
        "precision": run.precision,
        "recall": run.recall,
    }
