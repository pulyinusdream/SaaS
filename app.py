
from kjancy import create_app

app = create_app({
    "DATA_DIR": "/tmp/kjancy-data",
    "TRUSTED_HOSTS": ["kjancy.vercel.app"],
    "SESSION_COOKIE_SECURE": True,
})
