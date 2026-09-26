from django.contrib.auth.backends import ModelBackend


LEGACY_DEMO_USERNAME = 'dispatcher'
LEGACY_DEMO_PASSWORD = 'crewcast2026'


class LegacySeedGuardBackend(ModelBackend):
    """Reject the credential created by older demo seeds without deleting the account."""

    def authenticate(self, request, username=None, password=None, **kwargs):
        candidate = username or kwargs.get('username')
        if candidate == LEGACY_DEMO_USERNAME and password == LEGACY_DEMO_PASSWORD:
            return None
        return super().authenticate(request, username=username, password=password, **kwargs)

    def get_user(self, user_id):
        user = super().get_user(user_id)
        if user and user.get_username() == LEGACY_DEMO_USERNAME and user.check_password(LEGACY_DEMO_PASSWORD):
            return None
        return user
