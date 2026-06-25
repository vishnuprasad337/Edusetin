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
from django.http import JsonResponse
from .forms import StudentRegistrationForm, StudentLoginForm
from .models import Student,ExamAttempt, AttemptResponse
from django.views.decorators.http import require_POST
from django.views.decorators.cache import never_cache
from student_management.models import Exam
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
@never_cache
def student_register(request):
    if request.user.is_authenticated:
        if hasattr(request.user, 'student'):
            return redirect('student_portal:dashboard')
        logout(request)

    # ── Save checkout URL if coming from landing page Pay button ────
    next_url = request.GET.get('next', '').strip()
    if next_url and '/checkout/' in next_url:
        request.session['post_auth_redirect'] = next_url
    # ───────────────────────────────────────────────────────────────

    if request.method == 'POST':
        form = StudentRegistrationForm(request.POST)
        if form.is_valid():
            full_name = form.cleaned_data['full_name']
            email     = form.cleaned_data['email']
            password  = form.cleaned_data['password']
            phone_number = form.cleaned_data.get('phone_number', '')

            otp = _generate_otp()

            request.session['registration_data'] = {
                'full_name': full_name,
                'email':     email,
                'password':  password,
                'phone_number': phone_number,   
            }
            request.session['otp']            = otp
            request.session['otp_created_at'] = timezone.now().isoformat()
            request.session['otp_attempts']   = 0

            try:
                _send_otp_email(email, otp)
            except Exception:
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
            phone_number = reg_data.get('phone_number', '') 

            # Double-check email uniqueness (edge-case: someone registered
            # with same email in the 10-min window between sessions)
            if User.objects.filter(email=email).exists():
                login(request, user)   
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
            Student.objects.create(user=user, full_name=full_name,phone_number=phone_number)

            _clear_registration_session(request)

            login(request, user)
            messages.success(request, "Registration successful! Welcome to your dashboard.")
            next_url = request.session.pop('post_auth_redirect', '')
            if next_url:
                return redirect(next_url)
            return redirect('student_portal:plan_list')

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
@never_cache
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
import json
from django.contrib.auth.decorators import login_required
from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import render, redirect
from django.utils import timezone
from django.db.models import Avg, Sum, Count, F

ACCURACY_WINDOW = 10
MIN_ATTEMPTS_FOR_TREND = 4
TREND_RECENT_WINDOW = 5

WEAK_SUBJECT_THRESHOLD = 65
MAX_SUGGESTED_SUBJECTS = 4
MAX_SUBMODULES_PER_SUGGESTION = 4
SPARSE_EXAM_THRESHOLD = 3

MOCK_TEST_TYPE_NAME = 'mock_test'

@never_cache
@login_required(login_url='student_portal:login')
def student_dashboard(request):
    if not hasattr(request.user, 'student'):
        logout(request)
        messages.error(request, "Please login with a student account.")
        return redirect('student_portal:login')

    student     = request.user.student
    now         = timezone.now()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    from django.db.models import Avg, Sum, Case, When, IntegerField
    from student_management.models import Payment, Exam
    from .models import ExamAttempt, AttemptResponse, QuizAttempt

    # ── Active payments & accessible exams ──────────────────────────────────
    active_payments = list(
        student.payments.filter(
            status=Payment.STATUS_SUCCESS,
            expires_at__gt=now,
        ).select_related('plan').prefetch_related('plan__exams')
        .order_by('expires_at')
    )

    for payment in active_payments:
        if payment.expires_at:
            delta = payment.expires_at - now
            payment.days_until_expiry = max(0, delta.days)
        else:
            payment.days_until_expiry = None

    exam_ids = set()
    for payment in active_payments:
        for exam in payment.plan.exams.filter(is_active=True):
            exam_ids.add(exam.id)

    exams = Exam.objects.filter(
        id__in=exam_ids, is_active=True
    ).select_related('exam_type').prefetch_related('subjects')

    exams_by_type = {}
    for exam in exams.order_by('exam_type__name', 'title'):
        label = exam.exam_type.get_name_display()
        exams_by_type.setdefault(label, []).append(exam)

    total_available_exams = sum(len(v) for v in exams_by_type.values())

    # ── Annotate exams with attempt info ────────────────────────────────────
    from .models import ExamAttempt as EA
    for label, exam_list in exams_by_type.items():
        for exam in exam_list:
            exam.attempt_count = EA.objects.filter(exam=exam).count()
            exam.question_count = exam.questions.count() if hasattr(exam, 'questions') else 0
            exam.total_marks_val = getattr(exam, 'total_marks', exam.question_count)
            exam.last_attempt = (
                EA.objects.filter(
                    student=student,
                    exam=exam,
                    status=EA.STATUS_SUBMITTED,
                ).order_by('-submitted_at').first()
            )
            exam.in_progress_attempt = (
                EA.objects.filter(
                    student=student,
                    exam=exam,
                    status=EA.STATUS_IN_PROGRESS,
                ).order_by('-started_at').first()
            )

    # ── Completed exam attempts ──────────────────────────────────────────────
    completed_attempts = ExamAttempt.objects.filter(
        student=student,
        status=ExamAttempt.STATUS_SUBMITTED,
    )

    total_exam_attempts = completed_attempts.count()
    exams_this_month    = completed_attempts.filter(submitted_at__gte=month_start).count()

    overall_agg   = completed_attempts.aggregate(avg_score=Avg('percentage'))
    avg_net_score = round(overall_agg['avg_score'] or 0, 1)

    # ── Answer Breakdown: per-exam filter (JS-driven, no page reload) ────────
    selected_exam_id = request.GET.get('breakdown_exam', '').strip()

    # All-exam totals (always computed for "Overall" pill)
    all_agg = completed_attempts.aggregate(
        tot_correct=Sum('correct_count'),
        tot_wrong=Sum('wrong_count'),
        tot_skipped=Sum('skipped_count'),
    )
    total_correct_all  = all_agg['tot_correct']  or 0
    total_wrong_all    = all_agg['tot_wrong']    or 0
    total_skipped_all  = all_agg['tot_skipped']  or 0

    # Initial display totals (overall unless exam pre-selected via GET)
    if selected_exam_id:
        sel_agg = completed_attempts.filter(exam_id=selected_exam_id).aggregate(
            tot_correct=Sum('correct_count'),
            tot_wrong=Sum('wrong_count'),
            tot_skipped=Sum('skipped_count'),
        )
        total_correct  = sel_agg['tot_correct']  or 0
        total_wrong    = sel_agg['tot_wrong']    or 0
        total_skipped  = sel_agg['tot_skipped']  or 0
    else:
        total_correct  = total_correct_all
        total_wrong    = total_wrong_all
        total_skipped  = total_skipped_all

    total_answered = total_correct + total_wrong + total_skipped or 1
    correct_pct  = round(total_correct  / total_answered * 100, 1)
    wrong_pct    = round(total_wrong    / total_answered * 100, 1)
    skipped_pct  = round(total_skipped  / total_answered * 100, 1)

    # Exam options for the filter dropdown (only exams the student has attempted)
    breakdown_exam_rows = list(
        completed_attempts
        .select_related('exam')
        .values('exam__id', 'exam__title')
        .distinct()
        .order_by('exam__title')
    )

    breakdown_exam_options = [
        {'id': row['exam__id'], 'title': row['exam__title']}
        for row in breakdown_exam_rows
    ]

    # Build per-exam breakdown dict for JS (one DB query per exam — kept small)
    exam_breakdown_data = {}
    for row in breakdown_exam_rows:
        eid = row['exam__id']
        agg = completed_attempts.filter(exam_id=eid).aggregate(
            c=Sum('correct_count'),
            w=Sum('wrong_count'),
            s=Sum('skipped_count'),
        )
        exam_breakdown_data[str(eid)] = {
            'correct':  agg['c'] or 0,
            'wrong':    agg['w'] or 0,
            'skipped':  agg['s'] or 0,
        }
    exam_breakdown_json = json.dumps(exam_breakdown_data)

    # ── Accuracy & trend ────────────────────────────────────────────────────
    attempts_chrono = list(
        completed_attempts
        .filter(submitted_at__isnull=False)
        .order_by('submitted_at')
    )
    attempt_count = len(attempts_chrono)

    def _accuracy(a):
        total = a.total_questions or (a.correct_count + a.wrong_count + a.skipped_count) or 1
        return (a.correct_count / total) * 100

    recent_for_accuracy = attempts_chrono[-ACCURACY_WINDOW:] if attempts_chrono else []
    if recent_for_accuracy:
        window_correct = sum(a.correct_count for a in recent_for_accuracy)
        window_total   = sum(
            a.total_questions or (a.correct_count + a.wrong_count + a.skipped_count)
            for a in recent_for_accuracy
        ) or 1
        accuracy_rate = round(window_correct / window_total * 100, 1)
    else:
        accuracy_rate = 0

    trend_qs = list(
        completed_attempts
        .filter(submitted_at__isnull=False)
        .order_by('-submitted_at')
        .values('exam__title', 'percentage', 'submitted_at')[:10]
    )
    trend_qs.reverse()
    exam_trend_labels = [a['submitted_at'].strftime('%d %b') for a in trend_qs]
    exam_trend_scores = [float(a['percentage'] or 0) for a in trend_qs]

    has_trend_data = attempt_count >= MIN_ATTEMPTS_FOR_TREND

    if has_trend_data:
        recent_n      = min(TREND_RECENT_WINDOW, attempt_count // 2)
        recent_block  = attempts_chrono[-recent_n:]
        older_block   = attempts_chrono[:-recent_n]
        recent_avg    = sum(_accuracy(a) for a in recent_block) / len(recent_block)
        older_avg     = sum(_accuracy(a) for a in older_block)  / len(older_block)
        accuracy_trend = round(recent_avg - older_avg, 1)
    else:
        accuracy_trend = 0

    # ── Quiz attempts ────────────────────────────────────────────────────────
    completed_quizzes   = QuizAttempt.objects.filter(
        student=student, status=QuizAttempt.STATUS_SUBMITTED
    )
    total_quiz_attempts = completed_quizzes.count()
    quizzes_this_month  = completed_quizzes.filter(submitted_at__gte=month_start).count()

    quiz_trend_qs = list(
        completed_quizzes.select_related('subject')
        .filter(submitted_at__isnull=False)
        .order_by('-submitted_at')
        .values('subject__name', 'percentage', 'submitted_at')[:10]
    )
    quiz_trend_qs.reverse()
    quiz_trend_labels = [a['submitted_at'].strftime('%d %b') for a in quiz_trend_qs]
    quiz_trend_scores  = [float(a['percentage'] or 0) for a in quiz_trend_qs]

    # ── Subject performance ──────────────────────────────────────────────────
    subj_qs = (
        AttemptResponse.objects
        .filter(attempt__student=student, attempt__status=ExamAttempt.STATUS_SUBMITTED)
        .values('question__subject__name')
        .annotate(
            avg_correct=Avg(
                Case(When(is_correct=True, then=1), default=0, output_field=IntegerField())
            ) * 100
        )
        .order_by('-avg_correct')
    )
    subject_performance = [
        {'name': s['question__subject__name'], 'avg_score': round(s['avg_correct'] or 0, 1)}
        for s in subj_qs if s['question__subject__name']
    ]
    subject_score_map = {s['name']: s['avg_score'] for s in subject_performance}

    platform_subj_avg = {}
    platform_qs = (
        AttemptResponse.objects
        .filter(attempt__status=ExamAttempt.STATUS_SUBMITTED)
        .values('question__subject__name')
        .annotate(
            platform_avg=Avg(
                Case(When(is_correct=True, then=1), default=0, output_field=IntegerField())
            ) * 100
        )
    )
    for row in platform_qs:
        if row['question__subject__name']:
            platform_subj_avg[row['question__subject__name']] = round(row['platform_avg'] or 0, 1)

    subject_comparison = [
        {
            'name':       s['name'],
            'your_score': s['avg_score'],
            'avg_score':  platform_subj_avg.get(s['name'], 0),
        }
        for s in subject_performance
    ]

    # ── Platform rank ────────────────────────────────────────────────────────
    student_avg_qs = (
        ExamAttempt.objects
        .filter(status=ExamAttempt.STATUS_SUBMITTED)
        .values('student')
        .annotate(avg_pct=Avg('percentage'))
    )
    students_above  = sum(1 for s in student_avg_qs if float(s['avg_pct'] or 0) > float(avg_net_score))
    total_students  = student_avg_qs.count() or 1
    rank            = students_above + 1
    rank_percentile = round((1 - students_above / total_students) * 100)

    # ── Recent activity ──────────────────────────────────────────────────────
    recent_exam_attempts = (
        completed_attempts
        .select_related('exam__exam_type')
        .order_by('-submitted_at')[:8]
    )
    recent_quiz_attempts = (
        completed_quizzes
        .select_related('subject', 'submodule')
        .order_by('-submitted_at')[:8]
    )

    # ── Suggested quizzes ────────────────────────────────────────────────────
    show_suggested_quizzes = True
    suggested_quizzes = []

    if show_suggested_quizzes:
        from student_management.models import Subject, SubModule

        accessible_subject_ids = _get_accessible_subject_ids(student)

        if accessible_subject_ids:
            accessible_subjects = (
                Subject.objects.filter(id__in=accessible_subject_ids, is_active=True)
                .order_by('name')
            )

            attempted_submodule_ids = set(
                QuizAttempt.objects.filter(
                    student=student,
                    submodule__isnull=False,
                ).values_list('submodule_id', flat=True)
            )

            scored_candidates = []
            for subj in accessible_subjects:
                avg_score = subject_score_map.get(subj.name)
                has_score = avg_score is not None

                accessible_sm_ids = _get_accessible_submodule_ids(student, subj.id)
                unattempted_submodules = []
                if accessible_sm_ids:
                    sm_qs = (
                        SubModule.objects.filter(
                            id__in=accessible_sm_ids,
                            is_active=True,
                        )
                        .exclude(id__in=attempted_submodule_ids)
                        .order_by('order', 'name')[:MAX_SUBMODULES_PER_SUGGESTION]
                    )
                    for sm in sm_qs:
                        unattempted_submodules.append({
                            'name':           sm.name,
                            'icon':           _icon_for_name(sm.name),
                            'question_count': sm.questions.count() if hasattr(sm, 'questions') else None,
                        })

                is_weak = (not has_score) or (avg_score < WEAK_SUBJECT_THRESHOLD)
                if not is_weak and not unattempted_submodules:
                    continue

                sort_key = avg_score if has_score else -1

                scored_candidates.append({
                    'subject_name':  subj.name,
                    'subject_id':    subj.id,
                    'subject_image_url': subj.image.url if subj.image else None,
                    'has_score':     has_score,
                    'avg_score':     avg_score or 0,
                    'attempt_count': completed_quizzes.filter(subject=subj).count(),
                    'question_count': subj.questions.count() if hasattr(subj, 'questions') else None,
                    'submodules':    unattempted_submodules,
                    '_sort_key':     sort_key,
                })

            scored_candidates.sort(key=lambda c: c['_sort_key'])
            suggested_quizzes = scored_candidates[:MAX_SUGGESTED_SUBJECTS]
            for c in suggested_quizzes:
                c.pop('_sort_key', None)

    # ── Context ──────────────────────────────────────────────────────────────
    context = {
        'student':                  student,
        'active_payments':          active_payments,
        'has_active_subscription':  bool(active_payments),
        'exams_by_type':            exams_by_type,

        'accuracy_rate':            accuracy_rate,
        'accuracy_trend':           accuracy_trend,
        'has_trend_data':           has_trend_data,
        'total_exam_attempts':      total_exam_attempts,
        'exams_this_month':         exams_this_month,
        'total_quiz_attempts':      total_quiz_attempts,
        'quizzes_this_month':       quizzes_this_month,
        'rank':                     rank,
        'rank_percentile':          rank_percentile,

        # Breakdown — initial values
        'total_correct':            total_correct,
        'total_wrong':              total_wrong,
        'total_skipped':            total_skipped,
        'correct_pct':              correct_pct,
        'wrong_pct':                wrong_pct,
        'skipped_pct':              skipped_pct,

        # Breakdown — all-exam totals for "Overall" reset
        'total_correct_all':        total_correct_all,
        'total_wrong_all':          total_wrong_all,
        'total_skipped_all':        total_skipped_all,

        # Breakdown — per-exam filter data
        'breakdown_exam_options':   breakdown_exam_options,
        'selected_exam_id':         selected_exam_id,
        'exam_breakdown_json':      exam_breakdown_json,

        'exam_trend_labels_json':   json.dumps(exam_trend_labels),
        'exam_trend_scores_json':   json.dumps(exam_trend_scores),
        'quiz_trend_labels_json':   json.dumps(quiz_trend_labels),
        'quiz_trend_scores_json':   json.dumps(quiz_trend_scores),

        'subject_performance':      subject_performance,
        'subject_comparison':       subject_comparison,

        'recent_exam_attempts':     recent_exam_attempts,
        'recent_quiz_attempts':     recent_quiz_attempts,

        'show_suggested_quizzes':   show_suggested_quizzes,
        'suggested_quizzes':        suggested_quizzes,
    }
    return render(request, 'student_portal/dashboard.html', context)

_ICON_RULES = [
    (['math', 'algebra', 'geometry', 'arithmetic', 'calculus', 'trigon'], 'ti-calculator'),
    (['physic'], 'ti-atom-2'),
    (['chem'], 'ti-flask'),
    (['bio', 'botany', 'zoolog'], 'ti-microscope'),
    (['english', 'language', 'literat', 'grammar', 'writing'], 'ti-abc'),
    (['histor'], 'ti-landmark'),
    (['geog'], 'ti-world'),
    (['comput', 'program', 'ict', 'code', 'informat', 'software'], 'ti-code'),
    (['econom', 'business', 'commerce', 'account', 'finan'], 'ti-chart-line'),
    (['art', 'draw', 'design', 'craft'], 'ti-palette'),
    (['music'], 'ti-music'),
    (['physical education', 'sport', ' pe', 'games', 'gym'], 'ti-run'),
    (['civic', 'social stud', 'polity', 'politic'], 'ti-scale'),
    (['psycholog'], 'ti-brain'),
    (['environ', 'ecology', 'climate'], 'ti-leaf'),
    (['statistic', 'data'], 'ti-chart-bar'),
    (['astro', 'space'], 'ti-rocket'),
    (['moral', 'ethic', 'value'], 'ti-heart'),
    (['chapter', 'unit', 'module', 'topic', 'part', 'section'], 'ti-book'),
]


def _icon_for_name(name):
    n = (name or '').lower()
    for keywords, icon in _ICON_RULES:
        if any(k in n for k in keywords):
            return icon
    return 'ti-bulb'
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



from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils import timezone

from student_management.models import SubscriptionPlan, Payment


def plan_list_student(request):
    """
    Public page — anyone can see plans.
    'Get started' button sends unauthenticated users to register.
    After registration they come back here.
    """
    plans = SubscriptionPlan.objects.filter(is_active=True).prefetch_related(
        'subjects', 'submodules', 'exams'
    ).order_by('price')

    return render(request, 'student_portal/plan_list.html', {'plans': plans})




import json
from datetime import timedelta

import razorpay
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from django.utils import timezone

from student_management.models import SubscriptionPlan, Payment

razorpay_client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))



@login_required(login_url='student_portal:register')
def plan_checkout(request, plan_uuid):
    plan = get_object_or_404(
        SubscriptionPlan.objects.prefetch_related('subjects', 'submodules', 'exams'),
        uuid=plan_uuid,
        is_active=True,
    )
    student = getattr(request.user, 'student', None)

    if student is None:
        messages.error(request, "No student profile found.")
        return redirect('student_portal:register')

    # ── FREE PLAN: activate immediately, skip Razorpay ───────────────
    if plan.price == 0:
        # Don't create duplicate free activations
        already_active = student.payments.filter(
            plan=plan,
            status=Payment.STATUS_SUCCESS,
            expires_at__gt=timezone.now(),
        ).exists()

        if not already_active:
            now = timezone.now()
            Payment.objects.create(
                student=student,
                plan=plan,
                amount=0,
                status=Payment.STATUS_SUCCESS,
                paid_at=now,
                expires_at=now + timedelta(days=plan.duration_days),
            )
        return redirect('student_portal:dashboard')

    # ── PAID PLAN: reuse existing pending order if page is refreshed ──
    existing_payment = student.payments.filter(
        plan=plan,
        status=Payment.STATUS_PENDING,
        razorpay_order_id__isnull=False,
    ).order_by('-created_at').first()

    if existing_payment:
        # Verify the Razorpay order is still valid (not expired)
        try:
            rzp_order = razorpay_client.order.fetch(existing_payment.razorpay_order_id)
            if rzp_order.get('status') == 'created':
                payment = existing_payment
                razorpay_order_id = existing_payment.razorpay_order_id
                amount_paise = int(plan.price * 100)
            else:
                raise Exception("Order no longer valid")
        except Exception:
            existing_payment = None

    if not existing_payment:
        amount_paise = int(plan.price * 100)
        razorpay_order = razorpay_client.order.create({
            'amount': amount_paise,
            'currency': 'INR',
            'payment_capture': 1,
        })
        razorpay_order_id = razorpay_order['id']
        payment = Payment.objects.create(
            student=student,
            plan=plan,
            amount=plan.price,
            status=Payment.STATUS_PENDING,
            razorpay_order_id=razorpay_order_id,
        )

    context = {
        'plan': plan,
        'payment': payment,
        'razorpay_order_id': razorpay_order_id,
        'razorpay_key_id': settings.RAZORPAY_KEY_ID,
        'amount_paise': int(plan.price * 100),
        'amount_display': plan.price,
        'student_name': student.full_name,
        'student_email': request.user.email,
        'plan_subjects': plan.subjects.all(),
        'plan_submodules': plan.submodules.all(),
        'plan_exams': plan.exams.all(),
        'has_specific_content': plan.subjects.exists() or plan.submodules.exists() or plan.exams.exists(),
    }
    return render(request, 'student_portal/plan_checkout.html', context)


@login_required(login_url='student_portal:register')
def razorpay_payment_callback(request):
    if request.method != 'POST':
        return JsonResponse({'status': 'error', 'message': 'Invalid method'}, status=400)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)

    razorpay_order_id   = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature  = data.get('razorpay_signature')

    if not all([razorpay_order_id, razorpay_payment_id, razorpay_signature]):
        return JsonResponse({'status': 'error', 'message': 'Missing payment details'}, status=400)

    payment = get_object_or_404(Payment, razorpay_order_id=razorpay_order_id)

    if payment.student != getattr(request.user, 'student', None):
        return JsonResponse({'status': 'error', 'message': 'Unauthorized'}, status=403)

    # ── Already processed — idempotency guard ────────────────────────
    if payment.status == Payment.STATUS_SUCCESS:
        return JsonResponse({
            'status': 'success',
            'redirect_url': reverse('student_portal:dashboard'),
        })

    # ── Verify Razorpay signature ────────────────────────────────────
    try:
        razorpay_client.utility.verify_payment_signature({
            'razorpay_order_id':   razorpay_order_id,
            'razorpay_payment_id': razorpay_payment_id,
            'razorpay_signature':  razorpay_signature,
        })
    except razorpay.errors.SignatureVerificationError:
        payment.status = Payment.STATUS_FAILED
        payment.save(update_fields=['status'])
        return JsonResponse({'status': 'error', 'message': 'Payment verification failed'}, status=400)

    # ── Signature valid: mark SUCCESS with expiry ────────────────────
    # This single save IS the activation — dashboard reads Payment table
    now = timezone.now()
    payment.razorpay_payment_id = razorpay_payment_id
    payment.razorpay_signature  = razorpay_signature
    payment.status              = Payment.STATUS_SUCCESS
    payment.paid_at             = now
    payment.expires_at          = now + timedelta(days=payment.plan.duration_days)
    payment.save(update_fields=[
        'razorpay_payment_id',
        'razorpay_signature',
        'status',
        'paid_at',
        'expires_at',
    ])

    return JsonResponse({
        'status': 'success',
        'redirect_url': reverse('student_portal:dashboard'),
    })
from django.views.decorators.cache import never_cache
def _get_student_or_redirect(request):
    
    """Return the Student linked to request.user, or None."""
    return getattr(request.user, 'student', None)
 
 
def _has_exam_access(student, exam_id):
    """Return True if the student has an active payment covering this exam."""
    from student_management.models import Payment
    return student.payments.filter(
        status=Payment.STATUS_SUCCESS,
        expires_at__gt=timezone.now(),
        plan__exams__id=exam_id,
    ).exists()
 
 
def _no_cache_response(response):
    """
    Attach headers that prevent the browser from serving this page
    from cache — so the back button cannot restore a submitted exam.
    """
    response['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response['Pragma']        = 'no-cache'
    response['Expires']       = '0'
    return response
 
 
def _compute_score(attempt, exam, post_data):
    questions = list(exam.selected_questions.filter(is_active=True))
 
    correct = wrong = skipped = 0
 
    for question in questions:
        user_answer    = post_data.get(f'q_{question.id}', '').strip().upper()
        correct_answer = question.correct_answer.strip().upper()
 
        if not user_answer:
            skipped   += 1
            is_correct = False
        elif user_answer == correct_answer:
            correct   += 1
            is_correct = True
        else:
            wrong     += 1
            is_correct = False
 
        AttemptResponse.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={
                'selected_answer': user_answer,
                'is_correct':      is_correct,
            },
        )
 
    total_questions = len(questions)
    marks_earned    = (correct * float(exam.marks_per_question)) - (wrong * float(exam.negative_marks))
    total_marks     = total_questions * float(exam.marks_per_question)
    raw_percentage  = (marks_earned / total_marks * 100) if total_marks else 0
    percentage      = round(max(0, raw_percentage), 2)
 
    return {
        'total_questions': total_questions,
        'correct':         correct,
        'wrong':           wrong,
        'skipped':         skipped,
        'marks_earned':    round(marks_earned, 2),
        'total_marks':     total_marks,
        'percentage':      percentage,
    }
 
 
# ─────────────────────────────────────────────
# EXAM LIST
# ─────────────────────────────────────────────
 
@never_cache
@login_required(login_url='student_portal:login')
def exam_list_student(request):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    from student_management.models import Payment, Exam
    from .models import ExamAttempt

    active_payments = student.payments.filter(
        status=Payment.STATUS_SUCCESS,
        expires_at__gt=timezone.now(),
    ).select_related('plan').prefetch_related('plan__exams')

    
    exam_ids = set()
    for payment in active_payments:
        for exam in payment.plan.exams.filter(is_active=True):
            exam_ids.add(exam.id)

    
    exams = (
        Exam.objects.filter(id__in=exam_ids, is_active=True)
        .select_related('exam_type')
        .prefetch_related('subjects', 'selected_questions')
        .order_by('exam_type__name', 'title')
    )

    # Allow-list on STATUS_SUBMITTED (not "exclude in_progress") so a
    # timed_out attempt with zero real answers can't show up as the
    # student's "last attempt" or count toward attempt_count below.
    last_attempts_map = {}
    for attempt in (
        ExamAttempt.objects.filter(
            student=student,
            exam_id__in=exam_ids,
            status=ExamAttempt.STATUS_SUBMITTED,
        ).order_by('-started_at')
    ):
        if attempt.exam_id not in last_attempts_map:
            last_attempts_map[attempt.exam_id] = attempt

    in_progress_map = {}
    for attempt in (
        ExamAttempt.objects.filter(
            student=student,
            exam_id__in=exam_ids,
            status=ExamAttempt.STATUS_IN_PROGRESS,
        ).order_by('-started_at')
    ):
        if attempt.exam_id not in in_progress_map:
            in_progress_map[attempt.exam_id] = attempt

    exams_by_type = {}
    for exam in exams:
        exam.last_attempt        = last_attempts_map.get(exam.id)
        exam.in_progress_attempt = in_progress_map.get(exam.id)
        exam.attempt_count = ExamAttempt.objects.filter(
            exam=exam,
            status=ExamAttempt.STATUS_SUBMITTED,
        ).values('student').distinct().count()
        q_count = exam.selected_questions.count()
        exam.question_count  = q_count
        exam.total_marks_val = round(q_count * float(exam.marks_per_question), 2)

        type_name = exam.exam_type.name
        if type_name not in exams_by_type:
            exams_by_type[type_name] = []
        exams_by_type[type_name].append(exam)

    return render(request, 'student_portal/exam_list.html', {
        'exams_by_type':           exams_by_type,
        'has_active_subscription': active_payments.exists(),
    })
 
 
# ─────────────────────────────────────────────
# EXAM PREVIEW
# ─────────────────────────────────────────────
def get_exam_from_uid(exam_uid):
   
    exam_id = exam_uid.rsplit('-', 1)[-1]
    return get_object_or_404(Exam, id=exam_id)
@never_cache
@login_required(login_url='student_portal:login')
def exam_preview(request, exam_uid):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    # extract id from end of slug  e.g. "neet-mock-test-42" → 42
    try:
        exam_id = int(exam_uid.rsplit('-', 1)[-1])
    except (ValueError, IndexError):
        raise Http404

    if not _has_exam_access(student, exam_id):
        messages.error(request, "You don't have access to this exam.")
        return redirect('student_portal:exam_list')

    from student_management.models import Exam
    exam = get_object_or_404(
        Exam.objects.select_related('exam_type').prefetch_related(
            'subjects', 'submodules', 'selected_questions'
        ),
        id=exam_id,
        is_active=True,
    )

    # Canonical URL check — redirect if slug doesn't match exam title
    if exam_uid != exam.uid:
        return redirect('student_portal:exam_preview', exam_uid=exam.uid, permanent=True)

    question_count = exam.selected_questions.filter(is_active=True).count()
    total_marks    = question_count * float(exam.marks_per_question)

    last_attempt = (
        ExamAttempt.objects.filter(student=student, exam=exam)
        .exclude(status=ExamAttempt.STATUS_IN_PROGRESS)
        .order_by('-started_at')
        .first()
    )

    in_progress = (
        ExamAttempt.objects.filter(
            student=student,
            exam=exam,
            status=ExamAttempt.STATUS_IN_PROGRESS,
        )
        .order_by('-started_at')
        .first()
    )

    return render(request, 'student_portal/exam_preview.html', {
        'exam':           exam,
        'question_count': question_count,
        'total_marks':    total_marks,
        'last_attempt':   last_attempt,
        'in_progress':    in_progress,
    })


# ─────────────────────────────────────────────
# EXAM START
# ─────────────────────────────────────────────
from django.http import Http404
@never_cache
@login_required(login_url='student_portal:login')
def exam_start(request, exam_uid):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    # extract id from slug
    try:
        exam_id = int(exam_uid.rsplit('-', 1)[-1])
    except (ValueError, IndexError):
        raise Http404

    if not _has_exam_access(student, exam_id):
        messages.error(request, "You don't have access to this exam.")
        return redirect('student_portal:exam_list')

    from student_management.models import Exam
    exam = get_object_or_404(Exam, id=exam_id, is_active=True)

    # Canonical URL check
    if exam_uid != exam.uid:
        return redirect('student_portal:exam_start', exam_uid=exam.uid, permanent=True)

    resume_id = request.GET.get('resume')
    if resume_id:
        attempt = get_object_or_404(
            ExamAttempt,
            id=resume_id,
            student=student,
            exam=exam,
        )

        # ── BACK-BUTTON GUARD ─────────────────────────────────────────
        if attempt.status != ExamAttempt.STATUS_IN_PROGRESS:
            messages.warning(request, "This attempt has already been submitted.")
            return redirect('student_portal:exam_result', attempt_slug=attempt.slug)

        elapsed   = (timezone.now() - attempt.started_at).total_seconds()
        time_left = max(0, exam.duration_minutes * 60 - int(elapsed))

        if time_left == 0:
            attempt.status       = ExamAttempt.STATUS_TIMED_OUT
            attempt.submitted_at = timezone.now()
            attempt.save(update_fields=['status', 'submitted_at'])
            messages.warning(request, "Your exam time has expired.")
            return redirect('student_portal:exam_result', attempt_slug=attempt.slug)

    else:
        # Expire any stale in-progress attempts
        ExamAttempt.objects.filter(
            student=student,
            exam=exam,
            status=ExamAttempt.STATUS_IN_PROGRESS,
        ).update(status=ExamAttempt.STATUS_TIMED_OUT)

        attempt   = ExamAttempt.objects.create(student=student, exam=exam)
        time_left = exam.duration_minutes * 60

    questions = list(
        exam.selected_questions.filter(is_active=True)
        .select_related('subject')
        .prefetch_related('media_files')
    )

    existing_responses = {}
    if resume_id:
        for resp in AttemptResponse.objects.filter(attempt=attempt):
            existing_responses[resp.question_id] = {
                'selected_answer': resp.selected_answer,
                'is_marked':       resp.is_marked,
            }

    response = render(request, 'student_portal/exam_start.html', {
        'exam':               exam,
        'attempt':            attempt,
        'questions':          questions,
        'total_questions':    len(questions),
        'duration_seconds':   time_left,
        'existing_responses': json.dumps(existing_responses),
    })

    return _no_cache_response(response)
 
# ─────────────────────────────────────────────
# EXAM AUTO-SAVE  (AJAX)
# ─────────────────────────────────────────────
 
@login_required(login_url='student_portal:login')
@require_POST
def exam_autosave(request, attempt_id):
    student = _get_student_or_redirect(request)
    if not student:
        return JsonResponse({'status': 'error', 'message': 'Not authenticated'}, status=401)
 
    attempt = get_object_or_404(
        ExamAttempt,
        id=attempt_id,
        student=student,
        status=ExamAttempt.STATUS_IN_PROGRESS,
    )
 
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
 
    answers      = data.get('answers', {})
    marked       = data.get('marked', {})
    tab_switches = int(data.get('tab_switches', 0))
 
    if tab_switches > attempt.tab_switch_count:
        attempt.tab_switch_count = tab_switches
        attempt.save(update_fields=['tab_switch_count'])
 
    for qid_str, answer in answers.items():
        try:
            question_id = int(qid_str)
        except ValueError:
            continue
        AttemptResponse.objects.update_or_create(
            attempt=attempt,
            question_id=question_id,
            defaults={
                'selected_answer': str(answer).upper()[:1] if answer else '',
                'is_marked':       bool(marked.get(qid_str, False)),
                'is_correct':      False,
            },
        )
 
    return JsonResponse({'status': 'ok'})
 
 
# ─────────────────────────────────────────────
# TAB-SWITCH LOG  (AJAX)
# ─────────────────────────────────────────────
from django.db.models import F
@login_required(login_url='student_portal:login')
@require_POST
def exam_log_tab_switch(request, attempt_id):
    student = _get_student_or_redirect(request)
    if not student:
        return JsonResponse({'status': 'error'}, status=401)
 
    ExamAttempt.objects.filter(
        id=attempt_id,
        student=student,
        status=ExamAttempt.STATUS_IN_PROGRESS,
    ).update(tab_switch_count=F('tab_switch_count') + 1)
 
    return JsonResponse({'status': 'ok'})
 
 
# ─────────────────────────────────────────────
# EXAM SUBMIT
# ─────────────────────────────────────────────
 
@login_required(login_url='student_portal:login')
@require_POST
def exam_submit(request, exam_uid):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    # extract id from slug
    try:
        exam_id = int(exam_uid.rsplit('-', 1)[-1])
    except (ValueError, IndexError):
        raise Http404

    if not _has_exam_access(student, exam_id):
        messages.error(request, "Access denied.")
        return redirect('student_portal:exam_list')

    from student_management.models import Exam
    exam       = get_object_or_404(Exam, id=exam_id, is_active=True)
    attempt_id = request.POST.get('attempt_id')
    attempt    = get_object_or_404(ExamAttempt, id=attempt_id, student=student, exam=exam)

    # Double-submit guard
    if attempt.status != ExamAttempt.STATUS_IN_PROGRESS:
        return redirect('student_portal:exam_result', attempt_slug=attempt.slug)

    time_taken   = int(request.POST.get('time_taken', 0))
    tab_switches = int(request.POST.get('tab_switches', 0))
    stats        = _compute_score(attempt, exam, request.POST)

    attempt.status             = ExamAttempt.STATUS_SUBMITTED
    attempt.submitted_at       = timezone.now()
    attempt.time_taken_seconds = time_taken
    attempt.total_questions    = stats['total_questions']
    attempt.correct_count      = stats['correct']
    attempt.wrong_count        = stats['wrong']
    attempt.skipped_count      = stats['skipped']
    attempt.marks_earned       = stats['marks_earned']
    attempt.total_marks        = stats['total_marks']
    attempt.percentage         = stats['percentage']
    attempt.tab_switch_count   = max(attempt.tab_switch_count, tab_switches)
    attempt.save()

    return redirect('student_portal:exam_result', attempt_slug=attempt.slug)


 
# ─────────────────────────────────────────────
# EXAM RESULT
# ─────────────────────────────────────────────
 
@never_cache
@login_required(login_url='student_portal:login')
def exam_result(request, attempt_slug):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    attempt = get_object_or_404(
        ExamAttempt.objects.select_related('exam__exam_type', 'student'),
        slug=attempt_slug,   # model field is still 'slug'
        student=student,
    )

    responses = (
        attempt.responses
        .select_related('question__subject')
        .prefetch_related('question__media_files')
        .order_by('question_id')
    )

    enriched_responses = []
    for resp in responses:
        q = resp.question
        options = {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d}
        if q.option_e:
            options['E'] = q.option_e
        enriched_responses.append({
            'response':       resp,
            'question':       q,
            'options':        options,
            'selected':       resp.selected_answer.upper() if resp.selected_answer else '',
            'correct_answer': q.correct_answer.upper(),
            'is_correct':     resp.is_correct,
            'is_skipped':     not resp.selected_answer,
        })

    m, s = divmod(attempt.time_taken_seconds, 60)

    return render(request, 'student_portal/exam_result.html', {
        'attempt':             attempt,
        'exam':                attempt.exam,
        'enriched_responses':  enriched_responses,
        'subject_performance': attempt.subject_performance,
        'time_display':        f"{m}m {s}s",
        'percentage':          float(attempt.percentage),
        'marks_earned':        float(attempt.marks_earned),
        'total_marks':         float(attempt.total_marks),
    })
# ─────────────────────────────────────────────
# EXAM HISTORY
# ─────────────────────────────────────────────
 
@never_cache
@login_required(login_url='student_portal:login')
def exam_history(request):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    attempts = (
        ExamAttempt.objects.filter(student=student)
        .exclude(status=ExamAttempt.STATUS_IN_PROGRESS)
        .select_related('exam__exam_type')
        .order_by('-submitted_at')
    )

    return render(request, 'student_portal/exam_history.html', {
        'attempts': attempts,
    })
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect
from django.contrib.auth import update_session_auth_hash
 
from .forms import StudentUpdateForm
 
@never_cache 
@login_required
def student_detail(request):
    try:
        student = request.user.student
    except Exception:
        messages.error(request, "Student profile not found.")
        return redirect('student_portal:plan_list')
 
    # Fetch all payments ordered by most recent
    payments = student.payments.select_related('plan').order_by('-created_at')
 
    return render(request, 'student_portal/student_detail.html', {
        'student':  student,
        'user':     request.user,
        'form':     StudentUpdateForm(instance=student),
        'payments': payments,
    })
 
@never_cache
@login_required
def student_update(request):
    try:
        student = request.user.student
    except Exception:
        messages.error(request, "Student profile not found.")
        return redirect('student_portal:plan_list')
 
    if request.method == 'POST':
        form = StudentUpdateForm(request.POST, request.FILES, instance=student)
        if form.is_valid():
            updated_student = form.save()
            update_session_auth_hash(request, updated_student.user)
            messages.success(request, "Profile updated successfully.")
            return redirect('student_portal:student_detail')
    else:
        form = StudentUpdateForm(instance=student)
 
    return render(request, 'student_portal/student_update.html', {
        'form':    form,
        'student': student,
    })

import random
from .models import QuizAttempt, QuizAttemptResponse


def _get_accessible_subject_ids(student):
    """Return set of subject IDs the student can access via active payments."""
    from student_management.models import Payment
    from django.utils import timezone

    active_payments = student.payments.filter(
        status=Payment.STATUS_SUCCESS,
        expires_at__gt=timezone.now(),
    ).prefetch_related('plan__subjects', 'plan__submodules', 'plan__exams')

    subject_ids = set()
    for payment in active_payments:
        for subj in payment.plan.subjects.filter(is_active=True):
            subject_ids.add(subj.id)
        for submod in payment.plan.submodules.filter(is_active=True):
            subject_ids.add(submod.subject_id)
        for exam in payment.plan.exams.filter(is_active=True):
            for subj in exam.subjects.filter(is_active=True):
                subject_ids.add(subj.id)
    return subject_ids


def _get_accessible_submodule_ids(student, subject_id):
    """Return set of submodule IDs in a subject accessible to the student."""
    from student_management.models import Payment, SubModule
    from django.utils import timezone

    active_payments = student.payments.filter(
        status=Payment.STATUS_SUCCESS,
        expires_at__gt=timezone.now(),
    ).prefetch_related('plan__subjects', 'plan__submodules', 'plan__exams')

    submodule_ids = set()
    for payment in active_payments:
        if payment.plan.subjects.filter(id=subject_id).exists():
            ids = SubModule.objects.filter(
                subject_id=subject_id, is_active=True
            ).values_list('id', flat=True)
            submodule_ids.update(ids)
        for submod in payment.plan.submodules.filter(subject_id=subject_id, is_active=True):
            submodule_ids.add(submod.id)
        for exam in payment.plan.exams.filter(is_active=True):
            if exam.subjects.filter(id=subject_id).exists():
                ids = SubModule.objects.filter(
                    subject_id=subject_id, is_active=True
                ).values_list('id', flat=True)
                submodule_ids.update(ids)
            for submod in exam.submodules.filter(subject_id=subject_id, is_active=True):
                submodule_ids.add(submod.id)
    return submodule_ids


# ─────────────────────────────────────────────
# QUIZ SETUP  — choose subject / submodule / count
# ─────────────────────────────────────────────
@never_cache
@login_required(login_url='student_portal:login')
def quiz_setup(request):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    from student_management.models import Subject, SubModule
    from django.utils import timezone
    import json

    active_payment = student.payments.filter(
        status='success',
        expires_at__gt=timezone.now(),
    ).select_related('plan').order_by('-expires_at').first()

    if not active_payment:
        return render(request, 'student_portal/quiz_setup.html', {
            'subjects':                Subject.objects.none(),
            'subject_submodules_json': json.dumps({}),
            'has_subscription':        False,
        })

    plan = active_payment.plan
    plan_subjects   = plan.subjects.filter(is_active=True).order_by('name')
    plan_submodules = plan.submodules.filter(is_active=True)

    subject_submodules = {}
    for subj in plan_subjects:
        # ALL submodules of this subject (to show in UI)
        all_sms = SubModule.objects.filter(
            subject=subj, is_active=True
        ).order_by('order', 'name')

        # Only the ones in this plan
        plan_sm_ids = set(
            plan_submodules.filter(subject=subj).values_list('id', flat=True)
        )

        subject_submodules[subj.id] = [
            {
                'id':      sm.id,
                'name':    sm.name,
                'image':   sm.image.url if sm.image else None,
                'in_plan': sm.id in plan_sm_ids,   # ← locked/unlocked flag
            }
            for sm in all_sms
        ]

    return render(request, 'student_portal/quiz_setup.html', {
        'subjects':                plan_subjects,
        'subject_submodules_json': json.dumps(subject_submodules),
        'has_subscription':        True,
    })


# ─────────────────────────────────────────────
# QUIZ GENERATE  — POST: create attempt + questions
# ─────────────────────────────────────────────
@never_cache
@login_required(login_url='student_portal:login')
def quiz_generate(request):
    if request.method != 'POST':
        return redirect('student_portal:quiz_setup')

    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    from student_management.models import Question, Subject, SubModule
    from django.utils import timezone

    # ── fetch active payment ──
    active_payment = student.payments.filter(
        status='success',
        expires_at__gt=timezone.now(),
    ).select_related('plan').order_by('-expires_at').first()

    if not active_payment:
        messages.error(request, "No active subscription found.")
        return redirect('student_portal:plan_list')

    plan = active_payment.plan

    subject_id    = request.POST.get('subject_id', '').strip()
    submodule_ids = request.POST.get('submodule_ids', '').strip()  # comma-separated
    num_questions = int(request.POST.get('num_questions', 10))
    num_questions = max(5, min(num_questions, 50))

    # ── validate subject access ──
    accessible_subject_ids = _get_accessible_subject_ids(student)
    if not subject_id or int(subject_id) not in accessible_subject_ids:
        messages.error(request, "You don't have access to this subject.")
        return redirect('student_portal:quiz_setup')

    subject = Subject.objects.get(id=subject_id)

    # ── plan submodules for this subject ──
    plan_submodule_ids = list(
        plan.submodules.filter(subject_id=subject_id, is_active=True)
        .values_list('id', flat=True)
    )

    # ── block if no submodules in plan for this subject ──
    if not plan_submodule_ids:
        messages.error(request, "No topics are available for this subject in your plan. Please upgrade.")
        return redirect('student_portal:quiz_setup')

    qs = Question.objects.filter(subject_id=subject_id, is_active=True)
    submodule = None

    if submodule_ids:
        # Parse the comma-separated list sent from the form
        requested_ids = []
        for sid in submodule_ids.split(','):
            sid = sid.strip()
            if sid.isdigit():
                requested_ids.append(int(sid))

        # Validate — only allow IDs that are actually in the plan
        plan_sm_set    = set(plan_submodule_ids)
        allowed_ids    = [i for i in requested_ids if i in plan_sm_set]

        if not allowed_ids:
            messages.error(request, "You don't have access to the selected topic(s).")
            return redirect('student_portal:quiz_setup')

        qs = qs.filter(submodule_id__in=allowed_ids)

        # If exactly one submodule selected, pass it for display
        if len(allowed_ids) == 1:
            submodule = SubModule.objects.get(id=allowed_ids[0])

    else:
        # No specific submodule chosen → restrict to ALL plan submodules
        qs = qs.filter(submodule_id__in=plan_submodule_ids)

    # ── pull questions ──
    question_pool = list(qs.values_list('id', flat=True))
    if not question_pool:
        messages.error(request, "No questions available for the selected topic(s).")
        return redirect('student_portal:quiz_setup')

    selected_ids = random.sample(question_pool, min(num_questions, len(question_pool)))
    questions    = list(
        Question.objects.filter(id__in=selected_ids)
        .select_related('subject')
        .prefetch_related('media_files')
    )
    random.shuffle(questions)

    attempt = QuizAttempt.objects.create(
        student=student,
        subject=subject,
        submodule=submodule,
    )

    return render(request, 'student_portal/quiz_take.html', {
        'attempt':   attempt,
        'questions': questions,
        'subject':   subject,
        'submodule': submodule,
    })
 
# ─────────────────────────────────────────────
# QUIZ SUBMIT
# ─────────────────────────────────────────────
@never_cache
@login_required(login_url='student_portal:login')
@require_POST
def quiz_submit(request, attempt_id):
    from django.utils import timezone
    from student_management.models import Question

    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    attempt = get_object_or_404(QuizAttempt, id=attempt_id, student=student)

    if attempt.status != QuizAttempt.STATUS_IN_PROGRESS:
        return redirect('student_portal:quiz_result', slug=attempt.slug)  # ← fixed

    question_ids = request.POST.getlist('question_ids')
    questions    = Question.objects.filter(id__in=question_ids)
    time_taken   = int(request.POST.get('time_taken', 0))

    correct = wrong = skipped = 0
    MARKS_PER_Q = 1.0
    NEG_MARKS   = 0.25

    for question in questions:
        user_answer    = request.POST.get(f'q_{question.id}', '').strip().upper()
        correct_answer = question.correct_answer.strip().upper()

        if not user_answer:
            skipped   += 1
            is_correct = False
        elif user_answer == correct_answer:
            correct   += 1
            is_correct = True
        else:
            wrong     += 1
            is_correct = False

        QuizAttemptResponse.objects.update_or_create(
            attempt=attempt,
            question=question,
            defaults={
                'selected_answer': user_answer,
                'is_correct':      is_correct,
            },
        )

    total_q        = len(question_ids)
    marks          = (correct * MARKS_PER_Q) - (wrong * NEG_MARKS)
    total_marks    = total_q * MARKS_PER_Q
    raw_percentage = (marks / total_marks * 100) if total_marks else 0
    percentage     = round(max(0, raw_percentage), 2)

    attempt.status          = QuizAttempt.STATUS_SUBMITTED
    attempt.submitted_at    = timezone.now()
    attempt.total_questions = total_q
    attempt.correct_count   = correct
    attempt.wrong_count     = wrong
    attempt.skipped_count   = skipped
    attempt.marks_earned    = round(marks, 2)
    attempt.total_marks     = total_marks
    attempt.percentage      = percentage

    if hasattr(attempt, 'time_taken_seconds'):
        attempt.time_taken_seconds = time_taken

    attempt.save()  # ← this triggers slug generation in model's save()

    return redirect('student_portal:quiz_result', slug=attempt.slug)  # ← fixed
 
 

 
# ─────────────────────────────────────────────
# QUIZ RESULT
# ─────────────────────────────────────────────
@never_cache
@login_required(login_url='student_portal:login')
def quiz_result(request, slug):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')

    attempt = get_object_or_404(
        QuizAttempt.objects.select_related('subject', 'submodule'),
        slug=slug, 
        student=student,
    )

    responses = (
        attempt.responses
        .select_related('question__subject')
        .prefetch_related('question__media_files')
        .order_by('question_id')
    )

    enriched = []
    for resp in responses:
        q = resp.question
        options = {'A': q.option_a, 'B': q.option_b, 'C': q.option_c, 'D': q.option_d}
        if q.option_e:
            options['E'] = q.option_e

        selected_clean = (resp.selected_answer or '').strip().upper()

        enriched.append({
            'response':       resp,
            'question':       q,
            'options':        options,
            'selected':       selected_clean,
            'correct_answer': q.correct_answer.upper(),
            'is_correct':     resp.is_correct,
            'is_skipped':     selected_clean == '',
        })

    return render(request, 'student_portal/quiz_result.html', {
        'attempt':    attempt,
        'enriched':   enriched,
        'percentage': float(attempt.percentage),
    })
 
 
# ─────────────────────────────────────────────
# QUIZ HISTORY
# ─────────────────────────────────────────────
@never_cache 
@login_required(login_url='student_portal:login')
def quiz_history(request):
    student = _get_student_or_redirect(request)
    if not student:
        return redirect('student_portal:login')
 
    attempts = (
        QuizAttempt.objects.filter(student=student, status=QuizAttempt.STATUS_SUBMITTED)
        .select_related('subject', 'submodule')
        .order_by('-submitted_at')
    )
 
    return render(request, 'student_portal/quiz_history.html', {'attempts': attempts})
from django.utils.timesince import timesince
@login_required

def get_notifications(request):
    """
    Returns real-time notifications for the student based on:
    - New subscription plans added in the last 30 days
    - New exams added to their accessible plans
    - New subjects / submodules added to their accessible plans
    """
    student = getattr(request.user, 'student', None)
    if not student:
        return JsonResponse({'notifications': [], 'unread_count': 0})
 
    from student_management.models import (
        SubscriptionPlan, Exam, Subject, SubModule, Payment
    )
 
    now = timezone.now()
    cutoff_30 = now - datetime.timedelta(days=30)
    cutoff_7  = now - datetime.timedelta(days=7)
 
    notifications = []
 
    # ── 1. New subscription plans launched (last 30 days) ────────────────────
    new_plans = SubscriptionPlan.objects.filter(
        is_active=True,
        created_at__gte=cutoff_30,
    ).order_by('-created_at')[:5]
 
    for plan in new_plans:
        notifications.append({
            'type':    'new_plan',
            'icon':    'icon-tag',
            'color':   'bg-primary',
            'title':   f'New Plan: {plan.name}',
            'desc':    f'₹{plan.price} · {plan.duration_days} days validity',
            'time':    timesince(plan.created_at) + ' ago',
            'created': plan.created_at.isoformat(),
            'unread':  True,
        })
 
    # ── 2. New exams added to the student's accessible plans ─────────────────
    active_payments = student.payments.filter(
        status=Payment.STATUS_SUCCESS,
        expires_at__gt=now,
    ).prefetch_related('plan__exams')
 
    accessible_exam_ids = set()
    for payment in active_payments:
        for exam in payment.plan.exams.filter(is_active=True):
            accessible_exam_ids.add(exam.id)
 
    new_exams = Exam.objects.filter(
        id__in=accessible_exam_ids,
        created_at__gte=cutoff_7,
    ).select_related('exam_type').order_by('-created_at')[:5]
 
    for exam in new_exams:
        q_count = exam.selected_questions.count()
        notifications.append({
            'type':    'new_exam',
            'icon':    'icon-clipboard-list',
            'color':   'bg-success',
            'title':   f'New Mock Test Added',
            'desc':    f'{exam.title} · {q_count} questions · {exam.duration_minutes} min',
            'time':    timesince(exam.created_at) + ' ago',
            'created': exam.created_at.isoformat(),
            'unread':  True,
        })
 
    # ── 3. New subjects added to accessible plans (last 30 days) ─────────────
    accessible_subject_ids = set()
    for payment in active_payments:
        for subj in payment.plan.subjects.filter(is_active=True):
            accessible_subject_ids.add(subj.id)
 
    new_subjects = Subject.objects.filter(
        id__in=accessible_subject_ids,
        created_at__gte=cutoff_30,
    ).order_by('-created_at')[:5]
 
    for subj in new_subjects:
        notifications.append({
            'type':    'new_subject',
            'icon':    'icon-book-open',
            'color':   'bg-info',
            'title':   f'New Subject Available',
            'desc':    f'{subj.name} added to your plan',
            'time':    timesince(subj.created_at) + ' ago',
            'created': subj.created_at.isoformat(),
            'unread':  True,
        })
 
    # ── 4. New submodules added to accessible subjects (last 30 days) ────────
    accessible_sm_ids = set()
    for payment in active_payments:
        for sm in payment.plan.submodules.filter(is_active=True):
            accessible_sm_ids.add(sm.id)
 
    new_submodules = SubModule.objects.filter(
        id__in=accessible_sm_ids,
        created_at__gte=cutoff_30,
    ).select_related('subject').order_by('-created_at')[:5]
 
    for sm in new_submodules:
        notifications.append({
            'type':    'new_submodule',
            'icon':    'icon-layers',
            'color':   'bg-warning',
            'title':   f'New Topic Added',
            'desc':    f'{sm.name} · {sm.subject.name}',
            'time':    timesince(sm.created_at) + ' ago',
            'created': sm.created_at.isoformat(),
            'unread':  True,
        })
 
    # ── 5. Plan expiry warnings ───────────────────────────────────────────────
    expiring_soon = student.payments.filter(
        status=Payment.STATUS_SUCCESS,
        expires_at__gt=now,
        expires_at__lte=now + datetime.timedelta(days=7),
    ).select_related('plan').order_by('expires_at')
 
    for payment in expiring_soon:
        delta = payment.expires_at - now
        days_left = delta.days
        notifications.append({
            'type':    'expiry_warning',
            'icon':    'icon-clock',
            'color':   'bg-danger',
            'title':   f'Plan Expiring Soon',
            'desc':    f'{payment.plan.name} expires in {days_left} day{"s" if days_left != 1 else ""}',
            'time':    timesince(payment.paid_at) + ' ago' if payment.paid_at else '',
            'created': payment.expires_at.isoformat(),
            'unread':  days_left <= 3,
        })
 
    # Sort all by created date descending
    notifications.sort(key=lambda x: x['created'], reverse=True)
    notifications = notifications[:15]  # cap at 15
 
    unread_count = sum(1 for n in notifications if n['unread'])
 
    return JsonResponse({
        'notifications': notifications,
        'unread_count':  unread_count,
    })
@never_cache
def landing_page(request):
    from student_management.models import SubscriptionPlan
    plans = SubscriptionPlan.objects.filter(is_active=True).prefetch_related(
        'subjects', 'submodules', 'exams'
    ).order_by('price')
    return render(request, 'student_portal/index.html', {'plans': plans})
 






