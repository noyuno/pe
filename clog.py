import logging
import os
from datetime import datetime

class LoggerWriter():
  def __init__(self, logger, level):
    self.level = level
    self.logger = logger
  def write(self, buf):
    for line in buf.rstrip().splitlines():
      self.logger.log(self.level, line.rstrip())
  def flush(self):
    self.logger.log(self.level, sys.stderr)
  def fileno(self):
    # emulate fileno
    if self.level == logging.DEBUG:
      return 1
    elif self.level == logging.INFO:
      return 1
    elif self.level == logging.WARNING:
      return 2
    elif self.level == logging.ERROR:
      return 2
    elif self.level == logging.CRITICAL:
      return 2
    else:
      return 2

def initlogger():
    logdir = './logs'
    os.makedirs(logdir, exist_ok=True)
    starttime = datetime.now().strftime('%Y%m%d-%H%M')
    logging.getLogger().setLevel(logging.WARNING)
    logger = logging.getLogger('room')
    if os.environ.get('DEBUG'):
        logger.setLevel(logging.DEBUG)
    else:
        logger.setLevel(logging.INFO)
    logFormatter = logging.Formatter(fmt='%(asctime)s %(levelname)s: %(message)s',
                                     datefmt='%Y%m%d-%H%M')
    fileHandler = logging.FileHandler(f'{logdir}/{starttime}')
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)
    sys.stdout = LoggerWriter(logger, logging.DEBUG)
    sys.stderr = LoggerWriter(logger, logging.WARNING)
    return logger, starttime
