from django.urls import path

from . import views

app_name = "worksheets"
urlpatterns = [
    path("<uuid:batch_id>/", views.detail, name="detail"),
    path("<uuid:batch_id>/query/", views.query, name="query"),
    path("<uuid:batch_id>/save/", views.save, name="save"),
    path("<uuid:batch_id>/presentation/", views.presentation, name="presentation"),
    path("<uuid:batch_id>/download/", views.download, name="download"),
    path("<uuid:batch_id>/requests/", views.requests, name="requests"),
    path("<uuid:batch_id>/requests/<int:request_id>/decide/", views.decide, name="decide"),
    path("<uuid:batch_id>/history/", views.history, name="history"),
]
