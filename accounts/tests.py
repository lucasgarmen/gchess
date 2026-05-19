from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from .views import build_password_reset_token


class PasswordResetTests(TestCase):
    def test_signed_reset_link_uses_project_confirmation_template(self):
        user = User.objects.create_user(
            username='reset-user',
            email='reset@example.com',
            password='OldPassword123',
        )
        token = build_password_reset_token(user, 'es')

        response = self.client.get(reverse('password_reset_confirm', kwargs={'token': token}))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'temporary-password-box')
        self.assertNotContains(response, 'The password reset link was invalid')


class PasswordChangeLanguageTests(TestCase):
    def test_password_validator_errors_follow_selected_language(self):
        user = User.objects.create_user(
            username='language-user',
            email='language@example.com',
            password='OldPassword123',
        )
        session = self.client.session
        session['language'] = 'es'
        session.save()
        self.client.force_login(user)

        response = self.client.post(
            reverse('password_change'),
            {
                'old_password': 'OldPassword123',
                'new_password1': '123',
                'new_password2': '123',
            },
        )

        errors = response.context['form'].errors.as_text()
        self.assertIn('Esta contraseña', errors)
        self.assertNotIn('Your password', errors)
