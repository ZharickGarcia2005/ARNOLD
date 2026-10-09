from django.contrib import admin
from .models import ValidationIssue


@admin.register(ValidationIssue)
class ValidationIssueAdmin(admin.ModelAdmin):
    list_display = ("rule_code", "severity", "record", "requires_review", "resolved_at")
    list_filter = ("severity", "requires_review", "rule_code")
    search_fields = ("rule_code", "message")

