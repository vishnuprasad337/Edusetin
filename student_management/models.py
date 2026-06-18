from django.db import models


class Subject(models.Model):
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name
import uuid
from django.utils.text import slugify


class SubModule(models.Model):
    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='submodules')
    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=220, unique=True, blank=True)
    description = models.TextField(blank=True, null=True)
    image = models.ImageField(upload_to='submodules/', blank=True, null=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['subject__name', 'order', 'name']
        unique_together = ('subject', 'name')
        verbose_name = "Submodule"
        verbose_name_plural = "Submodules"

    def __str__(self):
        return f"{self.subject.name} → {self.name}"

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.name) or f"submodule-{uuid.uuid4().hex[:8]}"
            slug = base_slug
            counter = 1
            while SubModule.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

class Question(models.Model):
    ANSWER_CHOICES = [
        ('A', 'A'),
        ('B', 'B'),
        ('C', 'C'),
        ('D', 'D'),
        ('E', 'E'),
    ]
    SOURCE_CHOICES = [
        ('PYQ', 'PYQ'),
        ('EDUSETIN', 'EDUSETIN'),
        ('OTHER', 'OTHER'),
    ]

    subject = models.ForeignKey(Subject, on_delete=models.CASCADE, related_name='questions')
    submodule = models.ForeignKey(
        SubModule,
        on_delete=models.SET_NULL,
        related_name='questions',
        blank=True,
        null=True,
    )

    question_text = models.TextField()
    option_a = models.TextField()
    option_b = models.TextField()
    option_c = models.TextField()
    option_d = models.TextField()
    option_e = models.TextField(blank=True, null=True)
    correct_answer = models.CharField(max_length=1, choices=ANSWER_CHOICES)
    explanation = models.TextField(blank=True, null=True)
    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, blank=True, null=True)
    year = models.PositiveIntegerField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Per-slot media requirement flags (set by import or manual create/edit)
    requires_question_image = models.BooleanField(default=False)
    requires_option_a_image = models.BooleanField(default=False)
    requires_option_b_image = models.BooleanField(default=False)
    requires_option_c_image = models.BooleanField(default=False)
    requires_option_d_image = models.BooleanField(default=False)
    requires_option_e_image = models.BooleanField(default=False)

    # Derived/cached flag: True when all required slots have a QuestionMedia row
    media_uploaded = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.question_text[:80]

    @property
    def has_media(self):
        """True if any media slot is required."""
        return any([
            self.requires_question_image,
            self.requires_option_a_image,
            self.requires_option_b_image,
            self.requires_option_c_image,
            self.requires_option_d_image,
            self.requires_option_e_image,
        ])


# ─────────────────────────────────────────────
# MEDIA LIBRARY
# ─────────────────────────────────────────────

class MediaLibrary(models.Model):
    """
    Reusable media asset repository.
    Images uploaded here can be referenced by multiple QuestionMedia records
    without duplicating the physical file.
    """
    name = models.CharField(max_length=255, unique=True)
    image = models.ImageField(upload_to='media_library/')
    description = models.TextField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    @property
    def usage_count(self):
        return self.usages.count()

    @property
    def is_in_use(self):
        return self.usages.exists()


class QuestionMedia(models.Model):
    MEDIA_TYPES = [
        ('QUESTION', 'Question'),
        ('OPTION_A', 'Option A'),
        ('OPTION_B', 'Option B'),
        ('OPTION_C', 'Option C'),
        ('OPTION_D', 'Option D'),
        ('OPTION_E', 'Option E'),
    ]

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='media_files'
    )
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    image = models.ImageField(upload_to='question_media/', blank=True, default='')

    # Optional reference to the MediaLibrary asset this image came from.
    # NULL = manually uploaded file. Non-NULL = sourced from library.
    media_library = models.ForeignKey(
        MediaLibrary,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='usages'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('question', 'media_type')]
        ordering = ['media_type']

    def __str__(self):
        return f"Q#{self.question_id} — {self.media_type}"

    @property
    def effective_image(self):
        """
        Returns the authoritative image for this media record.

        - If sourced from Media Library (media_library FK set): returns the
          library asset's current image so any replacement to the library
          asset is automatically reflected here without touching this record.
        - If manually uploaded: returns the locally stored image.
        """
        if self.media_library_id and self.media_library:
            return self.media_library.image
        return self.image


# ─────────────────────────────────────────────
# PENDING MEDIA REFERENCES
# ─────────────────────────────────────────────

class PendingMediaReference(models.Model):
    """
    Stores a record when an Excel import references a MediaLibrary asset
    by name but the asset does not exist at import time.

    This allows the admin to see which images are still needed for a question
    even after the import report is dismissed.
    """
    MEDIA_TYPES = QuestionMedia.MEDIA_TYPES

    question = models.ForeignKey(
        Question,
        on_delete=models.CASCADE,
        related_name='pending_media_refs'
    )
    media_type = models.CharField(max_length=20, choices=MEDIA_TYPES)
    expected_media_name = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [('question', 'media_type')]
        ordering = ['media_type']

    def __str__(self):
        return f"Q#{self.question_id} — {self.media_type} — {self.expected_media_name}"


from django.db import models
from django.core.validators import MinValueValidator



class ExamType(models.Model):
    TYPE_CHOICES = [
        ('PYQ',    'PYQ Test'),
        ('MOCK',   'Mock Test'),
        ('QUIZ',   'Quick Quiz'),
        ('CUSTOM', 'Custom'),
    ]
    name        = models.CharField(max_length=10, choices=TYPE_CHOICES, unique=True)
    description = models.TextField(blank=True, null=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    custom_name = models.CharField(max_length=100, blank=True, null=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        if self.name == 'CUSTOM' and self.custom_name:
            return self.custom_name
        return self.get_name_display()


class Exam(models.Model):
    exam_type          = models.ForeignKey(ExamType, on_delete=models.PROTECT, related_name='exams')
    title              = models.CharField(max_length=300)
    custom_name        = models.CharField(max_length=300, blank=True, null=True)
    duration_minutes   = models.PositiveIntegerField(default=60, validators=[MinValueValidator(1)])
    marks_per_question = models.DecimalField(max_digits=5, decimal_places=2, default=1, validators=[MinValueValidator(0)])
    negative_marks     = models.DecimalField(max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    total_questions    = models.PositiveIntegerField(null=True, blank=True)
    pyq_years          = models.CharField(max_length=200, blank=True, null=True)
    subjects           = models.ManyToManyField(Subject, blank=True, related_name='exams')
    submodules = models.ManyToManyField(
    'SubModule',
    blank=True,
    related_name='exams',
)
    selected_questions = models.ManyToManyField(Question, blank=True, related_name='exams')
    is_active          = models.BooleanField(default=True)
    created_at         = models.DateTimeField(auto_now_add=True)
    updated_at         = models.DateTimeField(auto_now=True)
    description = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.exam_type}] {self.title}"

    @property
    def type_code(self):
        return self.exam_type.name

    @property
    def computed_total_marks(self):
        if self.total_questions and self.marks_per_question:
            return float(self.marks_per_question) * self.total_questions
        return None

    @property
    def pyq_year_list(self):
        if not self.pyq_years:
            return []
        return sorted(int(y.strip()) for y in self.pyq_years.split(',') if y.strip())

from django.core.validators import MinValueValidator


class SubscriptionPlan(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)
    name = models.CharField(max_length=200, unique=True)
    description = models.TextField(blank=True, null=True)
    price = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(0)],
    )
    duration_days = models.PositiveIntegerField(
        default=30,
        validators=[MinValueValidator(1)],
        help_text="Validity period in days (e.g. 30, 90, 365).",
    )
    subjects = models.ManyToManyField(
        Subject,
        blank=True,
        related_name="subscription_plans",
    )
    submodules = models.ManyToManyField(
        SubModule,
        blank=True,
        related_name="subscription_plans",
    )
    exams = models.ManyToManyField(
        Exam,
        blank=True,
        related_name="subscription_plans",
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["price"]

    def __str__(self):
        return f"{self.name} (₹{self.price})"

    @property
    def content_summary(self):
        return {
            "subjects": self.subjects.filter(is_active=True).count(),
            "submodules": self.submodules.filter(is_active=True).count(),
            "exams": self.exams.filter(is_active=True).count(),
        }
import uuid
from django.db import models
from django.core.validators import MinValueValidator


class Payment(models.Model):

    STATUS_PENDING  = "pending"
    STATUS_SUCCESS  = "success"
    STATUS_FAILED   = "failed"

    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_SUCCESS, "Success"),
        (STATUS_FAILED,  "Failed"),
    ]

    student = models.ForeignKey(
        "student_portal.Student",        
        on_delete=models.CASCADE,
        related_name="payments",
    )
    plan = models.ForeignKey(
        "SubscriptionPlan",
        on_delete=models.PROTECT,
        related_name="payments",
    )

    amount           = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)])
    status           = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)
    transaction_id   = models.CharField(max_length=200, blank=True, db_index=True)
    reference_number = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)

    paid_at    = models.DateTimeField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    razorpay_order_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_payment_id = models.CharField(max_length=100, blank=True, null=True)
    razorpay_signature = models.CharField(max_length=255, blank=True, null=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.student} | {self.plan} | ₹{self.amount} | {self.status}"