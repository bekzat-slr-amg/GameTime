from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from .models import User

INPUT = "input"


class AdminUserCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "first_name")


class RegisterForm(UserCreationForm):
    agree = forms.BooleanField(
        label="Я согласен с условиями использования",
        error_messages={"required": "Нужно согласиться с условиями"},
    )

    class Meta:
        model = User
        fields = ("first_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["first_name"].label = "Имя"
        self.fields["password1"].label = "Пароль"
        self.fields["password2"].label = "Подтвердите пароль"
        placeholders = {
            "first_name": "Ваше имя",
            "email": "example@mail.com",
            "phone": "+996 700 000 000",
            "password1": "Придумайте пароль",
            "password2": "Повторите пароль",
        }
        for name, text in placeholders.items():
            self.fields[name].widget.attrs.update({"class": INPUT, "placeholder": text})
        for name in ("password1", "password2"):
            self.fields[name].widget.attrs["class"] = f"{INPUT} pr-24"

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Пользователь с таким email уже существует")
        return email


class LoginForm(AuthenticationForm):
    username = forms.EmailField(
        label="Email",
        widget=forms.EmailInput(attrs={
            "autofocus": True, "autocomplete": "email",
            "placeholder": "example@mail.com", "class": INPUT,
        }),
    )
    password = forms.CharField(
        label="Пароль",
        strip=False,
        widget=forms.PasswordInput(attrs={
            "autocomplete": "current-password",
            "placeholder": "Ваш пароль", "class": f"{INPUT} pr-24",
        }),
    )
    remember_me = forms.BooleanField(required=False, label="Запомнить меня")

    def clean_username(self):
        return self.cleaned_data["username"].lower()

class ProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["first_name"].required = True
        self.fields["first_name"].label = "Имя"
        self.fields["email"].disabled = True  # email не меняется, значения из формы игнорируются
        for name, text in (("first_name", "Ваше имя"), ("email", ""), ("phone", "+996 700 000 000")):
            self.fields[name].widget.attrs.update({"class": INPUT, "placeholder": text})


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "old_password": "Текущий пароль",
            "new_password1": "Новый пароль",
            "new_password2": "Подтвердите новый пароль",
        }
        for name, label in labels.items():
            self.fields[name].label = label
            self.fields[name].widget.attrs["class"] = f"{INPUT} pr-24"