import sys
import subprocess

if len(sys.argv) < 3:
  sys.stderr.write('python3 scan.py name')
name = sys.argv[1]

try:
  conf = open('lirc/lirc.conf.d/{}'.format(name), 'w')
  conf.write('''\
begin remote
 name {}
 flags RAW_CODES
 eps 30
 aeps 100
 gap 200000
 toggle_bit_mask 0x0

 begin raw_codes
 name button
'''.format(name))
  print('type C-C to complete')
  mode2 = subprocess.Popen(['mode2', '-d', '/dev/lirc0'], stdout=subprocess.PIPE, shell=False)
  num = 1
  while True:
    line = mode2.stdout.readline()
    if num < 3:
      continue
    if num % 2 == 0:
      conf.write(' ' + line)
    else:
      conf.write(line.strip('\n'))
    num += 1
except KeyboardInterrupt:
  conf.write('''
 end raw_codes
end remote
''')
  conf.close()
  mode2.kill()
  print('ok')
