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

def calcet(t, h):
  # expecting value
  # h: 0.00 - 1.00
  # t: -10 - 40
  a = 1.76
  tm = 37 - ((37 - t) / ((0.68 - 0.14 * h) + (1 / a))) - 0.29 * t * (1 - h)
  return tm

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
    self.temp = 0
    self.press = 0
    self.humid = 0
    self.etemp = 0

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
    self.irisoff()
    self.acoff()
    self.mode = 0

  def odekake(self):
    self.logger.debug('odekake(=night) mode')
    self.radio.stop()
    self.irisoff()
    self.acoff()
    self.mode = 0
    self.nightmode = 1

  def night(self):
    self.logger.debug('night mode')
    self.radio.stop()
    self.irisoff()
    self.acoff()
    self.mode = 0
    self.nightmode = 1

  def morning(self):
    self.logger.debug('morning mode')
    self.irison()
    self.acon()
    self.radio.nextchannel()
    self.nightmode = 0
    self.mode = 1

  def irison(self):
    if self.lux < 10:
      self.device.sendir('iris:toggle')

  def irisoff(self):
    if self.lux > 20:
      self.device.sendir('iris:off')

  def acon(self):
    if self.etemp < 23:
      name = 'ac:heating'
    elif self.etemp > 27:
      name = 'ac:cooling'
    else:
      self.logger.debug(f'no need ac (etemp={self.etemp})')
      return
    self.logger.debug(f'turn on ac, name={name} (etemp={self.etemp})')
    self.device.sendir(name)

  def acoff(self):
    self.device.sendir('ac:off')

  def close(self):
    self.device.close()
    self.radio.close()

  def run(self):
    self.schedulerthread.start()
    
    self.radio.auth()
    self.radio.changechannel(self.radio.channels[0])
    stoptimer = None

    counter = 0
    aconauto = 0
    try:
      while True:
        counter += 1

        # 子プロセスの死活監視, 空調自動調節等(5secごと)
        if counter % 100 == 0:
          counter = 0
          if aconauto > 0:
            aconauto -= 0

          self.lux = self.device.lux()
          (self.temp, self.press, self.humid) = self.device.tph()
          self.etemp = calcet(self.temp, self.humid)
          if self.mode != 0:
            # 動作中
            if self.radio.current != 0:
              if (self.radio.mplayer != None and self.radio.mplayer.poll() != None) or \
                (self.radio.rtmpdump != None and self.radio.rtmpdump.poll() != None):
                self.logger.warning('radio process dead. restarting...')
                self.radio.stop()
                self.radio.nextchannel()
            if self.lux < 10:
              self.logger.debug(f'the room is gloomy, turn off radio, ac (lux={self.lux})')
              self.mode = 0
              self.radio.stop()
              self.device.sendir('ac:off')
            elif self.etemp < 20 and self.aconauto == 0:
              self.logger.debug(f'the room is cold, turn on ac (etemp={self.etemp})')
              self.acon()
              # 1h待機
              aconauto = 1 * 60 * 60 / 5
            elif self.etemp > 28 and self.aconauto == 0:
              self.logger.debug(f'the room is hot, turn on ac (etemp={self.etemp})')
              self.acon()
              aconauto = 1 * 60 * 60 / 5
          else:
            # 休止中
            if self.lux > 20:
              self.logger.debug(f'the room is bright, turn on radio, ac(lux={self.lux})')
              self.mode = 1
              self.acon()
              self.radio.nextchannel()
    
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
