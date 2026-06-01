from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from student_portal.models import Student

@login_required(login_url='admin_login')
def student_management_dashboard(request):
    total_students = Student.objects.count()
    recent_students = Student.objects.select_related('user').order_by('-created_at')[:5]

    return render(
        request,
        'student_management/dashboard.html',
        {
            'total_students': total_students,
            'recent_students': recent_students
        }
    )

@login_required(login_url='admin_login')
def student_list(request):
    students = Student.objects.select_related('user').order_by('-created_at')

    return render(
        request,
        'student_management/student_list.html',
        {
            'students': students
        }
    )

@login_required(login_url='admin_login')
def student_detail(request, id):
    student = get_object_or_404(Student.objects.select_related('user'), id=id)

    return render(
        request,
        'student_management/student_detail.html',
        {
            'student': student
        }
    )

@login_required(login_url='admin_login')
def student_activate(request, id):
    student = get_object_or_404(Student, id=id)
    if student.is_active:
        messages.warning(request, "Student is already active.")
    else:
        student.is_active = True
        student.save()
        student.user.is_active = True
        student.user.save()
        messages.success(request, "Student activated successfully.")
    return redirect('student_management:student_detail', id=student.id)

@login_required(login_url='admin_login')
def student_deactivate(request, id):
    student = get_object_or_404(Student, id=id)
    if not student.is_active:
        messages.warning(request, "Student is already inactive.")
    else:
        student.is_active = False
        student.save()
        student.user.is_active = False
        student.user.save()
        messages.warning(request, "Student deactivated successfully.")
    return redirect('student_management:student_detail', id=student.id)

@login_required(login_url='admin_login')
def student_delete(request, id):
    student = get_object_or_404(Student, id=id)
    if request.method == 'POST':
        user = student.user
        student.delete()
        user.delete()
        messages.success(request, "Student deleted successfully.")
        return redirect('student_management:student_list')
    return redirect('student_management:student_detail', id=student.id)
