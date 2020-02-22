# 1. インターネットラジオ

## 1. 要件

1. Raspberry Pi 4
2. ダイソー スピーカ(300円)（改造）
5. RPZ-IR-Sensor(4450円)
6. 人感センサ

## 2. 仕様

1. インターネットラジオが聞ける
4. 人がいるときにオン・いないときにオフ

## 3. 設定

### raspi-config

- `2. Network Options/N1 Hostname`
- `2. Network Options/Wi-fi`
- `4. Localization Option/I1 Change Locale`
- `4. Localization Option/I1 Change Keyboard Layout`
- `4. Localization Option/I1 Change Wi-fi Country`
- `5. Interfacing Options/P2 SSH`
- `7. Advanced Options/A1 Expand Filesystem...`
- `7. Advanced Options/A4 Audio`: `1 Force 3.5,, jack`

## 4. 必要なソフトのインストール

~~~
sudo apt update
sudo apt -y upgrade
sudo apt install -y libusb-dev git mpg321 rtmpdump swftools mplayer libxml2-utils python3-pip libi2c-dev pigpio python3-pigpio bluez ruby evtest
pip3 install --user schedule retry
sudo gem install bluebutton
git clone https://github.com/noyuno/room
~~~

## 5. エディタ等のインストール

~~~
sudo apt install -y zsh vim tmux
git clone https://github.com/noyuno/dotfiles
./dotfiles/bin/dfdeploy
~~~


## 6. 改造（任意）

分解してモノラル化。またコードの長さを短くしてはんだ付けをする。
最後にスピーカの上にラズパイをアクリル粘着テープで固定する。


## 7. スピーカ設定

~~~
sudo cp asound.conf /etc
mpg321 pastel-house.mp3
~~~

## 8. Radikoテスト

~~~
bash play_radiko.sh NACK5
~~~

## 10. 赤外線で各種機器の操作テスト・登録

~~~
sudo systemctl start pigpiod
sudo systemctl status pigpiod
sudo systemctl enable pigpiod
echo 'm 13 w   w 13 0   m 4 r   pud 4 u' > /dev/pigpio
python3 irrp.py -r -g4 -f codes iris:off --no-confirm --post 100
python3 irrp.py -p -g13 -f codes iris:off
python3 irrp.py -r -g4 -f codes iris:toggle --no-confirm --post 100
python3 irrp.py -p -g13 -f codes iris:toggle
python3 irrp.py -r -g4 -f codes ac:off --no-confirm --post 100
python3 irrp.py -p -g13 -f codes ac:off
python3 irrp.py -r -g4 -f codes ac:heating --no-confirm --post 100
python3 irrp.py -p -g13 -f codes ac:heating
~~~

## Bluetooth

~~~
sudo cp bluetooth.conf /etc/dbus-1/system.d/bluetooth.conf
sudo reboot
~~~

~~~
bluetoothctl
> scan on
[NEW] Device FF:FF:C1:21:C6:9D AB Shutter3
> connect FF:FF:C1:21:C6:9D
> pair FF:FF:C1:21:C6:9D
> trust FF:FF:C1:21:C6:9D
> quit

~~~



## 9. Pythonスクリプト

~~~
python3 run.py
DEBUG=1 python3 run.py
~~~

## Pythonスクリプトをデーモン化

~~~
sudo cp room.service /etc/systemd/system/
sudo systemctl start room
sudo systemctl status room
sudo systemctl enable room
~~~

## トラブルシューティング

### しばらくするとラジオにノイズ対策

sudo nano /etc/rc.local

~~~
iwconfig wlan0 power off
~~~