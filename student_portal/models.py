from django.db import models
from django.contrib.auth.models import User

class Student(models.Model):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE
    )
    full_name = models.CharField(
        max_length=255
    )
    phone_number = models.CharField(max_length=15, null=True, blank=True)
    is_active = models.BooleanField(
        default=True
    )
    profile_image = models.ImageField(
        upload_to='student_profiles/',
        null=True,
        blank=True
    )
    created_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return self.full_name
import uuid
class ExamAttempt(models.Model):
    """Records a single student sitting for an exam."""
 
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_SUBMITTED   = "submitted"
    STATUS_TIMED_OUT   = "timed_out"
 
    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_SUBMITTED,   "Submitted"),
        (STATUS_TIMED_OUT,   "Timed Out"),
    ]
    
    slug = models.UUIDField(unique=True, editable=False, null=True, blank=True)
    student = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="exam_attempts",
    )
    # String reference avoids circular import with student_management
    exam = models.ForeignKey(
        "student_management.Exam",
        on_delete=models.CASCADE,
        related_name="attempts",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=STATUS_IN_PROGRESS,
    )
 
    # Timing
    started_at         = models.DateTimeField(auto_now_add=True)
    submitted_at       = models.DateTimeField(null=True, blank=True)
    time_taken_seconds = models.PositiveIntegerField(default=0)
 
    # Scoring — computed on submit, cached here so result page is fast
    total_questions = models.PositiveIntegerField(default=0)
    correct_count   = models.PositiveIntegerField(default=0)
    wrong_count     = models.PositiveIntegerField(default=0)
    skipped_count   = models.PositiveIntegerField(default=0)
    marks_earned    = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_marks     = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    percentage      = models.DecimalField(max_digits=5, decimal_places=2, default=0)
 
    # Integrity monitoring
    tab_switch_count = models.PositiveIntegerField(default=0)
 
    class Meta:
        ordering = ["-started_at"]
    
    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = uuid.uuid4()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.student} | {self.exam} | {self.get_status_display()}"
 
    @property
    def grade(self):
        p = float(self.percentage)
        if p >= 80:
            return "Excellent"
        if p >= 60:
            return "Good"
        if p >= 40:
            return "Average"
        return "Needs Improvement"
 
    @property
    def subject_performance(self):
        """
        Returns a dict keyed by subject name:
          { 'History': {'correct': 3, 'total': 5, 'percentage': 60.0}, ... }
        """
        perf = {}
        for response in self.responses.select_related("question__subject"):
            subj = response.question.subject.name
            if subj not in perf:
                perf[subj] = {"correct": 0, "total": 0}
            perf[subj]["total"] += 1
            if response.is_correct:
                perf[subj]["correct"] += 1
        for subj in perf:
            total   = perf[subj]["total"]
            correct = perf[subj]["correct"]
            perf[subj]["percentage"] = round((correct / total * 100) if total else 0, 1)
        return perf
 
 
class AttemptResponse(models.Model):
    """
    One row per question per ExamAttempt.
    Written by auto-save during the exam and finalised on submit.
    """
 
    attempt = models.ForeignKey(
        ExamAttempt,
        on_delete=models.CASCADE,
        related_name="responses",
    )
    question = models.ForeignKey(
        "student_management.Question",
        on_delete=models.CASCADE,
        related_name="attempt_responses",
    )
 
    # Blank when the student skipped the question
    selected_answer = models.CharField(max_length=1, blank=True, default="")
    is_correct      = models.BooleanField(default=False)
    is_marked       = models.BooleanField(default=False)  # flagged for review
 
    class Meta:
        unique_together = [("attempt", "question")]
        ordering = ["question_id"]
 
    def __str__(self):
        status = "✓" if self.is_correct else "✗"
        return (
            f"Attempt#{self.attempt_id} Q#{self.question_id} "
            f"→ {self.selected_answer or '—'} ({status})"
        )

from django.utils.text import slugify

class QuizAttempt(models.Model):
    """One practice quiz session for a student."""

    STATUS_IN_PROGRESS = "in_progress"
    STATUS_SUBMITTED   = "submitted"

    STATUS_CHOICES = [
        (STATUS_IN_PROGRESS, "In Progress"),
        (STATUS_SUBMITTED,   "Submitted"),
    ]

    student  = models.ForeignKey(
        Student,
        on_delete=models.CASCADE,
        related_name="quiz_attempts",
    )
    subject  = models.ForeignKey(
        "student_management.Subject",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_attempts",
    )
    submodule = models.ForeignKey(
        "student_management.SubModule",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="quiz_attempts",
    )

    status             = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_IN_PROGRESS)
    started_at         = models.DateTimeField(auto_now_add=True)
    submitted_at       = models.DateTimeField(null=True, blank=True)

    # Scoring (cached on submit)
    total_questions    = models.PositiveIntegerField(default=0)
    correct_count      = models.PositiveIntegerField(default=0)
    wrong_count        = models.PositiveIntegerField(default=0)
    skipped_count      = models.PositiveIntegerField(default=0)
    marks_earned       = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_marks        = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    percentage         = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    time_taken_seconds = models.PositiveIntegerField(default=0)
    slug               = models.SlugField(max_length=160, blank=True, unique=False)

    class Meta:
        ordering = ["-started_at"]

    def __str__(self):
        scope = self.submodule or self.subject or "All"
        return f"{self.student} | {scope} | {self.get_status_display()}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # After save we have a pk — build a unique slug and update directly
        # to avoid infinite recursion from calling save() again
        if not self.slug or not self.slug.endswith(f"-{self.pk}"):
            base = self._build_base_slug()
            new_slug = f"{base}-{self.pk}"
            QuizAttempt.objects.filter(pk=self.pk).update(slug=new_slug)
            self.slug = new_slug

    def _build_base_slug(self):
        if self.submodule_id and self.submodule:
            return slugify(self.submodule.name)
        if self.subject_id and self.subject:
            return slugify(self.subject.name)
        return "quiz"

    @property
    def grade(self):
        p = float(self.percentage)
        if p >= 80: return "Excellent"
        if p >= 60: return "Good"
        if p >= 40: return "Average"
        return "Needs Improvement"

    @property
    def grade_color(self):
        p = float(self.percentage)
        if p >= 80: return "green"
        if p >= 60: return "cyan"
        if p >= 40: return "orange"
        return "red"

    @property
    def quiz_slug(self):
        """Convenience property — returns the stored slug, falling back to building one."""
        return self.slug or f"{self._build_base_slug()}-{self.pk}"

 
 
class QuizAttemptResponse(models.Model):
    """One row per question in a QuizAttempt."""
 
    attempt  = models.ForeignKey(QuizAttempt, on_delete=models.CASCADE, related_name="responses")
    question = models.ForeignKey(
        "student_management.Question",
        on_delete=models.CASCADE,
        related_name="quiz_responses",
    )
    selected_answer = models.CharField(max_length=1, blank=True, default="")
    is_correct      = models.BooleanField(default=False)
 
    class Meta:
        unique_together = [("attempt", "question")]
        ordering = ["question_id"]
 
    def __str__(self):
        status = "✓" if self.is_correct else "✗"
        return f"Quiz#{self.attempt_id} Q#{self.question_id} → {self.selected_answer or '—'} ({status})"
 
