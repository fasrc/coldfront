import environ

ENV = environ.Env()
PROJECT_ROOT = environ.Path(__file__) - 3

# Default paths to environment files
env_paths = [

    PROJECT_ROOT.path('.env'),
    environ.Path('/etc/coldfront/coldfront.env'),

    # added 03262021
    # Environment="PATH=/srv/coldront/venv/bin"
    # EnvironmentFile=/srv/coldfront/coldfront.env
    # STATIC_ROOT = ENV.str(‘STATIC_ROOT’, default=PROJECT_ROOT(‘static_root’))
]

if ENV.str('COLDFRONT_ENV', default='') != '':
    env_paths.insert(0, environ.Path(ENV.str('COLDFRONT_ENV')))

# Read in any environment files
for e in env_paths:
    try:
        e.file('')
        ENV.read_env(e())
    except FileNotFoundError:
        pass
