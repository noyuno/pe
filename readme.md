# 1. インターネットラジオ

## 1. 要件

1. Raspberry Pi 4 (4GB)
2. ダイソー スピーカ(300円)（改造）
5. RPZ-IR-Sensor(4450円)
6. 人感センサ
7. 2019-04-08-raspbian-stretch-lite

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
sudo apt-mark hold raspberrypi-kernel linux
sudo apt update
sudo apt install -y libusb-dev git mpg321 rtmpdump swftools libxml2-utils python3-pip libi2c-dev wiringpi
pip3 install --user rpi.gpio
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


## 7. スピーカテスト

~~~
mpg321 pastel-house.mp3
~~~

## 8. Radikoテスト

~~~
bash play_radiko.sh
~~~

## 9. Pythonスクリプト

~~~
python3 run.py
DEBUG=1 python3 run.py
~~~

## 10. 赤外線で各種機器を操作

[LIRCでRaspberry Piの赤外線制御 (Raspbian Stretchの設定方法) – Indoor Corgi](https://www.indoorcorgielec.com/resources/%e5%bf%9c%e7%94%a8%e4%be%8b/lirc%e3%81%a7rpitph-monitor-rpz-ir-sensor%e3%81%ae%e8%b5%a4%e5%a4%96%e7%b7%9a%e5%88%b6%e5%be%a1/lirc%e3%81%a7rpitph-monitor-rpz-ir-sensor%e3%81%ae%e8%b5%a4%e5%a4%96%e7%b7%9a%e5%88%b6%e5%be%a1-stretch/)

