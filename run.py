# requirements: swfextract (swftools), rtmpdump, mplayer

import os
import time
from datetime import datetime
if not os.environ.get('DEBUG'):
  import RPi.GPIO as GPIO
import requests
import base64
import xml.etree.ElementTree as et
import subprocess
import urllib.parse
import threading
import logging

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
                                     datefmt='%Y%m%d-%H%S')
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
    if not os.environ.get('DEBUG'):
      GPIO.setmode(GPIO.BCM)

    # SW1, SW2ピン入力設定
    if not os.environ.get('DEBUG'):
      GPIO.setup(5, GPIO.IN, pull_up_down=GPIO.PUD_UP)
      GPIO.setup(6, GPIO.IN, pull_up_down=GPIO.PUD_UP)

    # LED1, 2, 3, 4ピン出力設定
      GPIO.setup(17, GPIO.OUT)
      GPIO.setup(18, GPIO.OUT)
      GPIO.setup(22, GPIO.OUT)
      GPIO.setup(27, GPIO.OUT)


  def on(self, mode, radio):
    GPIO.output(17, int(mode))
    GPIO.output(18, int(int(radio / 4) % 2))
    GPIO.output(22, int(int(radio / 2) % 2))
    GPIO.output(27, int(int(radio / 1) % 2))

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
    self.logger.debug(f'areaid={areaid}, self.authtoken={self.authtoken}')
    # get channel list
    chan = requests.get(f'http://radiko.jp/v2/api/program/today?area_id={areaid}')
    for i in et.fromstring(chan.content).findall('./stations/station[@id]'):
      self.channels.append(i.attrib['id'])
    self.logger.debug(f'self.channels={self.channels}')

  def changechannel(self, channel):
    r = requests.get(f'http://radiko.jp/v2/station/stream/{channel}.xml')
    streamurl = et.fromstring(r.content).find('./item').text
    u = urllib.parse.urlparse(streamurl)

    if self.mplayer != None and self.mplayer.poll() == None:
      self.mplayer.kill()
    if self.rtmpdump != None and self.rtmpdump.poll() == None:
      self.rtmpdump.kill()
    
    command = [
      'rtmpdump',
      '-v',
      '-r', f'{u.scheme}://{u.netloc}',
      '--app', '/'.join(u.path.strip('/').split('/')[:-1]),
      '--playpath', u.path.split('/')[-1],
      '-W', self.player.url,
      '-C', 'S:', '-C', 'S:', '-C', 'S:', '-C', 'S:' + self.authtoken,
      '--live']
    self.logger.debug(' '.join(command))
    self.rtmpdump = subprocess.Popen(command,
      stdout=subprocess.PIPE, shell=False)
    self.mplayer = subprocess.Popen([
      'mplayer',
      '-channels', '2',
      '-af', 'pan=1:1',
      '-'],
      stdin=self.rtmpdump.stdout, shell=False)
    
  def nextchannel(self):
    if self.current + 1 >= len(self.channels):
      self.current = 0
    else:
      self.current += 1
    # if self.thread != None and self.thread.is_alive():
    #   self.thread.
    # self.thread = threading.Thread(target=self.changechannel, kwargs={
    #   'channel': self.channels[self.current]
    # })
    # self.thread.start()
    self.changechannel(self.channels[self.current])

  def close(self):
    if self.mplayer != None and self.mplayer.poll() == None:
      self.mplayer.kill()
    if self.rtmpdump != None and self.rtmpdump.poll() == None:
      self.rtmpdump.kill()

def main(logger):
  radio = Radio(logger)
  radio.auth()
  radio.nextchannel()
  led = Led(logger)

  try:
    while True:
      # SW2 blackが押された場合
      if 0==GPIO.input(6):
        radio.nextchannel()
        
      # SW1 red
      mode = int(0==GPIO.input(5))
      # if 0==GPIO.input(5):
        # LED1, 2, 3, 4 点灯
        # GPIO.output(17, 1)
        # GPIO.output(18, 1)
        # GPIO.output(22, 1)
        # GPIO.output(27, 1)
      #SW2押されていない場合
      # else:
        # LED1, 2, 3, 4 消灯
        # GPIO.output(17, 0)
        # GPIO.output(18, 0)
        # GPIO.output(22, 0)
        # GPIO.output(27, 0)

      led.on(mode, radio.current)
      time.sleep(0.01)

  # Ctrl+Cが押されたらGPIOを解放
  except KeyboardInterrupt:
    GPIO.cleanup(5)
    GPIO.cleanup(6)
    GPIO.cleanup(17)
    GPIO.cleanup(18)
    GPIO.cleanup(22)
    GPIO.cleanup(27)
    radio.close()







if __name__ == "__main__":
  logger, starttime = initlogger()
  logger.info('started room at {0}'.format(starttime))
  main(logger)
