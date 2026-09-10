'''Allowlist of Django management commands runnable through the API.

Only commands listed here can be triggered via ManagementCommandViewSet. Add
entries deliberately, one command at a time, and only for commands that
return promptly (no daemons / infinite loops).

Each entry maps the public command name to:
- 'command': the actual management command name to invoke.
- 'args': the accepted keyword arguments and their type, for validating and
  coercing caller-supplied values. Only list args here that are safe to let
  API callers control; leave as {} for commands that should only ever run
  with their own defaults.
'''

ALLOWED_MANAGEMENT_COMMANDS = {
    'calculateColdfrontBillingRecords': {
        'command': 'calculateColdfrontBillingRecords',
        'args': {
            'year': int,
            'month': int,
            'recalculate': bool,
        },
    },
    'createProductUsages': {
        'command': 'createProductUsages',
        'args': {
            'year': int,
            'month': int,
            'overwrite': bool,
        },
    },
    'getResourceAllocAuthData': {
        'command': 'getResourceAllocAuthData',
        'args': {},
    },
    'pruneOrganizations': {
        'command': 'pruneOrganizations',
        'args': {},
    },
    'updateAffiliations': {
        'command': 'updateAffiliations',
        'args': {
            'verbose': bool,
        },
    },
    'updateProjectOrganizations': {
        'command': 'updateProjectOrganizations',
        'args': {},
    },
}
