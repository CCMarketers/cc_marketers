
# tests/test_settings.py
"""
Test configuration and settings validation.
"""
from django.test import TestCase, override_settings
from django.conf import settings


class TestSettingsTest(TestCase):
    """Test that test settings are properly configured."""

    def test_database_configuration(self):
        """Test that test database is configured correctly."""
        db_config = settings.DATABASES['default']
        self.assertEqual(db_config['ENGINE'], 'django.db.backends.sqlite3')
        self.assertEqual(db_config['NAME'], ':memory:')

    def test_media_configuration(self):
        """Test that media settings are configured for tests."""
        self.assertTrue(settings.MEDIA_ROOT)
        self.assertTrue('test' in settings.MEDIA_ROOT.lower() or 
                       'tmp' in settings.MEDIA_ROOT.lower())

    def test_email_backend(self):
        """Test that email backend is configured for tests."""
        self.assertEqual(settings.EMAIL_BACKEND, 
                        'django.core.mail.backends.locmem.EmailBackend')

    def test_password_hashers(self):
        """Test that fast password hashers are configured."""
        hashers = settings.PASSWORD_HASHERS
        self.assertIn('django.contrib.auth.hashers.MD5PasswordHasher', hashers[0])

    @override_settings(DEBUG=True)
    def test_debug_override(self):
        """Test settings override functionality."""
        self.assertTrue(settings.DEBUG)

