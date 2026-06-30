from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView

app_name = 'student_portal'

urlpatterns = [
    path('register/', views.student_register, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('login/', views.student_login, name='login'),
    path('dashboard/', views.student_dashboard, name='dashboard'),
    path('logout/', views.student_logout, name='logout'),
    path('plans/',                   views.plan_list_student, name='plan_list'),
path('plans/<uuid:plan_uuid>/checkout/', views.plan_checkout, name='plan_checkout'),
    path('payments/razorpay-callback/', views.razorpay_payment_callback, name='razorpay_callback'),
    path("exams/",                              views.exam_list_student,   name="exam_list"),
   path("exams/<slug:exam_uid>/",       views.exam_preview, name="exam_preview"),
 
    # ── Exam flow ──────────────────────────────────────────────────────────────
    path("exams/<slug:exam_uid>/start/", views.exam_start,   name="exam_start"),
    path("exams/<slug:exam_uid>/submit/", views.exam_submit, name="exam_submit"),
 
    # ── AJAX endpoints ─────────────────────────────────────────────────────────
    path("attempts/<int:attempt_id>/autosave/",   views.exam_autosave,        name="exam_autosave"),
    path("attempts/<int:attempt_id>/tab-switch/", views.exam_log_tab_switch,  name="exam_log_tab_switch"),
 
    # ── Results & history ──────────────────────────────────────────────────────
   path("attempts/<uuid:attempt_slug>/result/", views.exam_result, name="exam_result"),
    path("history/",                           views.exam_history,        name="exam_history"),
    path('profile/',      views.student_detail, name='student_detail'),
    path('profile/edit/', views.student_update, name='student_update'),
    path('quiz/',              views.quiz_setup,    name='quiz_setup'),
    path('quiz/generate/',     views.quiz_generate, name='quiz_generate'),
    path('quiz/<int:attempt_id>/submit/',  views.quiz_submit,  name='quiz_submit'),
   path('quiz/<slug:slug>/result/', views.quiz_result, name='quiz_result'),
    path('quiz/history/',      views.quiz_history,  name='quiz_history'),
    path(
        'notifications/',
        views.get_notifications,
        name='get_notifications'
    ),
    path('notifications/read/', views.mark_notifications_read, name='mark_notifications_read'),
     path('home/', views.landing_page, name='home'),
    
    # Password Reset URLs
    path('password-reset/', 
     views.StudentPasswordResetView.as_view(), 
     name='password_reset'),
    
    path('password-reset/done/', 
         auth_views.PasswordResetDoneView.as_view(
             template_name='student_portal/password_reset_done.html'
         ), 
         name='password_reset_done'),
    
    path('password-reset-confirm/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(
             template_name='student_portal/password_reset_confirm.html',
             success_url=reverse_lazy('student_portal:password_reset_complete')
         ), 
         name='password_reset_confirm'),
    
    path('password-reset-complete/',
     RedirectView.as_view(url=reverse_lazy('student_portal:login')),
     name='password_reset_complete'),
]
