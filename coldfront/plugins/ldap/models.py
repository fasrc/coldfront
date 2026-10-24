from django.conf import settings
from django.db import models


class LDAPAccount(models.Model):
    """Local copy of a user's directory (e.g. AD) account information, synced from LDAP.

    The directory is the source of truth. This row is refreshed by the sync and
    written through when a value is changed from ColdFront, so pages can read
    directory account data without querying the directory.

    This is the home for per-user directory account attributes. It currently
    holds the account expiration; other attributes ColdFront reads from the
    directory (e.g. enabled status, uidNumber, primary gidNumber) can be added
    as fields here as needed.

    Fields are directory-neutral; translating a server's own representation
    (e.g. AD accountExpires, OpenLDAP shadowExpire, FreeIPA
    krbPrincipalExpiration) into these values belongs in the sync code.

    Attributes:
        user (User): the ColdFront user this directory account belongs to
        expiration (datetime): when the directory account expires; null if it never expires
        last_synced (datetime): when this row was last confirmed against the directory
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ldap_account',
    )
    expiration = models.DateTimeField(
        null=True,
        blank=True,
        help_text='When the directory account expires; null means it never expires.',
    )
    last_synced = models.DateTimeField(
        help_text='When this row was last read from or written to the directory.',
    )

    class Meta:
        verbose_name = 'LDAP account'
        verbose_name_plural = 'LDAP accounts'

    def __str__(self):
        return f'{self.user.username}: {self.expiration or "never expires"}'
