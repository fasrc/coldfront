"""Exceptions raised when integrations (e.g. LDAP) reject a project-user change.

Plugins that hook into project signals (see coldfront.core.project.signals) should
raise these -- or subclasses of these -- rather than plugin-specific exception types,
so core code can handle the failure without importing from any plugin.
"""


class ProjectUserAdditionError(Exception):
    """Raised when a user cannot be added to a project by a signal receiver."""


class ProjectUserDeactivatedError(ProjectUserAdditionError):
    """Raised when a user cannot be added to a project because their account is deactivated."""
