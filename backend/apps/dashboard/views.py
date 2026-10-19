from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render


@login_required
def index(request):
    resources = [settings.BASE_DIR / "static" / name for name in (
        "js/worksheet-app.js", "js/worksheet-grid-model.js", "js/worksheet-grid.js", "js/worksheet-download.js",
        "css/worksheet.css", "css/worksheet-grid.css", "css/worksheet-orders.css",
    )]
    response = render(
        request,
        "dashboard/worksheet.html",
        {"max_upload_bytes": settings.ARNOLD_MAX_UPLOAD_BYTES, "asset_version": int(max(path.stat().st_mtime for path in resources))},
    )
    response["Cache-Control"] = "no-store"
    return response


def health(_request):
    return JsonResponse({"service": "arnold-web", "status": "ok"})

