from django.contrib import admin
from .models import ValidationIssue, ValidationRun


@admin.register(ValidationRun)
class ValidationRunAdmin(admin.ModelAdmin):
    list_display = (
        "id", "current_batch", "status", "issue_count", "blocking_count",
        "engine_version", "created_at",
    )
    list_filter = ("status", "engine_version", "adapter_version")
    search_fields = ("id", "current_batch__display_name", "input_digest")
    readonly_fields = ("input_digest", "created_at", "updated_at")


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = (
        "rule_code", "severity", "blocking", "record", "requires_review", "resolved_at"
    )
    list_filter = (
        "severity", "blocking", "requires_review", "review_status", "rule_code"
    )
    search_fields = ("fingerprint", "rule_code", "message")
    readonly_fields = ("evidence_ciphertext", "evidence_sha256")

