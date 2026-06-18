from django import forms
from django.contrib.auth.models import User
from .models import Student

class StudentRegistrationForm(forms.Form):
    full_name = forms.CharField(
        max_length=255, 
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter your full name'})
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email address'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter a strong password'})
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Confirm your password'})
    )

    def clean_email(self):
        email = self.cleaned_data.get('email')
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return email

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        confirm_password = cleaned_data.get("confirm_password")

        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")

        return cleaned_data

class StudentLoginForm(forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Enter your email address'})
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Enter your password'})
    )
class StudentUpdateForm(forms.ModelForm):
    full_name = forms.CharField(max_length=150)

    class Meta:
        model = Student
        fields = ['full_name']

    def save(self, commit=True):
        student = super().save(commit=False)
        # Sync full_name back to the User model if you store it there
        user = student.user
        user.first_name, _, user.last_name = (
            self.cleaned_data['full_name'].partition(' ')
        )
        if commit:
            user.save()
            student.save()
        return student
class StudentUpdateForm(forms.ModelForm):
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your full name'
        })
    )
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter your email address'
        })
    )
    old_password = forms.CharField(
        label="Current Password",
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter current password to change it'
        })
    )
    new_password1 = forms.CharField(
        label="New Password",
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter new password'
        })
    )
    new_password2 = forms.CharField(
        label="Confirm New Password",
        required=False,
        widget=forms.PasswordInput(attrs={
            'class': 'form-control',
            'placeholder': 'Confirm new password'
        })
    )

    class Meta:
        model = Student
        fields = ['full_name', 'profile_image']
        widgets = {
            'profile_image': forms.FileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*'
            })
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['email'].initial = self.instance.user.email

    def clean_email(self):
        email = self.cleaned_data.get('email')
        qs = User.objects.filter(email=email).exclude(pk=self.instance.user.pk)
        if qs.exists():
            raise forms.ValidationError("This email is already in use.")
        return email

    def clean(self):
        cleaned_data  = super().clean()
        old_password  = cleaned_data.get('old_password')
        new_password1 = cleaned_data.get('new_password1')
        new_password2 = cleaned_data.get('new_password2')

        if old_password or new_password1 or new_password2:
            if not old_password:
                self.add_error('old_password', "Enter your current password.")
            if not new_password1:
                self.add_error('new_password1', "Enter a new password.")
            if not new_password2:
                self.add_error('new_password2', "Confirm your new password.")
            if old_password and not self.instance.user.check_password(old_password):
                self.add_error('old_password', "Current password is incorrect.")
            if new_password1 and new_password2 and new_password1 != new_password2:
                self.add_error('new_password2', "New passwords do not match.")

        return cleaned_data

    def save(self, commit=True):
        student = super().save(commit=False)
        user = student.user

        parts = self.cleaned_data['full_name'].strip().split(' ', 1)
        user.first_name = parts[0]
        user.last_name  = parts[1] if len(parts) > 1 else ''
        user.email      = self.cleaned_data['email']

        new_password1 = self.cleaned_data.get('new_password1')
        if new_password1:
            user.set_password(new_password1)

        if commit:
            user.save()
            student.save()
        return student