from django.shortcuts import render, redirect
from django.contrib.auth import login, authenticate, logout
from django.contrib.auth.models import User
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.mail import send_mail
from django.conf import settings
from django.utils import timezone
import secrets
import datetime

from .forms import StudentRegistrationForm, StudentLoginForm
from .models import Student


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _generate_otp():
    """Return a cryptographically secure 6-digit OTP string."""
    return str(secrets.randbelow(900000) + 100000)


def _send_otp_email(email, otp):
    """Send the OTP verification email."""
    subject = "Verify Your Edusetin Account"
    body = (
        f"Your verification code is:\n\n"
        f"{otp}\n\n"
        f"This code expires in 10 minutes.\n\n"
        f"If you did not request this registration, please ignore this email."
    )
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )


def _clear_registration_session(request):
    """Remove all OTP / registration keys from the session."""
    for key in ('registration_data', 'otp', 'otp_created_at', 'otp_attempts'):
        request.session.pop(key, None)


# ─────────────────────────────────────────────
# REGISTRATION (Step 1)
# ─────────────────────────────────────────────

def student_register(request):
    if request.user.is_authenticated:
        # Only redirect to dashboard if user actually has a Student profile
        if hasattr(request.user, 'student'):
            return redirect('student_portal:dashboard')
        # Non-student authenticated user (e.g. admin) — log them out silently
        logout(request)

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data['full_name']
            email     = form.cleaned_data['email']
            password  = form.cleaned_data['password']

            # ── Generate OTP ────────────────────────────────────────────
            otp = _generate_otp()

            # ── Store registration state in session (no DB writes) ───────
            request.session['registration_data'] = {
                'full_name': full_name,
                'email':     email,
                'password':  password,   # stored only for the ~10-min OTP window
            }
            request.session['otp']            = otp
            request.session['otp_created_at'] = timezone.now().isoformat()
            request.session['otp_attempts']   = 0

            # ── Send OTP email ───────────────────────────────────────────
            try:
                _send_otp_email(email, otp)
            except Exception:
                # If email fails, clean up session and show error
                _clear_registration_session(request)
                messages.error(
                    request,
                    "Failed to send verification email. Please check your email address and try again."
                )
                return render(request, 'student_portal/register.html', {'form': form})

            messages.info(
                request,
                f"A verification code has been sent to {email}. Please check your inbox."
            )
            return redirect('student_portal:verify_otp')
    else:
        form = StudentRegistrationForm()

    return render(request, 'student_portal/register.html', {'form': form})


# ─────────────────────────────────────────────
# OTP VERIFICATION (Step 2)
# ─────────────────────────────────────────────

MAX_OTP_ATTEMPTS = 5
OTP_EXPIRY_MINUTES = 10


def verify_otp(request):
    """Verify the OTP entered by the user and, if correct, create the account."""

    # Guard: must have an active registration session
    if not request.session.get('registration_data'):
        messages.error(request, "No pending registration found. Please register again.")
        return redirect('student_portal:register')

    reg_data = request.session['registration_data']
    masked_email = _mask_email(reg_data.get('email', ''))

    if request.method == 'POST':
        entered_otp = request.POST.get('otp', '').strip()

        # ── Retrieve session state ───────────────────────────────────────
        stored_otp      = request.session.get('otp')
        created_at_str  = request.session.get('otp_created_at')
        attempts        = request.session.get('otp_attempts', 0)

        # ── Attempt limit guard ──────────────────────────────────────────
        if attempts >= MAX_OTP_ATTEMPTS:
            _clear_registration_session(request)
            messages.error(
                request,
                "Too many incorrect attempts. Please register again."
            )
            return redirect('student_portal:register')

        # ── Expiry check ─────────────────────────────────────────────────
        if created_at_str:
            created_at = datetime.datetime.fromisoformat(created_at_str)
            # Make timezone-aware if needed
            if timezone.is_naive(created_at):
                created_at = timezone.make_aware(created_at)
            elapsed = (timezone.now() - created_at).total_seconds()
            if elapsed > OTP_EXPIRY_MINUTES * 60:
                _clear_registration_session(request)
                messages.error(
                    request,
                    "OTP has expired. Please request a new OTP."
                )
                return redirect('student_portal:register')

        # ── OTP comparison ───────────────────────────────────────────────
        if entered_otp == stored_otp:
            # ── Success: create User + Student ───────────────────────────
            email     = reg_data['email']
            password  = reg_data['password']
            full_name = reg_data['full_name']

            # Double-check email uniqueness (edge-case: someone registered
            # with same email in the 10-min window between sessions)
            if User.objects.filter(email=email).exists():
                _clear_registration_session(request)
                messages.error(
                    request,
                    "An account with this email already exists. Please log in."
                )
                return redirect('student_portal:login')

            user = User.objects.create_user(
                username=email,
                email=email,
                password=password,
            )
            Student.objects.create(user=user, full_name=full_name)

            _clear_registration_session(request)

            login(request, user)
            messages.success(request, "Registration successful! Welcome to your dashboard.")
            return redirect('student_portal:dashboard')

        else:
            # ── Wrong OTP ────────────────────────────────────────────────
            attempts += 1
            request.session['otp_attempts'] = attempts
            remaining = MAX_OTP_ATTEMPTS - attempts

            if remaining <= 0:
                _clear_registration_session(request)
                messages.error(
                    request,
                    "Too many incorrect attempts. Please register again."
                )
                return redirect('student_portal:register')

            messages.error(
                request,
                f"Incorrect OTP. You have {remaining} attempt{'s' if remaining != 1 else ''} remaining."
            )

    return render(request, 'student_portal/verify_otp.html', {
        'masked_email': masked_email,
    })


# ─────────────────────────────────────────────
# RESEND OTP
# ─────────────────────────────────────────────

RESEND_COOLDOWN_SECONDS = 60


def resend_otp(request):
    """Regenerate and resend OTP; enforces a 60-second cooldown."""

    if not request.session.get('registration_data'):
        messages.error(request, "No pending registration found. Please register again.")
        return redirect('student_portal:register')

    if request.method == 'POST':
        created_at_str = request.session.get('otp_created_at')

        # ── Cooldown check ───────────────────────────────────────────────
        if created_at_str:
            created_at = datetime.datetime.fromisoformat(created_at_str)
            if timezone.is_naive(created_at):
                created_at = timezone.make_aware(created_at)
            elapsed = (timezone.now() - created_at).total_seconds()
            if elapsed < RESEND_COOLDOWN_SECONDS:
                wait = int(RESEND_COOLDOWN_SECONDS - elapsed)
                messages.warning(
                    request,
                    f"Please wait {wait} second{'s' if wait != 1 else ''} before requesting a new OTP."
                )
                return redirect('student_portal:verify_otp')

        # ── Generate new OTP ─────────────────────────────────────────────
        email = request.session['registration_data']['email']
        otp   = _generate_otp()

        request.session['otp']            = otp
        request.session['otp_created_at'] = timezone.now().isoformat()
        request.session['otp_attempts']   = 0

        try:
            _send_otp_email(email, otp)
            messages.success(request, "A new verification code has been sent to your email.")
        except Exception:
            messages.error(request, "Failed to resend OTP. Please try again.")

    return redirect('student_portal:verify_otp')


# ─────────────────────────────────────────────
# LOGIN
# ─────────────────────────────────────────────

def student_login(request):
    if request.user.is_authenticated:
        # Only redirect to dashboard if user actually has a Student profile
        if hasattr(request.user, 'student'):
            return redirect('student_portal:dashboard')
        # Non-student authenticated user — log them out silently
        logout(request)

    if request.method == 'POST':
        form = StudentLoginForm(request.POST)
        if form.is_valid():
            email    = form.cleaned_data['email']
            password = form.cleaned_data['password']
            user = authenticate(username=email, password=password)
            if user is not None:
                # Ensure the authenticated user has a Student profile
                if not hasattr(user, 'student'):
                    messages.error(
                        request,
                        "No student account found for this email. Please register first."
                    )
                else:
                    login(request, user)
                    return redirect('student_portal:dashboard')
            else:
                messages.error(request, "Invalid email or password.")
    else:
        form = StudentLoginForm()

    return render(request, 'student_portal/login.html', {'form': form})


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

@login_required(login_url='student_portal:login')
def student_dashboard(request):
    # Hard guard: only users with a Student profile may enter
    if not hasattr(request.user, 'student'):
        logout(request)
        messages.error(request, "Please login with a student account.")
        return redirect('student_portal:login')

    student = request.user.student
    return render(request, 'student_portal/dashboard.html', {'student': student})


# ─────────────────────────────────────────────
# LOGOUT
# ─────────────────────────────────────────────

def student_logout(request):
    logout(request)
    return redirect('student_portal:login')


# ─────────────────────────────────────────────
# INTERNAL UTILITIES
# ─────────────────────────────────────────────

def _mask_email(email):
    """Return e.g. 'ab***@gmail.com' for display on the OTP page."""
    try:
        local, domain = email.split('@', 1)
        visible = local[:2] if len(local) >= 2 else local[:1]
        return f"{visible}***@{domain}"
    except Exception:
        return email
