"""After-close NSE market terminal."""

import logging

logging.getLogger("mt").addHandler(logging.NullHandler())  # silent unless the CLI sets a log file
