import sys

if len(sys.argv) < 2:
  sys.stderr.write('python3 convert.py name\n')
  sys.exit(1)
name = sys.argv[1]

try:
  conf = open('lirc/lircd.conf.d/{}'.format(name), 'w')

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

  with open('ir/{}'.format(name), 'r') as mode2:
    num = 1
    while True:
      line = mode2.stdout.readline()
      if line is None:
        break
      if num < 3:
        continue
      if num % 2 == 0:
        conf.write(' ' + line)
      else:
        conf.write(line.strip('\n'))
      num += 1

  conf.write('''
 end raw_codes
end remote
''')
  conf.close()
