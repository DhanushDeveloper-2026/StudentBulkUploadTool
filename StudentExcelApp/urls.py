from django.urls import path
from .views import *
from django.contrib.auth import views as auth_views

urlpatterns = [
    path("",home,name="home"),
    path("login/",login_page,name="login"),
    path("register/",register,name="register"),
    path("dashboard/",dashboard,name="dashboard"),
    path("logout",logout_view,name="logout"),
    path("update/<int:id>/", update_student, name="update_student"),
    path("delete/<int:id>/", delete_student, name="delete_student"),
    path("student-records/<int:upload_id>/",student_records,name="student_records"),
    path("download-template/", download_template, name="download_template"),
    
    path(
        "password-reset/",
        auth_views.PasswordResetView.as_view(
            template_name="password_reset.html"
        ),
        name="password_reset",
    ),

    path(
        "password-reset/done/",
        auth_views.PasswordResetDoneView.as_view(
            template_name="password_reset_done.html"
        ),
        name="password_reset_done",
    ),

    path(
        "reset/<uidb64>/<token>/",
        auth_views.PasswordResetConfirmView.as_view(
            template_name="password_reset_confirm.html"
        ),
        name="password_reset_confirm",
    ),

    path(
        "reset/done/",
        auth_views.PasswordResetCompleteView.as_view(
            template_name="password_reset_complete.html"
        ),
        name="password_reset_complete",
    ),
      

    # path("forgot-password/",forgot_password,name="forgot_password",),
    # path("reset-password/<uidb64>/<token>/",reset_password,name="reset_password",),
    
    path(
        "send-bulk-email/",
        send_bulk_email_view,
        name="send_bulk_email",
    ),
]