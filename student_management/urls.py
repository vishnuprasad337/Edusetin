from django.urls import path
from . import views

app_name = 'student_management'

urlpatterns = [
    path('', views.student_management_dashboard, name='dashboard'),
]
