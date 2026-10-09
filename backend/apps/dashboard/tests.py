from django.test import TestCase
from django.urls import reverse


class DashboardTests(TestCase):
    def test_dashboard_renders(self):
        response = self.client.get(reverse("dashboard:index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "ARNOLD")

    def test_health_endpoint(self):
        response = self.client.get(reverse("dashboard:health"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")

