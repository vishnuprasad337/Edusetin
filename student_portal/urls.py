from django.urls import path, reverse_lazy
from django.contrib.auth import views as auth_views
from . import views

app_name = 'student_portal'

urlpatterns = [
    path('register/', views.student_register, name='register'),
    path('verify-otp/', views.verify_otp, name='verify_otp'),
    path('resend-otp/', views.resend_otp, name='resend_otp'),
    path('login/', views.student_login, name='login'),
    path('dashboard/', views.student_dashboard, name='dashboard'),
    path('logout/', views.student_logout, name='logout'),
    
    # Password Reset URLs
    path('password-reset/', 
         auth_views.PasswordResetView.as_view(
             template_name='student_portal/password_reset.html',
             email_template_name='student_portal/password_reset_email.html',
             subject_template_name='student_portal/password_reset_subject.txt',
             success_url=reverse_lazy('student_portal:password_reset_done')
         ), 
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
         auth_views.PasswordResetCompleteView.as_view(
             template_name='student_portal/password_reset_complete.html'
         ), 
         name='password_reset_complete'),
]
