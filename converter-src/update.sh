#!/bin/sh -ex
echo "YASM"
cd yasm
git pull
autoreconf -vif
./configure --prefix=$HOME/.local
make
make install
cd ..

echo "OGG"
cd libogg
git pull
autoreconf -vif
./configure --prefix=$HOME/.local
make
make install
cd ..


echo "Theora"
cd libtheora
git pull
autoreconf -vif
./configure --prefix=$HOME/.local
make
make install
cd ..

echo "Vorbis"
cd libvorbis
git pull
autoreconf -vif
./configure --prefix=$HOME/.local
make
make install
cd ..

echo "Opus"
cd libopus
git pull
autoreconf -vif
./configure --prefix=$HOME/.local
make
make install
cd ..

echo "VPx"
cd libvpx
git pull
autoreconf -vif || true
./configure --prefix=$HOME/.local
make
make install
cd ..

echo "ffmpeg"
cd ffmpeg
git pull
autoreconf -vif || true
./configure --prefix=$HOME/.local --enable-libtheora --enable-libvorbis --enable-libvpx --enable-libopus
make
make install
cd ..


echo "update.sh: done"
