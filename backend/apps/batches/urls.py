from django.urls import path

from . import views


app_name = "batches"

urlpatterns = [
    path("", views.batch_list, name="list"),
    path("uploads/", views.upload_batch, name="upload"),
    path("<uuid:batch_id>/", views.batch_status, name="status"),
    path("<uuid:batch_id>/retry/", views.retry_batch, name="retry"),
    path("<uuid:batch_id>/records/", views.batch_records, name="records"),
]
