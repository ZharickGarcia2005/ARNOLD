"""Escritura centralizada de eventos sin datos personales."""

from hashlib import sha256
import json
import uuid

from .models import AuditEvent


def append_audit_event(*, actor, action: str, object_type: str, object_id, metadata=None):
    previous = AuditEvent.objects.order_by("-occurred_at").only("event_hash").first()
    event_id = uuid.uuid4()
    safe_metadata = metadata or {}
    payload = json.dumps(
        {
            "id": str(event_id),
            "previous": previous.event_hash if previous else "",
            "actor": str(getattr(actor, "pk", "") or ""),
            "action": action,
            "object_type": object_type,
            "object_id": str(object_id),
            "metadata": safe_metadata,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return AuditEvent.objects.create(
        id=event_id,
        actor=actor,
        action=action,
        object_type=object_type,
        object_id=str(object_id),
        metadata=safe_metadata,
        previous_hash=previous.event_hash if previous else "",
        event_hash=sha256(payload.encode("utf-8")).hexdigest(),
    )
