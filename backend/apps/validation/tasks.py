from datetime import timedelta
import math
import uuid

from celery import shared_task
from django.conf import settings
from django.db import InterfaceError, OperationalError, transaction
from django.utils import timezone

from apps.batches.crypto import CryptoConfigurationError, DecryptionError, EncryptionError
from apps.batches.models import Batch
from apps.audit.services import append_audit_event

from .excel_adapter import ExcelAdapterError
from .models import ValidationRun
from .services import ValidationConfigurationError, execute_validation


def _claim(run_id, broker_task_id: str) -> tuple[bool, str, str, int]:
    """Obtiene una ejecución exclusiva y devuelve su token de fencing.

    El identificador de Celery no es suficiente: una redelivery conserva el
    mismo id. Cada claim válido recibe por eso un token nuevo e impredecible.
    """

    broker_task_id = broker_task_id or "local"
    with transaction.atomic():
        run = ValidationRun.objects.select_for_update().select_related("current_batch").get(id=run_id)
        if run.status == ValidationRun.Status.SUCCEEDED:
            return False, run.status, "", 0
        now = timezone.now()
        if run.status == ValidationRun.Status.RUNNING:
            lease_active = run.lease_expires_at and run.lease_expires_at > now
            if lease_active:
                retry_after = max(
                    5,
                    math.ceil((run.lease_expires_at - now).total_seconds()) + 5,
                )
                return False, run.status, "", retry_after
        execution_token = f"{broker_task_id[:160]}:{uuid.uuid4().hex}"
        run.status = ValidationRun.Status.RUNNING
        run.task_id = execution_token
        run.attempt_count += 1
        run.started_at = now
        run.lease_expires_at = now + timedelta(
            seconds=int(settings.ARNOLD_VALIDATION_LEASE_SECONDS)
        )
        run.finished_at = None
        run.error_code = ""
        run.error_message = ""
        run.save(update_fields=(
            "status", "task_id", "attempt_count", "started_at", "lease_expires_at", "finished_at",
            "error_code", "error_message", "updated_at",
        ))
        run.current_batch.status = Batch.Status.PROCESSING
        run.current_batch.save(update_fields=("status", "updated_at"))
        return True, run.status, execution_token, 0


def _fail(run_id, execution_token: str, code: str, message: str) -> None:
    with transaction.atomic():
        run = ValidationRun.objects.select_for_update().select_related("current_batch").get(id=run_id)
        if run.task_id != execution_token:
            return
        run.status = ValidationRun.Status.FAILED
        run.error_code = code[:60]
        run.error_message = message[:500]
        run.finished_at = timezone.now()
        run.lease_expires_at = None
        run.save(update_fields=(
            "status", "error_code", "error_message", "lease_expires_at",
            "finished_at", "updated_at",
        ))
        run.current_batch.status = Batch.Status.FAILED
        run.current_batch.failure_code = code[:60]
        run.current_batch.failure_message = message[:500]
        run.current_batch.save(update_fields=("status", "failure_code", "failure_message", "updated_at"))
        append_audit_event(
            actor=run.created_by,
            action="validation.failed",
            object_type="ValidationRun",
            object_id=run.id,
            metadata={"batch_id": str(run.current_batch_id), "error_code": code[:60]},
        )


@shared_task(
    bind=True,
    autoretry_for=(OSError, OperationalError, InterfaceError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def validate_batch(self, run_id):
    """Procesa una ValidationRun sin duplicar incidencias en los reintentos."""

    claimed, status, execution_token, retry_after = _claim(
        run_id,
        getattr(self.request, "id", "") or "",
    )
    if not claimed:
        if status == ValidationRun.Status.RUNNING and retry_after:
            raise self.retry(countdown=retry_after, max_retries=10)
        return {"run_id": str(run_id), "status": status, "idempotent": True}
    try:
        return execute_validation(run_id, execution_token=execution_token)
    except (OSError, OperationalError, InterfaceError) as exc:
        _fail(
            run_id,
            execution_token,
            "temporary_processing_error",
            "Error temporal durante el procesamiento.",
        )
        raise
    except ExcelAdapterError as exc:
        _fail(run_id, execution_token, exc.code, str(exc))
        return {"run_id": str(run_id), "status": ValidationRun.Status.FAILED, "error": exc.code}
    except ValidationConfigurationError as exc:
        _fail(run_id, execution_token, exc.code, str(exc))
        return {
            "run_id": str(run_id),
            "status": ValidationRun.Status.FAILED,
            "error": exc.code,
        }
    except (CryptoConfigurationError, DecryptionError, EncryptionError, ValueError) as exc:
        _fail(run_id, execution_token, "invalid_validation_input", str(exc))
        return {
            "run_id": str(run_id),
            "status": ValidationRun.Status.FAILED,
            "error": "invalid_validation_input",
        }
    except Exception:
        _fail(
            run_id,
            execution_token,
            "unexpected_processing_error",
            "Ocurrió un error interno durante la validación.",
        )
        raise

