from django.shortcuts import render,redirect,get_object_or_404
from django.contrib.auth.models import User
from django.contrib import messages
from django.core.validators import validate_email
from django.core.exceptions import ValidationError
from django.contrib.auth import authenticate,login,logout
from django.contrib.auth.decorators import login_required
from .models import *
import openpyxl #--> pyxl   
import pandas as pd #-->  pandas
import re
from django.db.models import Count
from django.db import connection
from django.db import transaction
from django.utils.http import url_has_allowed_host_and_scheme
from django.db.models.functions import Lower
from django.utils import timezone
#-----------------------------------------------
#celery import
import os
import uuid
from django.conf import settings
from .tasks import send_invalid_records_email
# Downlaod Excel File view.
#--- Import 
from django.conf import settings
from django.http import FileResponse, Http404
from pathlib import Path
#-----------------------------------------------
# Forgot Email Import
# from django.contrib.auth.tokens import PasswordResetTokenGenerator
# from django.utils.http import urlsafe_base64_encode
# from django.utils.http import urlsafe_base64_decode
# from django.utils.encoding import force_bytes
# from django.urls import reverse
# from .tasks import send_password_reset_email
# from django.utils.encoding import force_str
# from django.contrib.auth.hashers import make_password
#------------------------------------------------


# Home view.
def home(request):
    return render(request,'home.html')


# Login page View
def login_page(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        login_input = request.POST.get("login", "").strip()
        password = request.POST.get("password")

        username = login_input

        # User entered email
        if "@" in login_input:

            try:
                user = User.objects.get(email__iexact=login_input)
                username = user.username
            except User.DoesNotExist:
                username = login_input

        user = authenticate(
            request,
            username=username,
            password=password
        )

        if user:

            login(request, user)
            
            LoginHistory.objects.create(
                user=user,
                username=user.username
            )

            next_url = request.POST.get("next") or request.GET.get("next")

            if next_url and url_has_allowed_host_and_scheme(
                next_url,
                allowed_hosts={request.get_host()},
                require_https=request.is_secure(),
            ):
                return redirect(next_url)

            return redirect("dashboard")
        
        LoginHistory.objects.create(username=login_input,status="FAILED",failure_reason="Invalid username or password")
        messages.error(request, "Invalid Email or Password.")
    
    return render(request, "login.html")

# Register Page VIew
def register(request):

    if request.user.is_authenticated:
        return redirect("dashboard")

    if request.method == "POST":

        first_name = request.POST.get("first_name", "").strip()
        last_name = request.POST.get("last_name", "").strip()
        email = request.POST.get("email", "").strip().lower()

        password = request.POST.get("password")
        confirm_password = request.POST.get("confirm_password")

        # ------------------------
        # First Name Validation
        # ------------------------
        if not first_name:
            messages.error(request, "First name is required.")
            return redirect("register")
        
        if len(first_name)<=2:
            messages.error(request,"First name Should be greater than 2 characters")
            return redirect('register')

        if not re.fullmatch(r"[A-Za-z ]+", first_name):
            messages.error(request, "First name should contain only letters.")
            return redirect("register")

        # ------------------------
        # Last Name Validation
        # ------------------------
        if not last_name:
            messages.error(request, "Last name is required.")
            return redirect("register")

        if not re.fullmatch(r"[A-Za-z ]+", last_name):
            messages.error(request, "Last name should contain only letters.")
            return redirect("register")
        
        username = email.split("@")[0]


        # If username already exists,
        # append number automatically
        if User.objects.filter(username=username).exists():
            messages.error(request,"Username Already Exist")
            return redirect('register')
        
        # ------------------------
        # Email Validation
        # ------------------------
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Enter a valid email address.")
            return redirect("register")

        allowed_domains = (
            "@gmail.com",
            "@yahoo.com",
            "@email.com",
        )

        if not email.endswith(allowed_domains):
            messages.error(
                request,
                "Only Gmail, Yahoo and Email.com addresses are allowed."
            )
            return redirect("register")

        if User.objects.filter(email__iexact=email).exists():
            messages.error(request, "Email already registered.")
            return redirect("register")

        # ------------------------
        # Password Validation
        # ------------------------
        if not password:
            messages.error(request, "Password is required.")
            return redirect("register")

    # Password should not exceed 12 characters
        if len(password) > 12:
            messages.error(request, "Password must not exceed 12 characters.")
            return redirect("register")


        if password != confirm_password:
            messages.error(request, "Passwords do not match.")
            return redirect("register")

        # ------------------------
        # Username from Email
        # ------------------------
        username = email.split("@")[0]

        # If username already exists,
        # append number automatically
        if User.objects.filter(username=username).exists():
            messages.error(request,"Username Already Exist")
            return redirect('register')
        # ------------------------
        # Create User
        # ------------------------
        User.objects.create_user(
            username=username,
            first_name=first_name,
            last_name=last_name,
            email=email,
            password=password,
        )

        messages.success(request, "Registration successful. Please login.")
        messages.success(
        request,
        f"Registration successful! Your username is: {username}"
        )
        return redirect("login")

    return render(request, "register.html")

# Validators
def validate_student_name(name):

    name = str(name).strip()

    return bool(re.fullmatch(r"[A-Za-z ]+", name))


def validate_student_email(email):

    try:
        validate_email(str(email).strip())
        return True

    except ValidationError:
        return False

def validate_student_id(studentid):

    return bool(
        re.fullmatch(r"STU\d{3}", studentid)
    )

def validate_course(course):

    return bool(
        re.fullmatch(r"[A-Za-z ]+", course)
    )
    
def validate_department(department):

    return bool(
        re.fullmatch(r"[A-Za-z ]+", department)
    )

# Dashboard Page View
@login_required(login_url='login')
def dashboard(request):
    uploads = (
    UploadFile.objects.filter(uploaded_by=request.user)
    .annotate(total_records=Count("students"))
    .filter(total_records__gt=0)
    .order_by("-uploaded_at")
    )
    invalid_rows = request.session.pop("invalid_rows", [])
    expected_columns = [
        "studentid*",
        "studentname*",
        "email*",
        "course*",
        "department*",
    ]

    if request.method == "POST":
        excel_file = request.FILES.get("excel_file")

        if not excel_file:
            messages.error(request, "Please choose an Excel file.")
            return render(request, "dashboard.html", {"uploads": uploads,
                                                      "invalid_rows" : invalid_rows})

        if not excel_file.name.lower().endswith((".xlsx", ".xls",".csv")):
            messages.error(request, "Only Excel files are allowed.")
            return render(request, "dashboard.html", {"uploads": uploads,"invalid_rows" : invalid_rows})

        try:
            df = pd.read_excel(excel_file, sheet_name=0)
        except Exception:
            messages.error(request, "Unable to read the Excel file.")
            return render(request, "dashboard.html", {"uploads": uploads,
                                                      "invalid_rows" : invalid_rows})

        if df.empty:
            messages.error(request, "The uploaded Excel file is empty.")
            return render(request, "dashboard.html", {"uploads": uploads,
                                                      "invalid_rows" : invalid_rows})

        df.columns = df.columns.str.strip().str.lower().str.replace(" ", "").str.replace("*","")
        
        
        # validating the exact column order also should be same in the excel sheet   
        # if list(df.columns) != expected_columns:
        #     messages.error(
        #         request,
        #         f"Invalid template. Expected columns in this order: {', '.join(expected_columns)}"
        #     )
        #     return render(request, "dashboard.html", {"uploads": uploads,
        #                                               "invalid_rows" : invalid_rows})

        seen_student_ids = set()
        invalid_rows = []
        valid_students = []

        uploaded_student_ids = df["studentid"].dropna().astype(str).str.strip().tolist()
        existing_ids = set(
        Student.objects.filter(
        upload__uploaded_by=request.user
        ).annotate(
        studentid_lower=Lower("studentid")
        ).values_list("studentid_lower", flat=True)
        )
        for index, row in df.iterrows():
            row_number = index + 2

            student_id = "" if pd.isna(row["studentid"]) else str(row["studentid"]).strip().lower()
            student_name = "" if pd.isna(row["studentname"]) else str(row["studentname"]).strip()
            email = "" if pd.isna(row["email"]) else str(row["email"]).strip()
            course = "" if pd.isna(row["course"]) else str(row["course"]).strip()
            department = "" if pd.isna(row["department"]) else str(row["department"]).strip()

            base_row = {
                "row": row_number,
                "studentid": student_id,
                "studentname": student_name,
                "email": email,
                "course": course,
                "department": department,
            }

            if not student_id:
                invalid_rows.append({**base_row, "error": "Student ID is mandatory"})
                continue
            if not student_name:
                invalid_rows.append({**base_row, "error": "Student Name is mandatory"})
                continue
            if not email:
                invalid_rows.append({**base_row, "error": "Email is mandatory"})
                continue
            if not course:
                invalid_rows.append({**base_row, "error": "Course is mandatory"})
                continue
            if not department:
                invalid_rows.append({**base_row, "error": "Department is mandatory"})
                continue

            if not validate_student_email(email):
                invalid_rows.append({**base_row, "error": "Invalid Email. Example: joe234@gmail.com"})
                continue

            if Student.objects.filter(email__iexact=email).exists():
                invalid_rows.append({**base_row, "error": "Email already exists in database."})
                continue
            
            if Student.objects.filter(studentid__iexact=student_id).exists():
                invalid_rows.append({**base_row, "error": "studentid already exists in database."})
                continue
            
            
            
            # check course Datatype Should be String.
            if not validate_course(department):
                
                invalid_rows.append({**base_row, "error": "Course name Should contains string."})
                continue
                
            # checking department Should be String.
            if not validate_department(department):
                invalid_rows.append({**base_row, "error": "Department Name should Contains String"})
                continue
            
            
            
            if student_id in seen_student_ids:
                invalid_rows.append({**base_row, "error": "Duplicate Student ID in Excel file"})
                continue
            seen_student_ids.add(student_id)

            if Student.objects.filter(
                upload__uploaded_by=request.user,
                studentid__iexact=student_id).exists():
                invalid_rows.append({**base_row,"error": "Student ID already exists in the database"})
                continue

            valid_students.append(
                
                Student(
                    studentid=student_id,
                    studentname=student_name,
                    email=email,
                    course=course,
                    department=department,
                )
            )

        upload = None
        
        if valid_students:
            with transaction.atomic():
                upload = UploadFile.objects.create(
                    uploaded_by=request.user,
                    filename=excel_file.name,
                )
                for student in valid_students:
                    student.upload = upload
                Student.objects.bulk_create(valid_students, batch_size=500)
                
        # Send invalid records through email
        if invalid_rows:

            related_id = upload.id if upload else 0

            send_invalid_records_email(
                request.user.email,
                invalid_rows,
                related_id,
            )                                      

        if invalid_rows and valid_students:
            messages.warning(
                request,
                f"{len(valid_students)} rows uploaded successfully. {len(invalid_rows)} rows failed."
            )
        elif invalid_rows and not valid_students:
            messages.error(
                request,
                f"Upload failed. {len(invalid_rows)} rows are invalid."
            )
        else:
            messages.success(
                request,
                f"{len(valid_students)} rows uploaded successfully."
            )

        uploads = (
            UploadFile.objects.filter(uploaded_by=request.user)
            .annotate(total_records=Count("students"))
            .order_by("-uploaded_at")
        )
        if invalid_rows:
            request.session["invalid_rows"] = invalid_rows
        return redirect("dashboard")

    return render(request, "dashboard.html", {"uploads": uploads,
                                              "invalid_rows" : invalid_rows})


# Logout View
@login_required(login_url="login")
def logout_view(request):

    history = LoginHistory.objects.filter(
        user=request.user,
        logout_time__isnull=True
    ).first()

    if history:
        history.logout_time = timezone.now()
        history.save(update_fields=["logout_time"])

    logout(request)
    messages.success(request, "Logged out Successfully.")
    return redirect("home")

# update view.
from django.shortcuts import get_object_or_404

@login_required(login_url='login')
def update_student(request, id):
    
    student = get_object_or_404(Student, id=id)

    if request.method == "POST":
        
        studentname = request.POST.get("studentname", "").strip()
        email = request.POST.get("email", "").strip()
        course = request.POST.get("course", "").strip()
        department = request.POST.get("department", "").strip()

        # -----------------------
        # Name Validation
        # -----------------------
        if not studentname:
            messages.error(request, "Student Name is required.")
            return redirect("student_records", upload_id=student.upload.id)
        
        if not validate_student_name(studentname):
            messages.error(request,"Student Name contains only alphabet characters")
            return redirect("student_records",upload_id=student.upload.id)

        # -----------------------
        # Email Validation
        # -----------------------
        try:
            validate_email(email)
        except ValidationError:
            messages.error(request, "Invalid Email Address.")
            return redirect("student_records", upload_id=student.upload.id)
        
        if Student.objects.filter(email__iexact=email).exclude(id=student.id).exists():
            messages.error(request, "Email already exists.")
            return redirect("student_records", upload_id=student.upload.id)

        # -----------------------
        # Course Validation
        # -----------------------
        if not course:
            messages.error(request, "Course is required.")
            return redirect("student_records", upload_id=student.upload.id)

        if not validate_course(course):
            messages.error(request,"Course Should be contains only alphabets")
            return redirect("student_records",upload_id=student.upload.id)
        
        # -----------------------
        # Department Validation
        # -----------------------
        if not department:
            messages.error(request, "Department is required.")
            return redirect("student_records", upload_id=student.upload.id)

        if not validate_department(department):
            messages.error(request,"Department Should be contains only alphabets")
            return redirect("student_records",upload_id=student.upload.id)
        
        # -----------------------
        
        
        student.studentname = studentname
        student.email = email
        student.course = course
        student.department = department

        student.save()

        messages.success(request, "Student updated successfully.")

        return redirect("student_records", upload_id=student.upload.id)

# delete view.
@login_required(login_url='login')
def delete_student(request, id):

    student = get_object_or_404(Student, id=id)

    upload = student.upload   # Save upload before deleting student

    student.delete()

    # If no students remain for this upload, delete the upload record
    if not upload.students.exists():
        upload.delete()

    messages.success(request, "Student deleted successfully.")

    return redirect("dashboard")

# student records view.
@login_required(login_url='login')
def student_records(request, upload_id):

    upload = get_object_or_404(
        UploadFile,
        id=upload_id,
        uploaded_by=request.user
    )

    students = Student.objects.filter(
        upload=upload
    )

    return render(
        request,
        "student_records.html",
        {
            "upload": upload,
            "students": students
        }
    )
    
    
# Forgot_email Password View.
# def forgot_password(request):

#     if request.method == "POST":

#         email = request.POST.get("email").strip()

#         if not User.objects.filter(email=email).exists():

#             messages.error(request, "Email does not exist.")

#             return redirect("forgot_password")

#         user = User.objects.get(email=email)

#         # Generate reset link here
#         token = PasswordResetTokenGenerator().make_token(user)
#         uid = urlsafe_base64_encode(force_bytes(user.pk))
#         reset_link = request.build_absolute_uri(
#             reverse(
#             "reset_password",
#             kwargs={
#                 "uidb64": uid,
#                 "token": token,
#                 },
#             )
#         )
#         send_password_reset_email.delay(

#             user.email,

#             reset_link,

#         )
        
#         messages.success(request,"Password reset link has been sent to your email.")
#         return redirect("login")
    
#     return render(request, "forgot_password.html")

# # Reset Password View
# def reset_password(request, uidb64, token):

#     try:

#         uid = force_str(urlsafe_base64_decode(uidb64))

#         user = User.objects.get(pk=uid)

#     except (TypeError, ValueError, OverflowError, User.DoesNotExist):

#         user = None

#     if user is None:

#         messages.error(request, "Invalid password reset link.")

#         return redirect("login")

#     if not PasswordResetTokenGenerator().check_token(user, token):

#         messages.error(request, "Password reset link has expired or is invalid.")

#         return redirect("login")

#     if request.method == "POST":

#         password1 = request.POST.get("password1", "").strip()

#         password2 = request.POST.get("password2", "").strip()

#         if not password1:

#             messages.error(request, "New Password is required.")

#             return render(request, "reset_password.html")

#         if not password2:

#             messages.error(request, "Confirm Password is required.")

#             return render(request, "reset_password.html")

#         if password1 != password2:

#             messages.error(request, "Passwords do not match.")

#             return render(request, "reset_password.html")

#         user.password = make_password(password1)

#         user.save()

#         messages.success(
#             request,
#             "Password changed successfully. Please login."
#         )

#         return redirect("login")


#     return render(request, "reset_password.html")
#--------------------------------------------------------------------------------------------------

# 404
# and 500 error views
def custom_404(request, exception):
    return render(request, "404.html", status=404)

def custom_500(request):
    return render(request, "500.html", status=500)

# downlaod_template view
@login_required(login_url='login')
def download_template(request):
    file_path = Path(settings.BASE_DIR) / "resources" / "Student_Template.xlsx"

    if not file_path.exists():
        raise Http404("Template file not found.")
    

    return FileResponse(
        open(file_path, "rb"),
        as_attachment=True,
        filename="Student_Template.xlsx",
    )
    
    
# CELERY_BROKER_URL=rediss://default:gQAAAAAAAn2wAAIgcDFlMzliNDc4ODk5NDI0NWQ3YjlhNTY0YzdiOTUwMWE2Nw@sought-iguana-163248.upstash.io:6379/0

# CELERY_RESULT_BACKEND=rediss://default:gQAAAAAAAn2wAAIgcDFlMzliNDc4ODk5NDI0NWQ3YjlhNTY0YzdiOTUwMWE2Nw@sought-iguana-163248.upstash.io:6379/1

