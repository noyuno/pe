import sys

if len(sys.argv) < 2:
  sys.stderr.write('python3 convert.py name\n')
  sys.exit(1)
name = sys.argv[1]

conf = open('lirc/lircd.conf.d/{}.conf'.format(name), 'w')

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
  num = 0
  while True:
    num += 1
    line = mode2.readline()
    if not line:
      break
    if num < 3:
      continue
    v = line.split(' ')[1]
    if num % 2 == 0:
      conf.write(' ' + v)
    else:
      conf.write(' ' + v.strip('\n'))

conf.write('''
end raw_codes
end remote
''')
conf.close()
