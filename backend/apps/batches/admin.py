from django.contrib import admin
from .models import Batch, Record


@admin.register(Batch)
class BatchAdmin(admin.ModelAdmin):
    list_display = (
        "display_name", "source_type", "period", "status", "row_count", "owner_area", "created_at"
    )
    list_filter = ("status", "source_type", "period", "owner_area", "scan_status")
    search_fields = ("display_name", "sha256")
    readonly_fields = (
        "id", "storage_key", "sha256", "file_size", "original_headers", "headers_ciphertext",
        "selected_occurrences", "created_at", "updated_at",
    )


@admin.register(Record)
class RecordAdmin(admin.ModelAdmin):
    list_display = ("id", "batch", "source_row", "status", "version", "assigned_to")
    list_filter = ("status", "batch")
    search_fields = ("clave_hmac", "ciu_hmac", "identifier_hmac")
    readonly_fields = ("data_ciphertext",)
