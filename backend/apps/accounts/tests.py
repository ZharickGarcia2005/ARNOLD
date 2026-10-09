from django.test import TestCase
from .models import User


class UserSecurityTests(TestCase):
    def test_supervisor_requires_mfa(self):
        user = User.objects.create_user(username="supervisor", role=User.Role.SUPERVISOR)
        self.assertTrue(user.must_use_mfa)

