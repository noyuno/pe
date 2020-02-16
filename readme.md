# 1. インターネットラジオ

## 1. 要件

1. Raspberry Pi zero
2. ダイソー スピーカ(300円)（改造）
5. RPZ-IR-Sensor(4450円)
6. 人感センサ

※RPI4はlinux 4.14不可(赤外線は4.14のみ確認)

## 2. 仕様

1. インターネットラジオが聞ける
4. 人がいるときにオン・いないときにオフ

## 3. raspi-config

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
sudo apt-mark hold raspberrypi-kernel raspberrypi-bootloader
sudo apt update
sudo apt -y upgrade
sudo apt install -y libusb-dev git mpg321 rtmpdump swftools mplayer libxml2-utils python3-pip libi2c-dev wiringpi lirc
pip3 install --user rpi.gpio schedule
git clone https://github.com/noyuno/room
~~~

## 5. エディタ等のインストール

~~~
sudo apt install -y zsh vim tmux
git clone https://github.com/noyuno/dotfiles
./dotfiles/bin/dfdeploy
~~~

RPiZeroでdotfilesの設定は重すぎてスクリプトが落ちるほどなので、適用しないこと。

~~~
rm .tmux.conf

~~~

## 6. 改造（任意）

分解してモノラル化。またコードの長さを短くしてはんだ付けをする。
最後にスピーカの上にラズパイをアクリル粘着テープで固定する。


## 7. スピーカテスト

~~~
mpg321 pastel-house.mp3
~~~

## 8. Radikoテスト

~~~
bash play_radiko.sh
~~~

## 10. 赤外線で各種機器の操作テスト

~~~
mkdir ir
sudo systemctl stop lircd
sudo rm -rf /etc/lirc
sudo ln -sfnv $HOME/room/lirc /etc/lirc

mode2 -d /dev/lirc0 > ir/iris-toggle
(C-C)
python3 convert.py iris-toggle

mode2 -d /dev/lirc0 > ir/ac-heating
(C-C)
python3 convert.py ac-heating

mode2 -d /dev/lirc0 > ir/iris-off
(C-C)
python3 convert.py iris-off

mode2 -d /dev/lirc0 > ir/ac-off
(C-C)
python3 convert.py ac-off

sudo systemctl restart lircd
irsend SEND_ONCE iris-toggle button
irsend SEND_ONCE ac-heating button
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
