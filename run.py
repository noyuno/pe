# requirements: swfextract (swftools), rtmpdump, mplayer, irsend(lirc)

import os
import sys
import time
from datetime import datetime
import RPi.GPIO as GPIO
import requests
import base64
import xml.etree.ElementTree as et
import subprocess
import urllib.parse
import threading
import logging
import schedule
import asyncio
import linecache

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
    fileHandler = logging.FileHandler('{}/{}'.format(logdir, starttime))
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)
    return logger, starttime

class Led():
  def __init__(self, logger):
    # GPIOの準備
    GPIO.setmode(GPIO.BCM)

    # SW1, SW2ピン入力設定
    GPIO.setup(5, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(6, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # LED1, 2, 3, 4ピン出力設定
    GPIO.setup(17, GPIO.OUT)
    GPIO.setup(18, GPIO.OUT)
    GPIO.setup(22, GPIO.OUT)
    GPIO.setup(27, GPIO.OUT)
    
    # human sensor
    GPIO.setup(23, GPIO.IN)

  def on(self, mode, radio):
    GPIO.output(17, int(mode))
    GPIO.output(18, int(int(radio / 4) % 2))
    GPIO.output(22, int(int(radio / 2) % 2))
    GPIO.output(27, int(int(radio / 1) % 2))

  def human(self):
    return int(1==GPIO.input(23))

  def sw1(self):
    return int(0==GPIO.input(5))

  def sw2(self):
    return int(0==GPIO.input(6))

  def close(self):
      GPIO.cleanup(5)
      GPIO.cleanup(6)
      GPIO.cleanup(17)
      GPIO.cleanup(18)
      GPIO.cleanup(22)
      GPIO.cleanup(27)
      GPIO.cleanup(23)

class Radio():
  def __init__(self, logger):
    self.logger = logger
    self.channels = []
    self.current = 0
    self.player = None
    self.rtmpdump = None
    self.mplayer = None

  def auth(self):
    # auth
    self.player = requests.get('http://radiko.jp/apps/js/flash/myplayer-release.swf')
    if self.player.status_code != 200:
      raise ConnectionError("failed get player")
    auth1 = requests.post('https://radiko.jp/v2/api/auth1_fms', headers={
        'pragma': 'no-cache',
        'X-Radiko-App': 'pc_ts',
        'X-Radiko-App-Version': '4.0.0',
        'X-Radiko-User': 'test-stream',
        'X-Radiko-Device': 'pc',
      },
      data='\r\n',
      verify=False)
    if auth1.status_code != 200:
      raise ConnectionError('failed auth1 process')
    self.authtoken = auth1.headers['x-radiko-authtoken']
    offset = auth1.headers['x-radiko-keyoffset']
    length = auth1.headers['x-radiko-keylength']
    swf = subprocess.check_output(['swfextract', '-b', '12', '/dev/stdin', '-o', '/dev/stdout'], input=self.player.content)
    dd = subprocess.check_output(['dd', 'bs=1', 'skip=' + offset, 'count=' + length], input=swf)
    partialkey = base64.b64encode(dd)
    auth2 = requests.post('https://radiko.jp/v2/api/auth2_fms',
      headers={
        'pragma': 'no-cache',
        'X-Radiko-App': 'pc_ts',
        'X-Radiko-App-Version': '4.0.0',
        'X-Radiko-User': 'test-stream',
        'X-Radiko-Device': 'pc',
        'X-Radiko-Authtoken': self.authtoken,
        'X-Radiko-Partialkey': partialkey,
      },
      data='\r\n',
      verify=False)
    if auth2.status_code != 200:
      raise ConnectionError('failed auth2 process')
    areaid = auth2.content.decode('utf-8').replace('\r\n', '').split(',')[0]
    self.logger.debug('areaid={}, self.authtoken={}'.format(areaid, self.authtoken))
    # get channel list
    chan = requests.get('http://radiko.jp/v2/api/program/today?area_id={}'.format(areaid))
    for i in et.fromstring(chan.content).findall('./stations/station[@id]'):
      self.channels.append(i.attrib['id'])
    self.logger.debug('self.channels={}'.format(self.channels))

  def changechannel(self, channel):
    r = requests.get('http://radiko.jp/v2/station/stream/{}.xml'.format(channel))
    streamurl = et.fromstring(r.content).find('./item').text
    u = urllib.parse.urlparse(streamurl)

    if self.mplayer != None and self.mplayer.poll() == None:
      self.mplayer.kill()
    if self.rtmpdump != None and self.rtmpdump.poll() == None:
      self.rtmpdump.kill()
    
    rtmpdumpcommand = [
      'rtmpdump',
      '-v',
      '-r', '{}://{}'.format(u.scheme, u.netloc),
      '--app', '/'.join(u.path.strip('/').split('/')[:-1]),
      '--playpath', u.path.split('/')[-1],
      '-W', self.player.url,
      '-C', 'S:', '-C', 'S:', '-C', 'S:', '-C', 'S:' + self.authtoken,
      '--live']
    if not os.environ.get('DEBUG'):
      rtmpdumpcommand.append('-q')
    self.logger.debug(' '.join(rtmpdumpcommand))
    self.rtmpdump = subprocess.Popen(rtmpdumpcommand, stdout=subprocess.PIPE, shell=False)
    mplayercommand = ['mplayer', '-channels', '2', '-af', 'pan=1:1', '-']
    if not os.environ.get('DEBUG'):
      mplayercommand.append('-quiet')
    self.mplayer = subprocess.Popen(mplayercommand, stdin=self.rtmpdump.stdout, shell=False)
    
  def nextchannel(self):
    if self.mplayer != None and self.mplayer.poll() == None and \
       self.rtmpdump != None and self.rtmpdump.poll() == None:
      if self.current + 1 >= len(self.channels):
        self.current = 0
      else:
        self.current += 1
    self.changechannel(self.channels[self.current])

  def close(self):
    self.stop()

  def stop(self):
    if self.mplayer != None and self.mplayer.poll() == None:
      self.mplayer.kill()
    if self.rtmpdump != None and self.rtmpdump.poll() == None:
      self.rtmpdump.kill()

class Scheduler():
  def __init__(self, logger, loop, main):
    self.logger = logger
    self.loop = loop
    self.main = main

  def run(self):
    asyncio.set_event_loop(self.loop)
    self.logger.debug('launch scheduler')
    schedule.every().day.at('06:30').do(self.morning)
    schedule.every().day.at('00:00').do(self.night)
    while True:
      schedule.run_pending()
      time.sleep(1)

  def night(self):
    self.main.night()

  def morning(self):
    self.main.morning()

class Main():
  def __init__(self, logger):
    self.logger = logger
    self.radio = Radio(self.logger)
    self.led = Led(logger)
    self.scheduler = Scheduler(self.logger, asyncio.new_event_loop(), self)
    threading.Thread(target=self.scheduler.run, name='scheduler').start()
    self.mode = 1
    self.night = 0

  def start(self):
    self.logger.debug('There seem to be people, starting radio')
    self.radio.nextchannel()
    subprocess.run(['irsend' 'SEND_ONCE' 'iris-toggle' 'button'])
    subprocess.run(['irsend' 'SEND_ONCE' 'ac-heating' 'button'])
    self.mode = 1

  def stop(self):
    self.logger.debug('There seem to be no people, stopping radio')
    self.radio.stop()
    subprocess.run(['irsend' 'SEND_ONCE' 'iris-off' 'button'])
    subprocess.run(['irsend' 'SEND_ONCE' 'ac-off' 'button'])
    self.mode = 0

  def night(self):
    self.logger.debug('night mode')
    self.radio.stop()
    subprocess.run(['irsend' 'SEND_ONCE' 'iris-off' 'button'])
    subprocess.run(['irsend' 'SEND_ONCE' 'ac-off' 'button'])
    self.mode = 0
    self.night = 1
  
  def morning(self):
    self.logger.debug('morning mode')
    subprocess.run(['irsend' 'SEND_ONCE' 'iris-toggle' 'button'])
    subprocess.run(['irsend' 'SEND_ONCE' 'ac-heating' 'button'])
    self.night = 0

  def close(self):
    self.led.close()
    self.radio.close()

  def run(self):
    self.radio.auth()
    self.radio.nextchannel()
    stoptimer = None

    counter = 0
    try:
      while True:
        counter += 1

        # 子プロセスの死活監視(1secごと)
        if counter % 20 == 0:
          counter = 0
          if (self.radio.mplayer != None and self.radio.mplayer.poll() != None) or \
            (self.radio.rtmpdump != None and self.radio.rtmpdump.poll() != None):
            self.logger.debug('radio process dead. restarting...')
            self.radio.stop()
            self.radio.nextchannel()
    
        # SW2 blackが押された場合
        if self.led.sw2():
          self.radio.nextchannel()

        # timer -> stop
        if 0==self.led.human():
          # 部屋の中に人がいない
          if self.mode == 1 and (stoptimer == None or stoptimer.is_alive() == False):
            self.logger.debug('starting stoptimer')
            stoptimer = threading.Timer(60, self.stop)
            stoptimer.start()
        elif self.night == 0:
          # 部屋の中に人がいる
          if stoptimer != None and stoptimer.is_alive() == True:
            self.logger.debug('canceling stoptimer')
            stoptimer.cancel()
          if self.mode == 0:
            self.start()

        # human sensor -> led
        hmode = int(not(self.led.human()))
        # SW1 red
        if hmode == 0:
          hmode = self.led.sw1()

        # send ir
        if self.led.sw1():
          pass

        self.led.on(hmode, self.radio.current)
        time.sleep(0.05)

    # Ctrl+Cが押されたらGPIOを解放
    except KeyboardInterrupt:
      self.close()
    except Exception as e:
      exc_type, exc_obj, tb = sys.exc_info()
      lineno = tb.tb_lineno
      self.logger.error("Unexpected error: line {}: {}: {}".format(lineno, str(type(e)), e))
      self.close()

if __name__ == "__main__":
  logger, starttime = initlogger()
  logger.info('started room at {0}'.format(starttime))
  main = Main(logger)
  main.run()
