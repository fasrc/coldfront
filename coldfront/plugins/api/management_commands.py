'''Allowlist of Django management commands runnable through the API.

Only commands listed here can be triggered via ManagementCommandViewSet.
Add entries deliberately, one command at a time, and only for commands that
can run with no arguments and return promptly (no daemons / infinite loops).
'''

ALLOWED_MANAGEMENT_COMMANDS = {
    'calculateColdfrontBillingRecords': 'calculateColdfrontBillingRecords',
    'createProductUsages': 'createProductUsages',
    'getResourceAllocAuthData': 'getResourceAllocAuthData',
    'pruneOrganizations': 'pruneOrganizations',
    'updateAffiliations': 'updateAffiliations',
    'updateProjectOrganizations': 'updateProjectOrganizations',
    # processIfxappsMessages intentionally excluded: it's a daemon
    # (while True loop) and would never return an HTTP response.
}
