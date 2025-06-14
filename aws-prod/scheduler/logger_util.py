# import logging
# import os
# from logging.handlers import TimedRotatingFileHandler

# # Ensure the logs directory exists
# log_dir = "logs"
# os.makedirs(log_dir, exist_ok=True)

# # Define log file path (logs will be stored in logs/YYYY-MM-DD.log)
# log_file = os.path.join(log_dir, "app.log")

# # Configure TimedRotatingFileHandler (creates new log file daily)
# file_handler = TimedRotatingFileHandler(log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8")
# file_handler.suffix = "%Y-%m-%d"  # Append date to the log file
# file_handler.setFormatter(logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(funcName)s() - %(message)s"))

# # Configure logging
# logging.basicConfig(
#     level=logging.INFO,
#     format="%(asctime)s - %(name)s - %(levelname)s - %(funcName)s() - %(message)s",
#     handlers=[
#         file_handler,  # Logs to file (rotated daily)
#         logging.StreamHandler()  # Logs to console
#     ]
# )

# # Create logger
# logger = logging.getLogger(__name__)


import logging
import os
from logging.handlers import TimedRotatingFileHandler
import sys

log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, "app.log")

# Create formatter
formatter = logging.Formatter(
    "%(asctime)s - %(name)s - %(levelname)s - %(funcName)s() - %(message)s"
)

# File handler
file_handler = TimedRotatingFileHandler(
    log_file, when="midnight", interval=1, backupCount=7, encoding="utf-8"
)
file_handler.suffix = "%Y-%m-%d"
file_handler.setFormatter(formatter)

# Stream handler
stream_handler = logging.StreamHandler(sys.stdout)
stream_handler.setFormatter(formatter)

# Create logger explicitly
logger = logging.getLogger("scheduler")
logger.setLevel(logging.INFO)
logger.handlers.clear()  # 🔥 Prevent duplicate logs
logger.addHandler(file_handler)
logger.addHandler(stream_handler)
logger.propagate = False
