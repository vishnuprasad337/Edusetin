from django.urls import path
from . import views

app_name = 'student_management'

urlpatterns = [
    # Dashboard
    path('', views.student_management_dashboard, name='dashboard'),

    # Students
    path('students/', views.student_list, name='student_list'),
    path('students/<int:id>/', views.student_detail, name='student_detail'),
    path('students/<int:id>/activate/', views.student_activate, name='student_activate'),
    path('students/<int:id>/deactivate/', views.student_deactivate, name='student_deactivate'),
    path('students/<int:id>/delete/', views.student_delete, name='student_delete'),

    # Subjects
    path('subjects/', views.subject_list, name='subject_list'),
    path('subjects/create/', views.subject_create, name='subject_create'),
    path('subjects/<int:id>/edit/', views.subject_edit, name='subject_edit'),
    path('subjects/<int:id>/activate/', views.subject_activate, name='subject_activate'),
    path('subjects/<int:id>/deactivate/', views.subject_deactivate, name='subject_deactivate'),
    path('subjects/<int:id>/delete/', views.subject_delete, name='subject_delete'),

    # Questions
    path('questions/', views.question_list, name='question_list'),
    path('questions/create/', views.question_create, name='question_create'),
    path('questions/import/', views.question_import, name='question_import'),
    path('questions/import/download-template/', views.download_question_template, name='download_question_template'),
    path('questions/<int:id>/', views.question_detail, name='question_detail'),
    path('questions/<int:id>/edit/', views.question_edit, name='question_edit'),
    path('questions/<int:id>/activate/', views.question_activate, name='question_activate'),
    path('questions/<int:id>/deactivate/', views.question_deactivate, name='question_deactivate'),
    path('questions/<int:id>/delete/', views.question_delete, name='question_delete'),

    # Media Management – Question-level
    path('media/pending/', views.media_pending, name='media_pending'),
    path('media/question/<int:id>/', views.media_upload, name='media_upload'),
    path('media/question/<int:id>/delete/<str:media_type>/', views.media_delete, name='media_delete'),

    # Media Library (two-section page)
    path('media/library/', views.media_library, name='media_library'),

    # Media Assets CRUD (MediaLibrary model)
    path('media/assets/upload/', views.media_assets_upload, name='media_assets_upload'),
    path('media/assets/<int:id>/edit/', views.media_assets_edit, name='media_assets_edit'),
    path('media/assets/<int:id>/delete/', views.media_assets_delete, name='media_assets_delete'),
    path('media/assets/<int:id>/toggle/', views.media_assets_toggle, name='media_assets_toggle'),
    path('media/assets/api/', views.media_assets_api, name='media_assets_api'),

    path('exam-types/',          views.examtype_list, name='examtype_list'),
    path('exam-list',                     views.exam_list,     name='exam_list'),
    path('add/',                 views.exam_add,      name='exam_add'),
    path('<int:pk>/edit/',       views.exam_edit,     name='exam_edit'),
    path("ajax/subjects/",  views.ajax_subjects_by_examtype, name="ajax_subjects_by_examtype"),
    path("ajax/questions/", views.ajax_questions_by_filter,  name="ajax_questions_by_filter"),
    path('submodules/', views.submodule_list, name='submodule_list'),
path('submodules/add/', views.submodule_add, name='submodule_add'),
path('submodules/<slug:slug>/edit/', views.submodule_edit, name='submodule_edit'),
path('submodules/<slug:slug>/delete/', views.submodule_delete, name='submodule_delete'),
path(
    'api/submodules-by-subject/',
    views.submodules_by_subject_api,
    name='submodules_by_subject_api',
),
 path("plans/", views.plan_list, name="plan_list"),
    path("plans/create/", views.plan_create, name="plan_create"),
    path("plans/<int:pk>/", views.plan_detail, name="plan_detail"),
    path("plans/<int:pk>/edit/", views.plan_update, name="plan_update"),
    path("plans/<int:pk>/delete/", views.plan_delete, name="plan_delete"),
    path("payments/",                        views.payment_list,          name="payment_list"),
path("payments/create/",                 views.payment_create,        name="payment_create"),
path("payments/<int:id>/",               views.payment_detail,        name="payment_detail"),
path("payments/<int:id>/update-status/", views.payment_update_status, name="payment_update_status"),
path("payments/<int:id>/delete/",        views.payment_delete,        name="payment_delete"),
]
