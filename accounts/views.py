from django.contrib.auth import login
from django.contrib.auth.models import User
from django.contrib.auth.views import PasswordChangeView
from django.core import signing
from django.core.mail import EmailMultiAlternatives
from django.shortcuts import render, redirect
from django.urls import reverse, reverse_lazy

import secrets
import string

from games.i18n import current_language, t

from .forms import PasswordRecoveryForm, RegisterForm
from .models import PlayerProfile


PASSWORD_RESET_SALT = 'gchess-password-reset'
PASSWORD_RESET_MAX_AGE = 60 * 30


def make_temporary_password(length=14):
    alphabet = string.ascii_letters + string.digits
    password = [
        secrets.choice(string.ascii_lowercase),
        secrets.choice(string.ascii_uppercase),
        secrets.choice(string.digits),
    ]
    password.extend(secrets.choice(alphabet) for _ in range(length - len(password)))
    secrets.SystemRandom().shuffle(password)
    return ''.join(password)


def build_password_reset_token(user, language):
    return signing.dumps(
        {'user_id': user.id, 'language': language},
        salt=PASSWORD_RESET_SALT,
    )


def load_password_reset_token(token):
    return signing.loads(
        token,
        salt=PASSWORD_RESET_SALT,
        max_age=PASSWORD_RESET_MAX_AGE,
    )


def send_password_reset_confirmation_email(request, user, language):
    reset_url = request.build_absolute_uri(
        reverse('password_reset_confirm', kwargs={'token': build_password_reset_token(user, language)})
    )
    subject = t(language, 'reset_confirmation_email_subject')
    message = t(language, 'reset_confirmation_email_body').format(
        username=user.username,
        reset_url=reset_url,
    )
    button_text = t(language, 'reset_confirmation_button')
    html_message = f"""
        <p>{t(language, 'reset_confirmation_email_greeting').format(username=user.username)}</p>
        <p>{t(language, 'reset_confirmation_email_intro')}</p>
        <p>
            <a href="{reset_url}" style="background:#f0d9b5;color:#111;display:inline-block;font-weight:700;padding:12px 18px;text-decoration:none;border-radius:6px;">
                {button_text}
            </a>
        </p>
        <p>{t(language, 'reset_confirmation_email_ignore')}</p>
        <p>{t(language, 'reset_confirmation_email_fallback')}</p>
        <p><a href="{reset_url}">{reset_url}</a></p>
    """
    email = EmailMultiAlternatives(subject, message, None, [user.email])
    email.attach_alternative(html_message, 'text/html')
    email.send()


def password_reset(request):
    language = current_language(request)

    if request.method == 'POST':
        form = PasswordRecoveryForm(request.POST)

        if form.is_valid():
            email = form.cleaned_data['email'].strip()
            user = (
                User.objects
                .filter(email__iexact=email, is_active=True)
                .order_by('id')
                .first()
            )

            if user:
                try:
                    send_password_reset_confirmation_email(request, user, language)
                except Exception:
                    form.add_error(None, t(language, 'email_send_error'))
                    return render(request, 'registration/password_reset_form.html', {'form': form})

            return redirect('password_reset_done')
    else:
        form = PasswordRecoveryForm()

    return render(request, 'registration/password_reset_form.html', {'form': form})


def password_reset_done(request):
    return render(request, 'registration/password_reset_done.html')


def password_reset_confirm(request, token):
    try:
        token_data = load_password_reset_token(token)
        language = token_data.get('language')
        user = User.objects.get(id=token_data.get('user_id'), is_active=True)
    except (signing.BadSignature, signing.SignatureExpired, User.DoesNotExist):
        return render(request, 'registration/password_reset_invalid.html')

    request.session['language'] = language
    temporary_password = make_temporary_password()
    user.set_password(temporary_password)
    user.save(update_fields=['password'])

    return render(
        request,
        'registration/password_reset_confirm.html',
        {'temporary_password': temporary_password},
    )


def legacy_password_reset_link(request, uidb64, token):
    return render(request, 'registration/password_reset_invalid.html')


class LocalizedPasswordChangeView(PasswordChangeView):
    template_name = 'registration/password_change_form.html'
    success_url = reverse_lazy('password_change_done')


def register(request):
    if request.method == 'POST':
        form = RegisterForm(request.POST)

        if form.is_valid():
            user = form.save()
            PlayerProfile.objects.get_or_create(user=user)
            login(request, user)
            return redirect('home')
    else:
        form = RegisterForm()

    return render(request, 'registration/register.html', {'form': form})
