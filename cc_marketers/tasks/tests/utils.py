
# tests/utils.py
"""
Utility functions and helpers for tests.
"""
import os
import shutil
from django.conf import settings


def cleanup_test_media():
    """Clean up test media files."""
    if hasattr(settings, 'MEDIA_ROOT') and settings.MEDIA_ROOT:
        try:
            if os.path.exists(settings.MEDIA_ROOT):
                shutil.rmtree(settings.MEDIA_ROOT)
        except OSError:
            pass


def get_test_file_path(filename):
    """Get path for test files."""
    test_files_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), 
        'test_files'
    )
    return os.path.join(test_files_dir, filename)


class TestDataMixin:
    """Mixin providing test data creation methods."""
    
    @classmethod
    def create_test_users(cls):
        """Create standard test users."""
        from django.contrib.auth import get_user_model
        User = get_user_model()
        
        users = {}
        
        users['admin'] = User.objects.create_superuser(
            username='test_admin',
            email='admin@test.com',
            password='testpass123'
        )
        
        users['advertiser'] = User.objects.create_user(
            username='test_advertiser',
            email='advertiser@test.com',
            password='testpass123'
        )
        users['advertiser'].role = 'advertiser'
        users['advertiser'].is_subscribed = True
        users['advertiser'].save()
        
        users['member'] = User.objects.create_user(
            username='test_member',
            email='member@test.com',
            password='testpass123'
        )
        users['member'].role = 'member'
        users['member'].is_subscribed = True
        users['member'].save()
        
        return users

