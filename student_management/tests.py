from django.test import TestCase, Client
from django.contrib.auth.models import User
from django.urls import reverse
from student_management.models import Subject, Question
from student_management.views import normalize_question

class DuplicateDetectionTest(TestCase):
    def setUp(self):
        self.subject = Subject.objects.create(name="Biology")
        self.user = User.objects.create_superuser(username='admin', password='password')
        self.client = Client()
        self.client.force_login(self.user)

    def test_normalization(self):
        self.assertEqual(normalize_question("What is 2 + 2?"), "what is 2+2?")
        self.assertEqual(normalize_question("What is 2+2?"), "what is 2+2?")

    def test_duplicate_rules(self):
        existing_questions_cache = {}
        
        def check_duplicate(question_text, source, year):
            if self.subject.id not in existing_questions_cache:
                existing_qs = Question.objects.filter(subject=self.subject).values('question_text', 'source', 'year')
                existing_questions_cache[self.subject.id] = [
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
            for eq in existing_questions_cache[self.subject.id]:
                if eq['text'] == normalized_current:
                    existing_source = eq['source']
                    if comparison_source == 'PYQ' and existing_source == 'PYQ':
                        if year == eq['year']:
                            is_duplicate = True
                            break
                    elif comparison_source == existing_source and comparison_source != 'PYQ':
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                Question.objects.create(
                    subject=self.subject,
                    question_text=question_text,
                    option_a="A", option_b="B", option_c="C", option_d="D",
                    correct_answer="A",
                    source=source,
                    year=year
                )
                existing_questions_cache[self.subject.id].append({
                    'text': normalized_current,
                    'source': source or 'OTHER',
                    'year': year
                })
                return False
            return True

        # Test PYQ same year
        self.assertFalse(check_duplicate("What is the powerhouse?", "PYQ", 2021))
        self.assertTrue(check_duplicate("What is the powerhouse?", "PYQ", 2021))
        
        # Test PYQ different years
        self.assertFalse(check_duplicate("What is the powerhouse?", "PYQ", 2022))
        self.assertFalse(check_duplicate("What is the powerhouse?", "PYQ", 2023))

        # Test EDUSETIN duplicates
        self.assertFalse(check_duplicate("What is the powerhouse?", "EDUSETIN", None))
        self.assertTrue(check_duplicate("What is the powerhouse?", "EDUSETIN", None))
        self.assertTrue(check_duplicate("What is the powerhouse?", "EDUSETIN", 2022))

        # Test OTHER duplicates
        self.assertFalse(check_duplicate("What is the powerhouse?", "OTHER", None))
        self.assertTrue(check_duplicate("What is the powerhouse?", "OTHER", None))
        
        # Test None vs OTHER
        self.assertTrue(check_duplicate("What is the powerhouse?", None, None))
        self.assertTrue(check_duplicate("What is the powerhouse?", "", None))

        self.assertEqual(Question.objects.filter(subject=self.subject).count(), 5)

    def test_manual_create_and_edit_validation(self):
        # Create initial question with source None
        response = self.client.post(reverse('student_management:question_create'), {
            'subject': self.subject.id,
            'question_text': "What is DNA?",
            'option_a': "A",
            'option_b': "B",
            'option_c': "C",
            'option_d': "D",
            'correct_answer': "A",
            'source': '',  # None
            'year': '',
        })
        self.assertEqual(Question.objects.filter(subject=self.subject, question_text="What is DNA?").count(), 1)
        q = Question.objects.get(subject=self.subject, question_text="What is DNA?")
        self.assertIsNone(q.source)

        # Attempt to create duplicate with source OTHER -> Should fail and display error message
        response = self.client.post(reverse('student_management:question_create'), {
            'subject': self.subject.id,
            'question_text': "What is DNA?",
            'option_a': "A",
            'option_b': "B",
            'option_c': "C",
            'option_d': "D",
            'correct_answer': "A",
            'source': 'OTHER',
            'year': '',
        })
        # Check that it did not create another question
        self.assertEqual(Question.objects.filter(subject=self.subject, question_text="What is DNA?").count(), 1)

        # Create another question
        response = self.client.post(reverse('student_management:question_create'), {
            'subject': self.subject.id,
            'question_text': "What is RNA?",
            'option_a': "A",
            'option_b': "B",
            'option_c': "C",
            'option_d': "D",
            'correct_answer': "A",
            'source': 'OTHER',
            'year': '',
        })
        q2 = Question.objects.get(subject=self.subject, question_text="What is RNA?")
        
        # Attempt to edit "What is RNA?" to be named "What is DNA?" -> Should fail
        response = self.client.post(reverse('student_management:question_edit', args=[q2.id]), {
            'subject': self.subject.id,
            'question_text': "What is DNA?",
            'option_a': "A",
            'option_b': "B",
            'option_c': "C",
            'option_d': "D",
            'correct_answer': "A",
            'source': 'OTHER',
            'year': '',
        })
        # Check it didn't change name to "What is DNA?" (it remains "What is RNA?")
        q2.refresh_from_db()
        self.assertEqual(q2.question_text, "What is RNA?")
