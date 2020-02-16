import sys
import subprocess

if len(sys.argv) < 3:
  sys.stderr.write('python3 scan.py name')
name = sys.argv[1]

try:
  conf = open(f'lirc/lirc.conf.d/{name}', 'w')
  conf.write(f'''\
begin remote
 name {name}
 flags RAW_CODES
 eps 30
 aeps 100
 gap 200000
 toggle_bit_mask 0x0

 begin raw_codes
 name button
''')
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
  conf.write(f'''
 end raw_codes
end remote
''')
  conf.close()
  mode2.kill()
  print('ok')
