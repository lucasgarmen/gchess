import re

from django import forms
from django.contrib.auth.models import User


class PasswordRecoveryForm(forms.Form):
    email = forms.EmailField(
        label='Email',
        widget=forms.EmailInput(attrs={'autocomplete': 'email'}),
    )


class RegisterForm(forms.Form):
    username = forms.CharField(
        label='Usuario',
        max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'username'}),
    )
    email = forms.EmailField(label='Email')
    password = forms.CharField(
        label='Senha',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )
    password_confirm = forms.CharField(
        label='Confirmar senha',
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password'}),
    )

    def clean_username(self):
        username = self.cleaned_data['username'].strip()

        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError('Esse usuário já existe.')

        return username

    def clean_email(self):
        email = self.cleaned_data['email'].strip()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Esse email já está cadastrado.')

        return email

    def clean_password(self):
        password = self.cleaned_data['password']

        has_letter = re.search(r'[A-Za-z]', password)
        has_number = re.search(r'\d', password)

        if not has_letter or not has_number:
            raise forms.ValidationError('A senha deve ter letras e números.')

        return password

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        password_confirm = cleaned_data.get('password_confirm')

        if password and password_confirm and password != password_confirm:
            self.add_error('password_confirm', 'As senhas não coincidem.')

        return cleaned_data

    def save(self, commit=True):
        user = User(
            username=self.cleaned_data['username'],
            email=self.cleaned_data['email'],
        )
        user.set_password(self.cleaned_data['password'])

        if commit:
            user.save()

        return user
