import base64
import logging
import os
import subprocess
import urllib.parse
import xml.etree.ElementTree as et

import retry
import requests
import clog

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
    swf = subprocess.check_output(['swfextract', '-b', '12', '/dev/stdin', '-o', '/dev/stdout'], input=self.player.content, stderr=clog.LoggerWriter(self.logger, logging.WARNING))
    dd = subprocess.check_output(['dd', 'bs=1', 'skip=' + offset, 'count=' + length], input=swf, stderr=clog.LoggerWriter(self.logger, logging.WARNING))
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
    self.channels = ['']
    self.current = 0
    chan = requests.get(f'http://radiko.jp/v2/api/program/today?area_id={areaid}')
    for i in et.fromstring(chan.content).findall('./stations/station[@id]'):
      self.channels.append(i.attrib['id'])
    self.logger.debug(f'self.channels={self.channels}')

  #@retry.retry(tries=50, delay=10)
  def changechannel(self, channel):
    if channel == '':
      if self.mplayer != None and self.mplayer.poll() == None:
        self.mplayer.kill()
      if self.rtmpdump != None and self.rtmpdump.poll() == None:
        self.rtmpdump.kill()
      return

    r = requests.get(f'http://radiko.jp/v2/station/stream/{channel}.xml')
    streamurl = et.fromstring(r.content).find('./item').text
    u = urllib.parse.urlparse(streamurl)

    if self.mplayer != None and self.mplayer.poll() == None:
      self.mplayer.kill()
    if self.rtmpdump != None and self.rtmpdump.poll() == None:
      self.rtmpdump.kill()
    
    rtmpdumpcommand = [
      'rtmpdump',
      '-v',
      '-r', f'{u.scheme}://{u.netloc}',
      '--app', '/'.join(u.path.strip('/').split('/')[:-1]),
      '--playpath', u.path.split('/')[-1],
      '-W', self.player.url,
      '-C', 'S:', '-C', 'S:', '-C', 'S:', '-C', 'S:' + self.authtoken,
      '--live']
    if not os.environ.get('DEBUG'):
      rtmpdumpcommand.append('-q')
    self.logger.debug(' '.join(rtmpdumpcommand))
    self.rtmpdump = subprocess.Popen(rtmpdumpcommand, stdout=subprocess.PIPE, stderr=clog.LoggerWriter(self.logger, logging.WARNING), shell=False)
    mplayercommand = ['mplayer', '-nolirc', '-ao', 'alsa', '-channels', '2', '-af', 'pan=1:1', '-']
    if not os.environ.get('DEBUG'):
      mplayercommand.append('-quiet')
    self.mplayer = subprocess.Popen(mplayercommand, stdin=self.rtmpdump.stdout,
      stdout=clog.LoggerWriter(self.logger, logging.DEBUG), stderr=clog.LoggerWriter(self.logger, logging.WARNING), shell=False)
    
  def nextchannel(self):
    if self.mplayer != None and self.mplayer.poll() == None and \
       self.rtmpdump != None and self.rtmpdump.poll() == None:
      if self.current + 1 >= len(self.channels):
        self.current = 0
      else:
        self.current += 1
    else:
      if self.current == 0:
        self.current += 1
    self.changechannel(self.channels[self.current])

  def close(self):
    self.stop()

  def stop(self):
    self.pause()
    self.current = 0

  def pause(self):
    if self.mplayer != None and self.mplayer.poll() == None:
      self.mplayer.kill()
    if self.rtmpdump != None and self.rtmpdump.poll() == None:
      self.rtmpdump.kill()

  def resume(self):
    self.changechannel(self.channels[self.current])
    