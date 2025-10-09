import logging
from logging.handlers import RotatingFileHandler
import os

def setup_logger():
    """
    Configures the root logger for the entire application.
    It logs to a rotating file and to the console.
    """
    # Define the path for the log file in the user's AppData directory
    log_dir = os.path.join(os.getenv('APPDATA'), 'NydusNet', 'logs')
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, 'nydusnet.log')

    # Get the root logger
    logger = logging.getLogger()
    logger.setLevel(logging.INFO) # Set the minimum level of messages to record

    # Create a formatter to define the log message structure
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # Create a rotating file handler to write logs to a file.
    # This will create up to 5 backup log files, each 1MB in size.
    file_handler = RotatingFileHandler(
        log_file, maxBytes=1024*1024, backupCount=5
    )
    file_handler.setFormatter(formatter)

    # Create a stream handler to print logs to the console (for debugging)
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    # Add the handlers to the root logger
    # Avoid adding handlers if they already exist (prevents duplicate logs)
    if not logger.handlers:
        logger.addHandler(file_handler)
        logger.addHandler(stream_handler)

    logging.info("Logger initialized.")
