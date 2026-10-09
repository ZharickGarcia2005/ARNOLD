from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import User


@admin.register(User)
class ArnoldUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ("ARNOLD", {"fields": ("role", "area", "must_use_mfa")}),
    )
    list_display = ("username", "email", "role", "area", "is_active")
    list_filter = ("role", "area", "is_active")

