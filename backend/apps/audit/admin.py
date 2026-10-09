from django.contrib import admin
from .models import AuditEvent


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = ("occurred_at", "actor", "action", "object_type", "object_id")
    list_filter = ("action", "object_type")
    search_fields = ("object_id", "event_hash")
    readonly_fields = (
        "id", "occurred_at", "actor", "action", "object_type", "object_id",
        "metadata", "previous_hash", "event_hash",
    )

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

