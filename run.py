# requirements: swfextract (swftools), rtmpdump, mplayer, irsend(lirc)

import asyncio
import base64
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
import traceback

import requests

import device
import radio
import schedule
import clog

class Scheduler():
  def __init__(self, logger, loop, main):
    self.logger = logger
    self.loop = loop
    self.main = main

  def run(self):
    asyncio.set_event_loop(self.loop)
    sys.stdout = clog.LoggerWriter(self.logger, logging.DEBUG)
    sys.stderr = clog.LoggerWriter(self.logger, logging.WARNING)
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
    return subprocess.run(command, stdout=clog.LoggerWriter(self.logger, logging.DEBUG), stderr=clog.LoggerWriter(self.logger, logging.WARNING))

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
  
  def morning(self):
    self.logger.debug('morning mode')
    if self.lux < 40:
      self.device.sendir('iris:toggle')
    self.ac(self.temp, self.humid)
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
            self.lux = self.device.lux()
            (self.temp, self.press, self.humid) = self.device.tph()
            if self.lux < 20:
              self.logger.debug(f'the room seems gloomy, turn off radio, ac (lux={self.lux})')
              self.mode = 0
              self.radio.stop()
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
      self.logger.error(f"Unexpected error: {e.__name__}: {e}")
      self.logger.error(traceback.format_exc())
      self.close()
      sys.exit(1)

main = None

def termed(signum, frame):
    print("shutting down...")
    if main != None:
      main.close()
    sys.exit(0)

if __name__ == "__main__":
  logger, starttime = clog.initlogger()
  logger.info(f'started room at {starttime}')
  signal.signal(signal.SIGTERM, termed)
  main = Main(logger)
  main.run()
