from celery import shared_task


@shared_task(bind=True, autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def validate_batch(self, batch_id):
    """Punto de entrada idempotente del trabajador aislado de Excel."""
    return {"batch_id": str(batch_id), "status": "pending-engine-integration"}

