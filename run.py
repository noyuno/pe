# requirements: swfextract (swftools), rtmpdump, mplayer, irsend(lirc)

import asyncio
import base64
import linecache
import logging
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.parse
import xml.etree.ElementTree as et
from datetime import datetime

import requests

import device
import radio
import schedule


class Scheduler():
  def __init__(self, logger, loop, main):
    self.logger = logger
    self.loop = loop
    self.main = main

  def run(self):
    asyncio.set_event_loop(self.loop)
    sys.stdout = LoggerWriter(self.logger, logging.DEBUG)
    sys.stderr = LoggerWriter(self.logger, logging.WARNING)
    self.logger.debug('launch scheduler')
    morningtime = os.environ.get('MORNING', default='06:20')
    odekaketime = os.environ.get('ODEKAKE', default='07:40')
    nighttime = os.environ.get('NIGHT', default='00:30')
    schedule.every().day.at(morningtime).do(self.main.morning)
    schedule.every().day.at(odekaketime).do(self.main.odekake)
    schedule.every().day.at(nighttime).do(self.main.night)
    while True:
      schedule.run_pending()
      time.sleep(1)

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



class Main():
  def __init__(self, logger):
    self.logger = logger
    self.radio = radio.Radio(self.logger)
    self.device = device.Device(logger)
    self.scheduler = Scheduler(self.logger, asyncio.new_event_loop(), self)
    self.schedulerthread = threading.Thread(target=self.scheduler.run, name='scheduler', daemon=True)
    self.mode = 1
    self.nightmode = 0

  def subrun(self, command):
    self.logger.info('executing command: {}'.format(' '.join(command)))
    return subprocess.run(command, stdout=LoggerWriter(self.logger, logging.DEBUG), stderr=LoggerWriter(self.logger, logging.WARNING))

  def start(self):
    self.logger.debug('There seem to be people... nothing to do')
    # 人がいないはずなのにご認識するので、コメントアウト
    #self.radio.nextchannel()
    #subprocess.run(['irsend', 'SEND_ONCE', 'iris-toggle', 'button'])
    #subprocess.run(['irsend', 'SEND_ONCE', 'ac-heating', 'button'])
    #self.mode = 1

  def stop(self):
    self.logger.debug('There seem to be no people, stopping radio')
    self.radio.stop()
    self.device.sendir('iris:off')
    self.device.sendir('ac:off')
    self.mode = 0

  def odekake(self):
    self.logger.debug('odekake(=night) mode')
    self.radio.stop()
    self.device.sendir('iris:off')
    self.device.sendir('ac:off')
    self.mode = 0
    self.nightmode = 1

  def night(self):
    self.logger.debug('night mode')
    self.radio.stop()
    self.device.sendir('iris:off')
    self.device.sendir('ac:off')
    self.mode = 0
    self.nightmode = 1
  
  def morning(self, lux, t, h):
    self.logger.debug('morning mode')
    if lux < 40:
      self.device.sendir('iris:toggle')
    self.ac(t, h)
    self.radio.nextchannel()
    self.nightmode = 0
    self.mode = 1

  def calcet(self, t, h):
    # expecting value
    # h: 0.00 - 1.00
    # t: -10 - 40
    a = 1.76
    tm = 37 - ((37 - t) / ((0.68 - 0.14 * h) + (1 / a))) - 0.29 * t * (1 - h)
    return tm

  def ac(self, t, h):
    et = self.calcet(t, h)
    if et < 22:
      name = 'ac:heating'
    elif et > 28:
      name = 'ac:cooling'
    else:
      self.logger.debug(f'no need ac (et={et})')
      return
    self.logger.debug(f'turn on ac, name={name} (et={et})')
    self.device.sendir(name)

  def close(self):
    self.device.close()
    self.radio.close()

  def run(self):
    self.schedulerthread.start()
    
    self.radio.auth()
    self.radio.changechannel(self.radio.channels[0])
    stoptimer = None

    counter = 0
    try:
      while True:
        counter += 1

        # 子プロセスの死活監視, 暗くなったらOFF(5secごと)
        if counter % 100 == 0:
          counter = 0
          if self.mode != 0:
            if self.radio.current != 0:
              if (self.radio.mplayer != None and self.radio.mplayer.poll() != None) or \
                (self.radio.rtmpdump != None and self.radio.rtmpdump.poll() != None):
                self.logger.warning('radio process dead. restarting...')
                self.radio.stop()
                self.radio.nextchannel()
            if self.device.lux() < 40:
              self.radio.stop()
              self.device.sendir('iris:off')
              self.device.sendir('ac:off')
    
        # SW2 blackが押された場合
        sw2 = self.device.sw2()
        if sw2 == 1:
          # short
          self.logger.debug('pressed sw2(short), change next channel')
          self.radio.nextchannel()
        elif sw2 == 2:
          # long
          self.device.blink(0b0111, 0b0111, 0.5, 1)
          self.radio.current = 0
          self.radio.changechannel(self.radio.channels[0])
          
        hmode = (self.device.sw1() == 1)

        # 暗かったらOFF
        #if self.mode != 0

        self.device.all(hmode << 3 | self.radio.current)
        time.sleep(0.05)

    # Ctrl+Cが押されたらGPIOを解放
    except KeyboardInterrupt:
      self.close()
      sys.exit(1)
    except Exception as e:
      exc_type, exc_obj, tb = sys.exc_info()
      lineno = tb.tb_lineno
      self.logger.error(f"Unexpected error: line {lineno}: {str(type(e))}: {e}")
      self.close()
      sys.exit(1)

main = None

def termed(signum, frame):
    print("shutting down...")
    if main != None:
      main.close()
    sys.exit(0)

if __name__ == "__main__":
  logger, starttime = initlogger()
  logger.info(f'started room at {starttime}')
  signal.signal(signal.SIGTERM, termed)
  main = Main(logger)
  main.run()
