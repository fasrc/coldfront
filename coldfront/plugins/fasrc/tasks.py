from coldfront.plugins.fasrc.utils import pull_push_quota_data
import logging

import io
import traceback
from contextlib import redirect_stdout, redirect_stderr
from django.core.management import call_command
from django.core.mail import send_mail

from coldfront.core.utils.common import import_from_settings

logger = logging.getLogger('coldfront.run_ifx_updates')

def import_quotas(volumes=None):
    """
    Collect group-level quota and usage data from ATT and NESE and insert it
    into the Coldfront database.

    Parameters
    ----------
    volumes : string of volume names separated by commas. Optional, default None
    """
    if volumes:
        volumes = volumes.split(",")
    pull_push_quota_data()

def id_import_allocations():
    """ID and import new allocations using ATT and Starfish data"""
    call_command('id_import_new_allocations')


def pull_resource_data():
    call_command('pull_resource_data')

def run_ifx_updates(emails=None):
    out = io.StringIO()
    err = io.StringIO()

    success = True
    exception_info = []

    with redirect_stdout(out), redirect_stderr(err):
        print("=== Starting coldfront updates ===")
        try:
            print("=== Starting updateOrganizations ===")
            call_command(
                "updateOrganizations", "-t", "Harvard,Research Computing Storage Billing"
            )
            print("=== updateOrganizations completed successfully ===")
        except Exception as e:
            success = False
            exception_info.append(("=== updateOrganizations EXCEPTION OCCURRED ==="))
            exception_info.append(traceback.format_exc())
        except SystemExit as e:
            success = False
            exception_info.append(f"updateOrganizations exited with code {e.code}")
        try:
            print("=== Starting updateApplicationUsers ===")
            call_command("updateApplicationUsers")
            print("=== updateApplicationUsers completed successfully ===")
        except Exception as e:
            success = False
            exception_info.append(("=== updateApplicationUsers EXCEPTION OCCURRED ==="))
            exception_info.append(traceback.format_exc())
        except SystemExit as e:
            success = False
            exception_info.append(f"updateApplicationUsers exited with code {e.code}")
        try:
            print("=== Starting updateUserAccounts ===")
            call_command("updateUserAccounts")
            print("=== updateUserAccounts completed successfully ===")
        except Exception as e:
            success = False
            exception_info.append(("=== updateOrganizations EXCEPTION OCCURRED ==="))
            exception_info.append(traceback.format_exc())
        except SystemExit as e:
            success = False
            exception_info.append(f"updateUserAccounts exited with code {e.code}")
        print("=== All commands completed (with errors)" if not success
              else "=== All commands completed successfully ===")

    stdout_content = out.getvalue()
    stderr_content = err.getvalue()

    subject_status = "SUCCESS" if success else "FAILURE"
    subject = f"coldfront ifx update [{subject_status}]"

    body_parts = [
        "This is the output from the scheduled coldfront update.\n",
        "=== STDOUT ===",
        stdout_content or "(no stdout output)",
        "\n=== STDERR ===",
        stderr_content or "(no stderr output)",
    ]
    if exception_info:
        body_parts.append("\n=== EXIT/EXCEPTION INFO ===")
        body_parts.extend(exception_info)

    body = "\n".join(body_parts)
    if emails:
        send_mail(
            subject=subject,
            message=body,
            from_email=import_from_settings('EMAIL_SENDER'),
            recipient_list=emails,
            fail_silently=False,
        )
    else:
        logger.info("No email recipients provided, logging output instead.")
        logger.info(subject)
        logger.info(body)
