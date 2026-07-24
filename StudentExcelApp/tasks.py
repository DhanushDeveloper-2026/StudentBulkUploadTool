import os
from django.conf import settings
from django.core.mail import EmailMessage
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from .models import EmailLog
import uuid
import pandas as pd
from .models import UploadFile
import tempfile
import traceback


def send_invalid_records_email(user_email, invalid_rows, upload_id):

    subject = "Invalid Student Records"

    body = (
        "Dear User,\n\n"
        "Some rows in your uploaded Excel file were invalid.\n"
        "Please find the attached Excel file containing the failed records.\n\n"
        "Regards,\n"
        "InESS"
    )

    # Create a temporary folder
    temp_dir = os.path.join(tempfile.gettempdir(), "error_reports")
    os.makedirs(temp_dir, exist_ok=True)

    file_name = f"errors_{uuid.uuid4().hex}.xlsx"
    excel_path = os.path.join(temp_dir, file_name)

    error_df = pd.DataFrame(invalid_rows)
    error_df.to_excel(excel_path, index=False)

    # Decide recipient
    if settings.SERVER_TYPE == "DEMO":
        recipients = [user_email]
    else:
        recipients = ["dhanusharumugam245@gmail.com"]

    try:

        email = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipients,
        )

        email.attach_file(excel_path)

        email.send(fail_silently=False)

        EmailLog.objects.create(
            to_email=recipients[0],
            subject=subject,
            email_status="sent",
            related_object_id=upload_id,
        )

    except Exception:

        EmailLog.objects.create(
            to_email=recipients[0],
            subject=subject,
            email_status="failed",
            related_object_id=upload_id,
        )

        raise

    finally:

        if os.path.exists(excel_path):
            os.remove(excel_path)
            
        
# Forgot Email Task.
# @shared_task
# def send_password_reset_email(

#     email,

#     reset_link,

# ):

#     subject = "Reset Your Password"

#     html = render_to_string(

#         "password_reset_email.html",

#         {

#             "reset_link": reset_link,

#         },

#     )

#     message = EmailMultiAlternatives(

#         subject,

#         "Click the link below to reset your password.",

#         settings.DEFAULT_FROM_EMAIL,

#         [email],

#     )

#     message.attach_alternative(

#         html,

#         "text/html",

#     )

#     message.send()

def send_bulk_upload_email(recipients, upload_id):
    print("IM entering mail send")
    subject = "Engineering Solutions That Drive Innovation"

    for person in recipients:
        print(person['name'],person['email'])
        html_content = render_to_string(
            "email_template.html",
            {
                "name": person["name"],
                "user_email": person["email"],
            }
        )

        text_content = f"""
Dear {person['name']},

Engineering Solutions That Drive Innovation.
"""

        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_content,
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[person["email"]],
            )

            email.attach_alternative(html_content, "text/html")
            print(f"Sending mail to {person['email']}")
            email.send(fail_silently=False)
            print(f"Sent successfully to {person['email']}")

            EmailLog.objects.create(
                to_email=person["email"],
                subject=subject,
                email_status="sent",
                related_object_id=upload_id,
            )

        except Exception as e:
            
            
            print("=" * 80)
            print("EMAIL ERROR")
            traceback.print_exc()
            print("=" * 80)
             
            EmailLog.objects.create(
                to_email=person["email"],
                subject=subject,
                email_status="failed",
                related_object_id=upload_id,
            )