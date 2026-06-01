from django.urls import path
from . import views

app_name = 'student_management'

urlpatterns = [
    path('', views.student_management_dashboard, name='dashboard'),
    path('students/', views.student_list, name='student_list'),
    path('students/<int:id>/', views.student_detail, name='student_detail'),
    path('students/<int:id>/activate/', views.student_activate, name='student_activate'),
    path('students/<int:id>/deactivate/', views.student_deactivate, name='student_deactivate'),
    path('students/<int:id>/delete/', views.student_delete, name='student_delete'),
]
