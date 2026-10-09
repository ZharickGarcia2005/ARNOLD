from django.http import JsonResponse
from django.shortcuts import render


def index(request):
    return render(request, "dashboard/index.html")


def health(_request):
    return JsonResponse({"service": "arnold-web", "status": "ok"})

