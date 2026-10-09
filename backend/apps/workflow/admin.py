from django.contrib import admin
from .models import ChangeRequest


@admin.register(ChangeRequest)
class ChangeRequestAdmin(admin.ModelAdmin):
    list_display = ("record", "field_name", "status", "requested_by", "decided_by", "requested_at")
    list_filter = ("status", "field_name")
    readonly_fields = ("old_value_ciphertext", "new_value_ciphertext")

