from django.shortcuts import render, get_object_or_404, redirect
from django.http import FileResponse, Http404
from django.conf import settings
import os
import io
import re
import pandas as pd
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from student_portal.models import Student
from .models import Subject, Question


def normalize_question(text):
    text = text.lower().strip()

    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text)

    # Remove spaces around punctuation and mathematical operators
    text = re.sub(
        r'\s*([?.!,;:+\-*/=])\s*',
        r'\1',
        text
    )

    return text


# ─────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────

@login_required(login_url='admin_login')
def student_management_dashboard(request):
    total_students = Student.objects.count()
    total_subjects = Subject.objects.count()
    total_questions = Question.objects.count()
    total_pyqs = Question.objects.filter(source='PYQ').count()
    active_questions = Question.objects.filter(is_active=True).count()
    inactive_questions = Question.objects.filter(is_active=False).count()

    recent_students = Student.objects.select_related('user').order_by('-created_at')[:5]
    recent_subjects = Subject.objects.order_by('-created_at')[:5]
    recent_questions = Question.objects.select_related('subject').order_by('-created_at')[:5]

    return render(request, 'student_management/dashboard.html', {
        'total_students': total_students,
        'total_subjects': total_subjects,
        'total_questions': total_questions,
        'total_pyqs': total_pyqs,
        'active_questions': active_questions,
        'inactive_questions': inactive_questions,
        'recent_students': recent_students,
        'recent_subjects': recent_subjects,
        'recent_questions': recent_questions,
    })


# ─────────────────────────────────────────────
# STUDENTS
# ─────────────────────────────────────────────

@login_required(login_url='admin_login')
def student_list(request):
    students = Student.objects.select_related('user').order_by('-created_at')
    return render(request, 'student_management/student_list.html', {'students': students})


@login_required(login_url='admin_login')
def student_detail(request, id):
    student = get_object_or_404(Student.objects.select_related('user'), id=id)
    return render(request, 'student_management/student_detail.html', {'student': student})


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


# ─────────────────────────────────────────────
# SUBJECTS
# ─────────────────────────────────────────────

@login_required(login_url='admin_login')
def subject_list(request):
    subjects = Subject.objects.order_by('-created_at')
    return render(request, 'student_management/subject_list.html', {'subjects': subjects})


@login_required(login_url='admin_login')
def subject_create(request):
    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not name:
            messages.error(request, "Subject name is required.")
            return render(request, 'student_management/subject_create.html', {
                'post_data': request.POST
            })

        if Subject.objects.filter(name__iexact=name).exists():
            messages.error(request, f"A subject with the name \"{name}\" already exists.")
            return render(request, 'student_management/subject_create.html', {
                'post_data': request.POST
            })

        subject = Subject.objects.create(
            name=name,
            description=description or None,
            is_active=is_active,
        )
        messages.success(request, f"Subject \"{subject.name}\" created successfully.")
        return redirect('student_management:subject_list')

    return render(request, 'student_management/subject_create.html', {})


@login_required(login_url='admin_login')
def subject_edit(request, id):
    subject = get_object_or_404(Subject, id=id)

    if request.method == 'POST':
        name = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        is_active = request.POST.get('is_active') == 'on'

        if not name:
            messages.error(request, "Subject name is required.")
            return render(request, 'student_management/subject_edit.html', {'subject': subject})

        if Subject.objects.filter(name__iexact=name).exclude(id=id).exists():
            messages.error(request, f"Another subject with the name \"{name}\" already exists.")
            return render(request, 'student_management/subject_edit.html', {'subject': subject})

        subject.name = name
        subject.description = description or None
        subject.is_active = is_active
        subject.save()
        messages.success(request, f"Subject \"{subject.name}\" updated successfully.")
        return redirect('student_management:subject_list')

    return render(request, 'student_management/subject_edit.html', {'subject': subject})


@login_required(login_url='admin_login')
def subject_activate(request, id):
    subject = get_object_or_404(Subject, id=id)
    if subject.is_active:
        messages.warning(request, "Subject is already active.")
    else:
        subject.is_active = True
        subject.save()
        messages.success(request, "Subject activated successfully.")
    return redirect('student_management:subject_list')


@login_required(login_url='admin_login')
def subject_deactivate(request, id):
    subject = get_object_or_404(Subject, id=id)
    if not subject.is_active:
        messages.warning(request, "Subject is already inactive.")
    else:
        subject.is_active = False
        subject.save()
        messages.warning(request, "Subject deactivated successfully.")
    return redirect('student_management:subject_list')


@login_required(login_url='admin_login')
def subject_delete(request, id):
    subject = get_object_or_404(Subject, id=id)
    if request.method == 'POST':
        name = subject.name
        subject.delete()
        messages.success(request, f"Subject \"{name}\" deleted successfully.")
    return redirect('student_management:subject_list')


# ─────────────────────────────────────────────
# QUESTIONS
# ─────────────────────────────────────────────

@login_required(login_url='admin_login')
def question_list(request):
    questions = Question.objects.select_related('subject').order_by('-created_at')
    subjects = Subject.objects.filter(is_active=True).order_by('name')
    sources = Question.SOURCE_CHOICES
    years = Question.objects.exclude(year__isnull=True).values_list('year', flat=True).distinct().order_by('-year')

    # Filtering logic
    subject_id = request.GET.get('subject')
    source = request.GET.get('source')
    year = request.GET.get('year')

    if subject_id:
        questions = questions.filter(subject_id=subject_id)
    if source:
        questions = questions.filter(source=source)
    if year:
        questions = questions.filter(year=year)

    context = {
        'questions': questions,
        'subjects': subjects,
        'sources': sources,
        'years': years,
        'selected_subject': subject_id,
        'selected_source': source,
        'selected_year': year,
    }
    return render(request, 'student_management/question_list.html', context)


@login_required(login_url='admin_login')
def question_create(request):
    subjects = Subject.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        subject_id = request.POST.get('subject')
        question_text = request.POST.get('question_text', '').strip()
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        option_e = request.POST.get('option_e', '').strip()
        correct_answer = request.POST.get('correct_answer', '').strip()
        source = request.POST.get('source', '').strip() or None
        year_raw = request.POST.get('year', '').strip()
        explanation = request.POST.get('explanation', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        question_image = request.FILES.get('question_image')

        errors = []
        subject = None
        year = None

        if not subject_id:
            errors.append("Please select a subject.")
        else:
            subject = Subject.objects.filter(id=subject_id).first()
            if not subject:
                errors.append("Selected subject does not exist.")

        if not question_text:
            errors.append("Question text is required.")
        if not option_a:
            errors.append("Option A is required.")
        if not option_b:
            errors.append("Option B is required.")
        if not option_c:
            errors.append("Option C is required.")
        if not option_d:
            errors.append("Option D is required.")
        if not correct_answer:
            errors.append("Please select the correct answer.")

        if year_raw:
            try:
                year = int(year_raw)
                if year < 1900 or year > 2100:
                    errors.append("Please enter a valid year between 1900 and 2100.")
            except ValueError:
                errors.append("Year must be a valid number.")

        if not errors and subject and question_text:
            normalized_current = normalize_question(question_text)
            comparison_source = source or 'OTHER'
            existing_qs = Question.objects.filter(subject=subject).values('question_text', 'source', 'year')
            is_duplicate = False
            for eq in existing_qs:
                if normalize_question(eq['question_text']) == normalized_current:
                    existing_source = eq['source'] or 'OTHER'
                    if comparison_source == 'PYQ' and existing_source == 'PYQ':
                        if year == eq['year']:
                            is_duplicate = True
                            break
                    elif comparison_source == existing_source and comparison_source != 'PYQ':
                        is_duplicate = True
                        break
            if is_duplicate:
                errors.append("This question already exists (duplicate detected based on subject, text, source, and year rules).")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'student_management/question_create.html', {
                'subjects': subjects,
                'post_data': request.POST,
            })

        Question.objects.create(
            subject=subject,
            question_text=question_text,
            question_image=question_image,
            option_a=option_a,
            option_b=option_b,
            option_c=option_c,
            option_d=option_d,
            option_e=option_e or None,
            correct_answer=correct_answer,
            explanation=explanation or None,
            source=source,
            year=year,
            is_active=is_active,
        )
        messages.success(request, "Question created successfully.")
        return redirect('student_management:question_list')

    return render(request, 'student_management/question_create.html', {
        'subjects': subjects,
    })


@login_required(login_url='admin_login')
def question_detail(request, id):
    question = get_object_or_404(Question.objects.select_related('subject'), id=id)
    question_options = [
        ('A', question.option_a),
        ('B', question.option_b),
        ('C', question.option_c),
        ('D', question.option_d),
    ]
    if question.option_e:
        question_options.append(('E', question.option_e))
    return render(request, 'student_management/question_detail.html', {
        'question': question,
        'question_options': question_options,
    })


@login_required(login_url='admin_login')
def question_edit(request, id):
    question = get_object_or_404(Question.objects.select_related('subject'), id=id)
    subjects = Subject.objects.filter(is_active=True).order_by('name')

    if request.method == 'POST':
        subject_id = request.POST.get('subject')
        question_text = request.POST.get('question_text', '').strip()
        option_a = request.POST.get('option_a', '').strip()
        option_b = request.POST.get('option_b', '').strip()
        option_c = request.POST.get('option_c', '').strip()
        option_d = request.POST.get('option_d', '').strip()
        option_e = request.POST.get('option_e', '').strip()
        correct_answer = request.POST.get('correct_answer', '').strip()
        source = request.POST.get('source', '').strip() or None
        year_raw = request.POST.get('year', '').strip()
        explanation = request.POST.get('explanation', '').strip()
        is_active = request.POST.get('is_active') == 'on'
        question_image = request.FILES.get('question_image')
        clear_image = request.POST.get('clear_image') == 'on'

        errors = []
        subject = None
        year = None

        if not subject_id:
            errors.append("Please select a subject.")
        else:
            subject = Subject.objects.filter(id=subject_id).first()
            if not subject:
                errors.append("Selected subject does not exist.")

        if not question_text:
            errors.append("Question text is required.")
        if not option_a:
            errors.append("Option A is required.")
        if not option_b:
            errors.append("Option B is required.")
        if not option_c:
            errors.append("Option C is required.")
        if not option_d:
            errors.append("Option D is required.")
        if not correct_answer:
            errors.append("Please select the correct answer.")

        if year_raw:
            try:
                year = int(year_raw)
                if year < 1900 or year > 2100:
                    errors.append("Please enter a valid year between 1900 and 2100.")
            except ValueError:
                errors.append("Year must be a valid number.")

        if not errors and subject and question_text:
            normalized_current = normalize_question(question_text)
            comparison_source = source or 'OTHER'
            existing_qs = Question.objects.filter(subject=subject).exclude(id=id).values('question_text', 'source', 'year')
            is_duplicate = False
            for eq in existing_qs:
                if normalize_question(eq['question_text']) == normalized_current:
                    existing_source = eq['source'] or 'OTHER'
                    if comparison_source == 'PYQ' and existing_source == 'PYQ':
                        if year == eq['year']:
                            is_duplicate = True
                            break
                    elif comparison_source == existing_source and comparison_source != 'PYQ':
                        is_duplicate = True
                        break
            if is_duplicate:
                errors.append("This question already exists (duplicate detected based on subject, text, source, and year rules).")

        if errors:
            for err in errors:
                messages.error(request, err)
            return render(request, 'student_management/question_edit.html', {
                'question': question,
                'subjects': subjects,
            })

        question.subject = subject
        question.question_text = question_text
        question.option_a = option_a
        question.option_b = option_b
        question.option_c = option_c
        question.option_d = option_d
        question.option_e = option_e or None
        question.correct_answer = correct_answer
        question.explanation = explanation or None
        question.source = source
        question.year = year
        question.is_active = is_active

        if clear_image:
            question.question_image = None
        elif question_image:
            question.question_image = question_image

        question.save()
        messages.success(request, "Question updated successfully.")
        return redirect('student_management:question_detail', id=question.id)

    return render(request, 'student_management/question_edit.html', {
        'question': question,
        'subjects': subjects,
    })


@login_required(login_url='admin_login')
def question_activate(request, id):
    question = get_object_or_404(Question, id=id)
    if question.is_active:
        messages.warning(request, "Question is already active.")
    else:
        question.is_active = True
        question.save()
        messages.success(request, "Question activated successfully.")
    return redirect('student_management:question_detail', id=question.id)
@login_required(login_url='admin_login')
def question_deactivate(request, id):
    question = get_object_or_404(Question, id=id)
    if not question.is_active:
        messages.warning(request, "Question is already inactive.")
    else:
        question.is_active = False
        question.save()
        messages.warning(request, "Question deactivated successfully.")
    return redirect('student_management:question_detail', id=question.id)


@login_required(login_url='admin_login')
def question_delete(request, id):
    question = get_object_or_404(Question, id=id)
    if request.method == 'POST':
        question.delete()
        messages.success(request, "Question deleted successfully.")
        return redirect('student_management:question_list')
    return redirect('student_management:question_detail', id=question.id)


@login_required(login_url='admin_login')
def question_import(request):
    import_report = None  # Only set after a POST with a valid file

    if request.method == 'POST':
        excel_file = request.FILES.get('excel_file')

        # ── 1. File presence check ──────────────────────────────────────
        if not excel_file:
            messages.error(request, "No file was uploaded. Please select an Excel file.")
            return redirect('student_management:question_import')

        # ── 2. File format check ────────────────────────────────────────
        filename = excel_file.name.lower()
        if not (filename.endswith('.xlsx') or filename.endswith('.xls')):
            messages.error(request, "Invalid file format. Only .xlsx and .xls files are accepted.")
            return redirect('student_management:question_import')

        # ── 3. Parse Excel ──────────────────────────────────────────────
        try:
            file_bytes = io.BytesIO(excel_file.read())
            df = pd.read_excel(file_bytes, engine='openpyxl')
        except Exception as e:
            messages.error(request, f"Could not read the Excel file. Please check the file is valid. ({e})")
            return redirect('student_management:question_import')

        # ── 4. Required columns check ───────────────────────────────────
        required_columns = [
            'Subject', 'Question', 'Option A', 'Option B',
            'Option C', 'Option D', 'Correct Answer',
        ]
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            messages.error(
                request,
                f"Missing required column(s): {', '.join(missing_columns)}. "
                "Please use the provided sample template."
            )
            return redirect('student_management:question_import')

        # ── 5. Process rows ─────────────────────────────────────────────
        VALID_ANSWERS = {'A', 'B', 'C', 'D', 'E'}
        VALID_SOURCES = {'PYQ', 'EDUSETIN', 'OTHER'}

        imported_count = 0
        duplicate_count = 0
        failed_count = 0
        error_rows = []    # list of dicts: {row, column, value, message}
        duplicate_rows = []  # list of dicts: {row, message}
        
        existing_questions_cache = {}

        for row_num, (_, row) in enumerate(df.iterrows(), start=2):

            def get_cell(col_name, _row=row):
                """Return stripped string value or empty string for a cell."""
                val = _row.get(col_name, None)
                try:
                    if pd.isna(val):
                        return ''
                except (TypeError, ValueError):
                    pass
                return str(val).strip() if val is not None else ''

            subject_name   = get_cell('Subject')
            question_text  = get_cell('Question')
            option_a       = get_cell('Option A')
            option_b       = get_cell('Option B')
            option_c       = get_cell('Option C')
            option_d       = get_cell('Option D')
            option_e       = get_cell('Option E') if 'Option E' in df.columns else ''
            correct_answer = get_cell('Correct Answer').upper()
            source_raw     = get_cell('Source').upper() if 'Source' in df.columns else ''
            year_raw       = get_cell('Year') if 'Year' in df.columns else ''
            explanation    = get_cell('Explanation') if 'Explanation' in df.columns else ''

            # ── Per-row validation — collect structured errors ──────────
            row_has_error = False
            subject = None

            def add_error(column, value, message):
                nonlocal row_has_error
                row_has_error = True
                error_rows.append({
                    'row': row_num,
                    'column': column,
                    'value': value if value else 'Empty',
                    'message': message,
                })

            if not subject_name:
                add_error('Subject', subject_name, 'Subject is required')
            else:
                subject = Subject.objects.filter(name__iexact=subject_name).first()
                if not subject:
                    add_error('Subject', subject_name, f"Subject not found in database")

            if not question_text:
                add_error('Question', question_text, 'Question text is required')

            if not option_a:
                add_error('Option A', option_a, 'Option A is required')
            if not option_b:
                add_error('Option B', option_b, 'Option B is required')
            if not option_c:
                add_error('Option C', option_c, 'Option C is required')
            if not option_d:
                add_error('Option D', option_d, 'Option D is required')

            if not correct_answer:
                add_error('Correct Answer', correct_answer, 'Correct Answer is required')
            elif correct_answer not in VALID_ANSWERS:
                add_error('Correct Answer', correct_answer, 'Must be A, B, C, D, or E')

            source = None
            if source_raw:
                if source_raw not in VALID_SOURCES:
                    add_error('Source', source_raw, 'Must be PYQ, EDUSETIN, or OTHER')
                else:
                    source = source_raw

            year = None
            if year_raw:
                try:
                    year = int(float(year_raw))
                    if year < 1900 or year > 2100:
                        add_error('Year', year_raw, 'Must be between 1900 and 2100')
                        year = None
                except (ValueError, TypeError):
                    add_error('Year', year_raw, 'Must be a valid number')

            if row_has_error:
                failed_count += 1
                continue

            # ── Duplicate check ─────────────────────────────────────────
            if subject.id not in existing_questions_cache:
                existing_qs = Question.objects.filter(subject=subject).values('question_text', 'source', 'year')
                existing_questions_cache[subject.id] = [
                    {
                        'text': normalize_question(q['question_text']),
                        'source': q['source'] or 'OTHER',
                        'year': q['year']
                    }
                    for q in existing_qs
                ]

            normalized_current = normalize_question(question_text)
            comparison_source = source or 'OTHER'
            
            is_duplicate = False
            for eq in existing_questions_cache[subject.id]:
                if eq['text'] == normalized_current:
                    existing_source = eq['source']
                    # If both are PYQ, check the year
                    if comparison_source == 'PYQ' and existing_source == 'PYQ':
                        if year == eq['year']:
                            is_duplicate = True
                            break
                    # If both are from the same source (non-PYQ), ignore the year and match
                    elif comparison_source == existing_source and comparison_source != 'PYQ':
                        is_duplicate = True
                        break

            if is_duplicate:
                duplicate_count += 1
                duplicate_rows.append({'row': row_num, 'message': 'Question already exists'})
                continue

            # ── Create question ─────────────────────────────────────────
            try:
                Question.objects.create(
                    subject=subject,
                    question_text=question_text,
                    option_a=option_a,
                    option_b=option_b,
                    option_c=option_c,
                    option_d=option_d,
                    option_e=option_e or None,
                    correct_answer=correct_answer,
                    source=source,
                    year=year,
                    explanation=explanation or None,
                    is_active=True,
                )
                imported_count += 1
                existing_questions_cache[subject.id].append({
                    'text': normalized_current,
                    'source': source or 'OTHER',
                    'year': year
                })
            except Exception as e:
                failed_count += 1
                error_rows.append({
                    'row': row_num,
                    'column': '—',
                    'value': '—',
                    'message': f"Database error: {e}",
                })

        # ── 6. Build structured import report ───────────────────────────
        import_report = {
            'total_rows': len(df),
            'imported': imported_count,
            'duplicates': duplicate_count,
            'failed': failed_count,
            'errors': error_rows,
            'duplicate_rows': duplicate_rows,
        }

    return render(request, 'student_management/question_import.html', {
        'import_report': import_report,
    })





@login_required(login_url='admin_login')
def download_question_template(request):
    file_path = os.path.join(
        settings.BASE_DIR, 
        'student_management', 'static', 'student_management', 'downloads', 'sample_question_import.xlsx'
    )
    
    if os.path.exists(file_path):
        response = FileResponse(
            open(file_path, 'rb'), 
            as_attachment=True, 
            filename="sample_question_import.xlsx"
        )
        response['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        return response
    else:
        messages.error(request, "Sample template file not found.")
        return redirect('student_management:question_import')

