from django.shortcuts import render

def student_management_dashboard(request):
    return render(request, 'student_management/dashboard.html')

