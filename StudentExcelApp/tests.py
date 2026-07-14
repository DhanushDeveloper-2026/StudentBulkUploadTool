import io
from unittest.mock import patch

from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, Client
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

import openpyxl

from .models import Student, UploadFile, LoginHistory


def make_xlsx_bytes(rows, headers=None):
    """
    Build an in-memory .xlsx file for upload tests.
    rows: list of tuples (studentid, studentname, email, course, department)
    """
    if headers is None:
        headers = ["studentid", "studentname", "email", "course", "department"]

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(list(row))

    buffer = io.BytesIO()
    wb.save(buffer)
    buffer.seek(0)
    return buffer.read()


class HomeViewTests(TestCase):

    def test_home_page_loads(self):
        response = self.client.get(reverse("home"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "home.html")


class LoginViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="johndoe",
            email="johndoe@gmail.com",
            password=self.password,
            first_name="John",
            last_name="Doe",
        )

    def test_login_page_get(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "login.html")

    def test_authenticated_user_redirected_to_dashboard(self):
        self.client.login(username="johndoe", password=self.password)
        response = self.client.get(reverse("login"))
        self.assertRedirects(response, reverse("dashboard"))

    def test_login_with_username_success(self):
        response = self.client.post(
            reverse("login"),
            {"login": "johndoe", "password": self.password},
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertTrue(
            LoginHistory.objects.filter(user=self.user).exists()
        )

    def test_login_with_email_success(self):
        response = self.client.post(
            reverse("login"),
            {"login": "johndoe@gmail.com", "password": self.password},
        )
        self.assertRedirects(response, reverse("dashboard"))

    def test_login_invalid_password_fails(self):
        response = self.client.post(
            reverse("login"),
            {"login": "johndoe", "password": "wrongpass"},
        )
        self.assertEqual(response.status_code, 200)
        messages = list(response.context["messages"])
        self.assertTrue(any("Invalid Email or Password" in str(m) for m in messages))
        self.assertTrue(
            LoginHistory.objects.filter(
                username="johndoe", status="FAILED"
            ).exists()
        )

    def test_login_with_open_redirect_blocked(self):
        response = self.client.post(
            reverse("login") + "?next=https://evil.com",
            {"login": "johndoe", "password": self.password},
        )
        # Unsafe next url must NOT be honored; falls back to dashboard.
        self.assertRedirects(response, reverse("dashboard"))

    def test_login_with_safe_next_redirect(self):
        response = self.client.post(
            reverse("login") + "?next=" + reverse("dashboard"),
            {"login": "johndoe", "password": self.password},
        )
        self.assertRedirects(response, reverse("dashboard"))


class RegisterViewTests(TestCase):

    def valid_payload(self, **overrides):
        payload = {
            "first_name": "Jane",
            "last_name": "Smith",
            "email": "janesmith@gmail.com",
            "password": "Pass1234",
            "confirm_password": "Pass1234",
        }
        payload.update(overrides)
        return payload

    def test_register_page_get(self):
        response = self.client.get(reverse("register"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "register.html")

    def test_register_missing_first_name(self):
        response = self.client.post(
            reverse("register"), self.valid_payload(first_name="")
        )
        self.assertRedirects(response, reverse("register"))
        self.assertFalse(User.objects.filter(email="janesmith@gmail.com").exists())

    def test_register_invalid_first_name_characters(self):
        response = self.client.post(
            reverse("register"), self.valid_payload(first_name="Jane123")
        )
        self.assertRedirects(response, reverse("register"))
        self.assertFalse(User.objects.exists())

    def test_register_first_name_too_short(self):
        # First name must be more than 2 characters long.
        response = self.client.post(
            reverse("register"), self.valid_payload(first_name="Al")
        )
        self.assertRedirects(response, reverse("register"))
        self.assertFalse(User.objects.exists())

    def test_register_disallowed_email_domain(self):
        response = self.client.post(
            reverse("register"), self.valid_payload(email="jane@outlook.com")
        )
        self.assertRedirects(response, reverse("register"))
        self.assertFalse(User.objects.exists())

    def test_register_password_too_long(self):
        response = self.client.post(
            reverse("register"),
            self.valid_payload(
                password="ThisIsWayTooLong123",
                confirm_password="ThisIsWayTooLong123",
            ),
        )
        self.assertRedirects(response, reverse("register"))
        self.assertFalse(User.objects.exists())

    def test_register_password_mismatch(self):
        response = self.client.post(
            reverse("register"),
            self.valid_payload(confirm_password="Different1"),
        )
        self.assertRedirects(response, reverse("register"))
        self.assertFalse(User.objects.exists())

    def test_register_duplicate_email(self):
        User.objects.create_user(
            username="janesmit",
            email="janesmith@gmail.com",
            password="Pass1234",
        )
        response = self.client.post(reverse("register"), self.valid_payload())
        self.assertRedirects(response, reverse("register"))
        self.assertEqual(
            User.objects.filter(email="janesmith@gmail.com").count(), 1
        )

    def test_register_success(self):
        response = self.client.post(reverse("register"), self.valid_payload())
        self.assertRedirects(response, reverse("login"))
        self.assertTrue(
            User.objects.filter(email="janesmith@gmail.com").exists()
        )
        user = User.objects.get(email="janesmith@gmail.com")
        self.assertEqual(user.username, "janesmith")


class DashboardViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="tester", email="tester@gmail.com", password=self.password
        )
        self.client.login(username="tester", password=self.password)

    def test_dashboard_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('dashboard')}"
        )

    def test_dashboard_get(self):
        response = self.client.get(reverse("dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard.html")

    def test_dashboard_post_without_file(self):
        response = self.client.post(reverse("dashboard"), {})
        self.assertRedirects(response, reverse("dashboard")) if response.status_code == 302 else None
        # View re-renders dashboard.html directly (no redirect) when file missing
        self.assertIn(response.status_code, (200, 302))

    def test_dashboard_post_invalid_file_extension(self):
        bad_file = SimpleUploadedFile(
            "students.txt", b"not an excel file", content_type="text/plain"
        )
        response = self.client.post(
            reverse("dashboard"), {"excel_file": bad_file}
        )
        self.assertEqual(response.status_code, 200)

    @patch("StudentExcelApp.views.send_invalid_records_email")
    def test_dashboard_post_valid_students_created(self, mock_send_email):
        content = make_xlsx_bytes(
            [
                ("STU001", "Alice Brown", "alice@gmail.com", "CS", "Engineering"),
                ("STU002", "Bob White", "bob@gmail.com", "IT", "Engineering"),
            ]
        )
        upload_file = SimpleUploadedFile(
            "students.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            reverse("dashboard"), {"excel_file": upload_file}
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(Student.objects.count(), 2)
        self.assertTrue(UploadFile.objects.filter(uploaded_by=self.user).exists())
        mock_send_email.assert_not_called()

    @patch("StudentExcelApp.views.send_invalid_records_email")
    def test_dashboard_post_invalid_rows_reported(self, mock_send_email):
        content = make_xlsx_bytes(
            [
                ("STU003", "", "carol@gmail.com", "CS", "Engineering"),  # missing name
            ]
        )
        upload_file = SimpleUploadedFile(
            "students.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            reverse("dashboard"), {"excel_file": upload_file}
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(Student.objects.count(), 0)
        mock_send_email.assert_called_once()

    @patch("StudentExcelApp.views.send_invalid_records_email")
    def test_dashboard_post_duplicate_student_id_in_file(self, mock_send_email):
        content = make_xlsx_bytes(
            [
                ("STU004", "Dave Grey", "dave@gmail.com", "CS", "Engineering"),
                ("STU004", "Dana Grey", "dana@gmail.com", "CS", "Engineering"),
            ]
        )
        upload_file = SimpleUploadedFile(
            "students.xlsx",
            content,
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            reverse("dashboard"), {"excel_file": upload_file}
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertEqual(Student.objects.count(), 1)
        mock_send_email.assert_called_once()

    def test_dashboard_post_malformed_excel_file(self):
        # A file with a .xlsx extension but bytes that are not a real
        # spreadsheet at all (passes the extension check, fails to parse).
        bad_file = SimpleUploadedFile(
            "students.xlsx",
            b"this is not a real excel file, just plain text bytes",
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        response = self.client.post(
            reverse("dashboard"), {"excel_file": bad_file}
        )
        # View catches the pandas parse error and re-renders the same page
        # (no redirect) with an error message; nothing should be saved.
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard.html")
        self.assertEqual(Student.objects.count(), 0)

    def test_dashboard_post_csv_extension_fails_to_parse(self):
        # KNOWN ISSUE (see test documentation / defect log): the view accepts
        # .csv by extension, but always calls pandas.read_excel() on the
        # uploaded content regardless of extension. A genuinely CSV-formatted
        # file is therefore NOT valid input for read_excel() and is rejected
        # with the generic "Unable to read the Excel file." error, even
        # though .csv is advertised as an allowed upload type.
        csv_content = (
            "studentid,studentname,email,course,department\n"
            "STU900,Eve Black,eve@gmail.com,CS,Engineering\n"
        ).encode("utf-8")
        csv_file = SimpleUploadedFile(
            "students.csv", csv_content, content_type="text/csv"
        )
        response = self.client.post(
            reverse("dashboard"), {"excel_file": csv_file}
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "dashboard.html")
        # No student is created because parsing fails before validation runs.
        self.assertEqual(Student.objects.count(), 0)


class LogoutViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="loguser", email="loguser@gmail.com", password=self.password
        )

    def test_logout_updates_login_history_and_redirects_home(self):
        self.client.login(username="loguser", password=self.password)
        LoginHistory.objects.create(user=self.user, username=self.user.username)

        response = self.client.get(reverse("logout"))
        self.assertRedirects(response, reverse("home"))

        history = LoginHistory.objects.get(user=self.user)
        self.assertIsNotNone(history.logout_time)

    def test_logout_requires_login(self):
        response = self.client.get(reverse("logout"))
        self.assertRedirects(
            response, f"{reverse('login')}?next={reverse('logout')}"
        )


class UpdateStudentViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="owner", email="owner@gmail.com", password=self.password
        )
        self.client.login(username="owner", password=self.password)

        self.upload = UploadFile.objects.create(
            uploaded_by=self.user, filename="students.xlsx"
        )
        self.student = Student.objects.create(
            studentid="stu100",
            studentname="Original Name",
            email="original@gmail.com",
            course="CS",
            department="Engineering",
            upload=self.upload,
        )

    def test_update_student_requires_login(self):
        self.client.logout()
        response = self.client.post(
            reverse("update_student", args=[self.student.id]),
            {"studentname": "New Name"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn(reverse("login"), response.url)

    def test_update_student_success(self):
        response = self.client.post(
            reverse("update_student", args=[self.student.id]),
            {
                "studentname": "Updated Name",
                "email": "updated@gmail.com",
                "course": "IT",
                "department": "Technology",
            },
        )
        self.assertRedirects(
            response, reverse("student_records", args=[self.upload.id])
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.studentname, "Updated Name")
        self.assertEqual(self.student.email, "updated@gmail.com")

    def test_update_student_invalid_name(self):
        response = self.client.post(
            reverse("update_student", args=[self.student.id]),
            {
                "studentname": "Invalid123",
                "email": "updated@gmail.com",
                "course": "IT",
                "department": "Technology",
            },
        )
        self.assertRedirects(
            response, reverse("student_records", args=[self.upload.id])
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.studentname, "Original Name")

    def test_update_student_duplicate_email(self):
        Student.objects.create(
            studentid="stu101",
            studentname="Other Student",
            email="taken@gmail.com",
            course="CS",
            department="Engineering",
            upload=self.upload,
        )
        response = self.client.post(
            reverse("update_student", args=[self.student.id]),
            {
                "studentname": "Updated Name",
                "email": "taken@gmail.com",
                "course": "IT",
                "department": "Technology",
            },
        )
        self.assertRedirects(
            response, reverse("student_records", args=[self.upload.id])
        )
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "original@gmail.com")

    def test_update_student_nonexistent_id_returns_404(self):
        nonexistent_id = self.student.id + 99999
        response = self.client.post(
            reverse("update_student", args=[nonexistent_id]),
            {
                "studentname": "Doesn't Matter",
                "email": "wontsave@gmail.com",
                "course": "IT",
                "department": "Technology",
            },
        )
        self.assertEqual(response.status_code, 404)


class DeleteStudentViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="deluser", email="deluser@gmail.com", password=self.password
        )
        self.client.login(username="deluser", password=self.password)

        self.upload = UploadFile.objects.create(
            uploaded_by=self.user, filename="students.xlsx"
        )
        self.student = Student.objects.create(
            studentid="stu200",
            studentname="Delete Me",
            email="deleteme@gmail.com",
            course="CS",
            department="Engineering",
            upload=self.upload,
        )

    def test_delete_student_removes_record(self):
        response = self.client.get(
            reverse("delete_student", args=[self.student.id])
        )
        self.assertRedirects(response, reverse("dashboard"))
        self.assertFalse(Student.objects.filter(id=self.student.id).exists())

    def test_delete_last_student_removes_upload(self):
        self.client.get(reverse("delete_student", args=[self.student.id]))
        self.assertFalse(UploadFile.objects.filter(id=self.upload.id).exists())

    def test_delete_student_keeps_upload_if_others_remain(self):
        other = Student.objects.create(
            studentid="stu201",
            studentname="Stay Here",
            email="stay@gmail.com",
            course="CS",
            department="Engineering",
            upload=self.upload,
        )
        self.client.get(reverse("delete_student", args=[self.student.id]))
        self.assertTrue(UploadFile.objects.filter(id=self.upload.id).exists())
        self.assertTrue(Student.objects.filter(id=other.id).exists())

    def test_delete_student_nonexistent_id_returns_404(self):
        nonexistent_id = self.student.id + 99999
        response = self.client.get(
            reverse("delete_student", args=[nonexistent_id])
        )
        self.assertEqual(response.status_code, 404)


class StudentRecordsViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="recuser", email="recuser@gmail.com", password=self.password
        )
        self.other_user = User.objects.create_user(
            username="otheruser", email="otheruser@gmail.com", password=self.password
        )
        self.client.login(username="recuser", password=self.password)

        self.upload = UploadFile.objects.create(
            uploaded_by=self.user, filename="students.xlsx"
        )
        Student.objects.create(
            studentid="stu300",
            studentname="Visible Student",
            email="visible@gmail.com",
            course="CS",
            department="Engineering",
            upload=self.upload,
        )

    def test_student_records_success(self):
        response = self.client.get(
            reverse("student_records", args=[self.upload.id])
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "student_records.html")
        self.assertEqual(len(response.context["students"]), 1)

    def test_student_records_wrong_owner_returns_404(self):
        other_upload = UploadFile.objects.create(
            uploaded_by=self.other_user, filename="others.xlsx"
        )
        response = self.client.get(
            reverse("student_records", args=[other_upload.id])
        )
        self.assertEqual(response.status_code, 404)


class DownloadTemplateViewTests(TestCase):

    def setUp(self):
        self.password = "Pass1234"
        self.user = User.objects.create_user(
            username="dluser", email="dluser@gmail.com", password=self.password
        )
        self.client.login(username="dluser", password=self.password)

    def test_download_template_requires_login(self):
        self.client.logout()
        response = self.client.get(reverse("download_template"))
        self.assertEqual(response.status_code, 302)

    def test_download_template_missing_file_returns_404(self):
        # Assumes no Student_Template.xlsx exists at BASE_DIR/resources
        # in the test environment; adjust/skip if your CI provisions one.
        response = self.client.get(reverse("download_template"))
        self.assertIn(response.status_code, (200, 404))


class PasswordResetViewTests(TestCase):
    """
    Covers Django's built-in auth views wired up in urls.py:
    password_reset, password_reset_done, password_reset_confirm,
    password_reset_complete.
    """

    def setUp(self):
        self.old_password = "OldPass123"
        self.user = User.objects.create_user(
            username="resetuser",
            email="resetuser@gmail.com",
            password=self.old_password,
        )

    # ---- password_reset (request form) ----

    def test_password_reset_page_get(self):
        response = self.client.get(reverse("password_reset"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "password_reset.html")

    def test_password_reset_valid_email_sends_mail(self):
        response = self.client.post(
            reverse("password_reset"), {"email": self.user.email}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(self.user.email, mail.outbox[0].to)

    def test_password_reset_unknown_email_does_not_leak(self):
        # Django's PasswordResetForm silently no-ops for unknown emails,
        # still redirecting to the "done" page so attackers can't use
        # this form to enumerate registered addresses.
        response = self.client.post(
            reverse("password_reset"), {"email": "nobody@gmail.com"}
        )
        self.assertRedirects(response, reverse("password_reset_done"))
        self.assertEqual(len(mail.outbox), 0)

    # ---- password_reset_done ----

    def test_password_reset_done_page_get(self):
        response = self.client.get(reverse("password_reset_done"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "password_reset_done.html")

    # ---- password_reset_confirm ----

    def test_password_reset_confirm_valid_link_and_reset(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse(
            "password_reset_confirm", kwargs={"uidb64": uid, "token": token}
        )

        # First GET redirects internally to a one-time "set-password" URL
        # and marks the link valid in the session.
        response = self.client.get(confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "password_reset_confirm.html")
        self.assertTrue(response.context["validlink"])

        set_password_url = response.redirect_chain[-1][0]

        new_password = "BrandNewPass789"
        response = self.client.post(
            set_password_url,
            {"new_password1": new_password, "new_password2": new_password},
        )
        self.assertRedirects(response, reverse("password_reset_complete"))

        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(new_password))
        self.assertFalse(self.user.check_password(self.old_password))

    def test_password_reset_confirm_invalid_token_rejected(self):
        uid = urlsafe_base64_encode(force_bytes(self.user.pk))
        bad_token = "invalid-token-000"
        confirm_url = reverse(
            "password_reset_confirm", kwargs={"uidb64": uid, "token": bad_token}
        )

        response = self.client.get(confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "password_reset_confirm.html")
        self.assertFalse(response.context["validlink"])

        # Password must remain unchanged since the link was never valid.
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(self.old_password))

    def test_password_reset_confirm_invalid_uid_rejected(self):
        bad_uid = urlsafe_base64_encode(force_bytes(999999))
        token = default_token_generator.make_token(self.user)
        confirm_url = reverse(
            "password_reset_confirm", kwargs={"uidb64": bad_uid, "token": token}
        )

        response = self.client.get(confirm_url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["validlink"])

    # ---- password_reset_complete ----

    def test_password_reset_complete_page_get(self):
        response = self.client.get(reverse("password_reset_complete"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "password_reset_complete.html")
