from datetime import datetime
import logging

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from coldfront.core.department.models import Department
from coldfront.core.department.views import DepartmentStorageReportView
from coldfront.core.project.models import Project
from coldfront.core.project.views import ProjectStorageReportView
from coldfront.core.utils.common import import_from_settings
from coldfront.core.utils.mail import send_email_template, email_template_context, build_link

TESTUSER = import_from_settings('TESTUSER')
EMAIL_TICKET_SYSTEM_ADDRESS = import_from_settings('EMAIL_TICKET_SYSTEM_ADDRESS')

DEPARTMENT_REPORT_PROJECT_THRESHOLD = 10

logger = logging.getLogger(__name__)

def send_storage_report_emails():
    """Send monthly email with project storage reports"""
    projects = Project.objects.filter(
        status__name='Active',
        allocation__resources__resource_type__name="Storage",
        allocation__status__name="Active"
    ).distinct()
    for project in projects:
        send_storagereport_pdf(project)

def send_storagereport_pdf(project, context=None):
    """
    Renders the ReportPdfView to PDF and emails it to `to_email`.
    `context` will be passed to the view when rendering.
    """
    system_user = get_user_model().objects.get(username=TESTUSER)
    month = datetime.now().strftime("%B")
    year = datetime.now().year
    title = project.title
    subject = f'Monthly ColdFront Storage Allocation Report for {title} [{month} {year}]'
    context = email_template_context(extra_context={
        'EMAIL_TICKET_SYSTEM_ADDRESS': EMAIL_TICKET_SYSTEM_ADDRESS,
        'project_title': title,
        'project_detail_url': build_link(f'/project/{project.pk}/')
    })
    # 1) build a fake GET request, set any necessary attributes
    factory = RequestFactory()
    request = factory.get(f'project/{project.pk}/report')
    request.user = system_user

    # 2) instantiate and call class‐based view
    view = ProjectStorageReportView.as_view()
    response = view(request, pk=project.pk)

    # 3) make sure the response is rendered and grab the bytes
    if hasattr(response, 'rendered_content'):
        pdf_bytes = response.rendered_content
    else:
        pdf_bytes = response.content

    receivers = project.projectuser_set.filter(role__name='General Manager', status__name='Active')
    receiver_list = [receiver.user.email for receiver in receivers] + [project.pi.email]
    attachment = (f'{title}_{month}_{year}_storagereport.pdf', pdf_bytes, 'application/pdf')
    try:
        send_email_template(
            subject,
            'email/storage_report.txt',
            context,
            EMAIL_TICKET_SYSTEM_ADDRESS,
            receiver_list,
            attachments=(attachment,)
        )
    except Exception as e:
        logger.exception(
            'could not send storage report email for project %s to receivers %s from sender %s: %s',
            title, receiver_list, EMAIL_TICKET_SYSTEM_ADDRESS, e
        )

def send_dept_storage_report_emails():
    """Send monthly email with department storage reports to departments
    with more than DEPARTMENT_REPORT_PROJECT_THRESHOLD active projects.
    """
    for department in Department.objects.all():
        active_project_count = department.get_projects().filter(status__name='Active').count()
        if active_project_count > DEPARTMENT_REPORT_PROJECT_THRESHOLD:
            send_dept_storagereport_pdf(department)

def send_dept_storagereport_pdf(department, context=None):
    """
    Renders the DepartmentStorageReportView to PDF and emails it to the
    department's approvers. `context` will be passed to the view when rendering.
    """
    system_user = get_user_model().objects.get(username=TESTUSER)
    month = datetime.now().strftime("%B")
    year = datetime.now().year
    name = department.name
    subject = f'Monthly ColdFront Department Storage Report for {name} [{month} {year}]'
    context = email_template_context(extra_context={
        'EMAIL_TICKET_SYSTEM_ADDRESS': EMAIL_TICKET_SYSTEM_ADDRESS,
        'department_name': name,
    })
    # 1) build a fake GET request, set any necessary attributes
    factory = RequestFactory()
    request = factory.get(f'department/{department.pk}/report')
    request.user = system_user

    # 2) instantiate and call class‐based view
    view = DepartmentStorageReportView.as_view()
    response = view(request, pk=department.pk)

    # 3) make sure the response is rendered and grab the bytes
    if hasattr(response, 'rendered_content'):
        pdf_bytes = response.rendered_content
    else:
        pdf_bytes = response.content

    approvers = department.members.filter(role="Approver")
    receiver_list = [approver.user.email for approver in approvers]
    attachment = (f'{name}_{month}_{year}_dept_storagereport.pdf', pdf_bytes, 'application/pdf')
    try:
        send_email_template(
            subject,
            'email/dept_storage_report.txt',
            context,
            EMAIL_TICKET_SYSTEM_ADDRESS,
            receiver_list,
            attachments=(attachment,)
        )
    except Exception as e:
        logger.exception(
            'could not send department storage report email for department %s to receivers %s from sender %s: %s',
            name, receiver_list, EMAIL_TICKET_SYSTEM_ADDRESS, e
        )
