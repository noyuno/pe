# 1. インターネットラジオ

## 1. 要件

1. Raspberry Pi 4 (4GB)
2. ダイソー スピーカ(300円)（改造）
5. センサーモジュール
6. 人感センサ
7. 各種ケーブル
8. 各種トランジスタ

## 2. 仕様

1. インターネットラジオが聞ける
4. 人がいるときにオン・いないときにオフ

## raspi-config

- `2. Network Options/N1 Hostname`
- `2. Network Options/Wi-fi`
- `4. Localization Option/I1 Change Locale`
- `4. Localization Option/I1 Change Keyboard Layout`
- `4. Localization Option/I1 Change Wi-fi Country`
- `5. Interfacing Options/P2 SSH`
- `7. Advanced Options/A1 Expand Filesystem...`
- `7. Advanced Options/A4 Audio`: `1 Force 3.5,, jack`

## 必要なソフトのインストール

~~~
sudo apt update
sudo apt upgrade -y
sudo apt install -y libusb-dev git mpg321 rtmpdump swftools libxml2-utils
git clone https://github.com/noyuno/room
~~~

## エディタ等のインストール

~~~
sudo apt install -y zsh vim tmux
git clone https://github.com/noyuno/dotfiles
./dotfiles/bin/dfdeploy
~~~

## 改造（任意）

分解してモノラル化。またコードの長さを短くしてはんだ付けをする。
最後にスピーカの上にラズパイをアクリル粘着テープで固定する。


## スピーカテスト

~~~
mpg321 pastel-house.mp3
~~~

## Radiko

~~~
bash play_radiko.sh
~~~

