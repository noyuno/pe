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
import retry
import RPi.GPIO as GPIO
import schedule


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
    fileHandler = logging.FileHandler('{}/{}'.format(logdir, starttime))
    fileHandler.setFormatter(logFormatter)
    logger.addHandler(fileHandler)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    logger.addHandler(consoleHandler)
    sys.stdout = LoggerWriter(logger, logging.DEBUG)
    sys.stderr = LoggerWriter(logger, logging.WARNING)
    return logger, starttime

class Led():
  def __init__(self, logger):
    # GPIOの準備
    GPIO.setmode(GPIO.BCM)

    # SW1, SW2ピン入力設定
    GPIO.setup(5, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.setup(6, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # LED1, 2, 3, 4ピン出力設定
    self.ledpin = [27, 22, 18, 17]
    for i in range(4):
      GPIO.setup(self.ledpin[i], GPIO.OUT)
    
    # human sensor
    # GPIO.setup(23, GPIO.IN)

    self.sw1press = 0
    self.sw2press = 0

  def all(self, mode):
    for b in range(3):
      GPIO.output(self.ledpin[b], not(not(mode & 1 << b)))
    
  def blink(self, mode, mask, span, count):
    for i in range(count * 2):
      for b in range(3):
        if mask & 1 << b:
          if mode & 1 << b:
            GPIO.output(self.ledpin[b], (i + 1) % 2)
          else:
            GPIO.output(self.ledpin[b], 0)
      time.sleep(span)

  # def human(self):
  #   return int(1==GPIO.input(23))

  def sw1(self):
    if self.sw1press != 0 and int(0==GPIO.input(5)) == 0:
      self.sw1press = 0
      if time.time() - self.sw1press < 1:
        return 1
      else:
        return 2
    else:
      self.sw1press = time.time()
      return 0

  def sw2(self):
    if self.sw2press != 0 and int(0==GPIO.input(6)) == 0:
      self.sw2press = 0
      if time.time() - self.sw2press < 1:
        return 1
      else:
        return 2
    else:
      self.sw2press = time.time()
      return 0

  def close(self):
      GPIO.cleanup(5)
      GPIO.cleanup(6)
      GPIO.cleanup(17)
      GPIO.cleanup(18)
      GPIO.cleanup(22)
      GPIO.cleanup(27)
      # GPIO.cleanup(23)

class Radio():
  def __init__(self, logger):
    self.logger = logger
    self.channels = []
    self.current = 0
    self.player = None
    self.rtmpdump = None
    self.mplayer = None

  @retry.retry(tries=50, delay=10)
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
    swf = subprocess.check_output(['swfextract', '-b', '12', '/dev/stdin', '-o', '/dev/stdout'], input=self.player.content, stderr=LoggerWriter(self.logger, logging.WARNING))
    dd = subprocess.check_output(['dd', 'bs=1', 'skip=' + offset, 'count=' + length], input=swf, stderr=LoggerWriter(self.logger, logging.WARNING))
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
    self.channels = ['']
    self.current = 0
    chan = requests.get('http://radiko.jp/v2/api/program/today?area_id={}'.format(areaid))
    for i in et.fromstring(chan.content).findall('./stations/station[@id]'):
      self.channels.append(i.attrib['id'])
    self.logger.debug('self.channels={}'.format(self.channels))

  @retry.retry(tries=50, delay=10)
  def changechannel(self, channel):
    if channel == '':
      if self.mplayer != None and self.mplayer.poll() == None:
        self.mplayer.kill()
      if self.rtmpdump != None and self.rtmpdump.poll() == None:
        self.rtmpdump.kill()
      return

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
    self.rtmpdump = subprocess.Popen(rtmpdumpcommand, stdout=subprocess.PIPE, stderr=LoggerWriter(self.logger, logging.WARNING), shell=False)
    mplayercommand = ['mplayer', '-channels', '2', '-af', 'pan=1:1', '-']
    if not os.environ.get('DEBUG'):
      mplayercommand.append('-quiet')
    self.mplayer = subprocess.Popen(mplayercommand, stdin=self.rtmpdump.stdout,
      stdout=LoggerWriter(self.logger, logging.DEBUG), stderr=LoggercWriter(self.logger, logging.WARNING), shell=False)
    
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
    sys.stdout = LoggerWriter(self.logger, logging.DEBUG)
    sys.stderr = LoggerWriter(self.logger, logging.WARNING)
    self.logger.debug('launch scheduler')
    morningtime = os.environ.get('MORNING')
    if morningtime is None:
      morningtime = '06:20'
    nighttime = os.environ.get('NIGHT')
    if nighttime is None:
      nighttime = '00:30'
    schedule.every().day.at(morningtime).do(self.main.morning)
    schedule.every().day.at(nighttime).do(self.main.night)
    while True:
      schedule.run_pending()
      time.sleep(1)

class Main():
  def __init__(self, logger):
    self.logger = logger
    self.radio = Radio(self.logger)
    self.led = Led(logger)
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
    self.subrun(['irsend', 'SEND_ONCE', 'iris-off', 'button'])
    self.subrun(['irsend', 'SEND_ONCE', 'ac-off', 'button'])
    self.mode = 0

  def night(self):
    self.logger.debug('night mode')
    self.radio.stop()
    self.subrun(['irsend', 'SEND_ONCE', 'iris-off', 'button'])
    self.subrun(['irsend', 'SEND_ONCE', 'ac-off', 'button'])
    self.mode = 0
    self.nightmode = 1
  
  def morning(self):
    self.logger.debug('morning mode')
    self.subrun(['irsend', 'SEND_ONCE', 'iris-toggle', 'button'])
    self.subrun(['irsend', 'SEND_ONCE', 'ac-heating', 'button'])
    self.radio.nextchannel()
    self.nightmode = 0

  def close(self):
    self.led.close()
    self.radio.close()

  def run(self):
    self.schedulerthread.start()
    
    self.radio.auth()
    self.radio.nextchannel()
    stoptimer = None

    counter = 0
    try:
      while True:
        counter += 1

        # 子プロセスの死活監視(5secごと)
        if counter % 100 == 0:
          counter = 0
          if self.mode != 0:
            if (self.radio.mplayer != None and self.radio.mplayer.poll() != None) or \
              (self.radio.rtmpdump != None and self.radio.rtmpdump.poll() != None):
              self.logger.warning('radio process dead. restarting...')
              self.radio.stop()
              self.radio.nextchannel()
    
        # SW2 blackが押された場合
        sw2 = self.led.sw2()
        if sw2 == 1:
          # short
          self.radio.nextchannel()
        elif sw2 == 2:
          # long
          self.led.blink(0b0111, 0b0111, 0.5, 1)
          self.radio.current = 0
          self.radio.changechannel(self.radio.channels[0])
          
        hmode = (self.led.sw1() == 1)

        # send ir
        if self.led.sw1():
          pass

        self.led.all(hmode << 3 | self.radio.current)
        time.sleep(0.05)

    # Ctrl+Cが押されたらGPIOを解放
    except KeyboardInterrupt:
      self.close()
      sys.exit(1)
    except Exception as e:
      exc_type, exc_obj, tb = sys.exc_info()
      lineno = tb.tb_lineno
      self.logger.error("Unexpected error: line {}: {}: {}".format(lineno, str(type(e)), e))
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
  logger.info('started room at {0}'.format(starttime))
  signal.signal(signal.SIGTERM, termed)
  main = Main(logger)
  main.run()
