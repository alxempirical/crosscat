FROM ubuntu:14.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update
RUN apt-get build-dep -y python
RUN apt-get install -y git gcc g++ libboost-dev
RUN apt-get install -y python-numpy python-matplotlib python-pip cython
RUN git clone https://github.com/probcomp/crosscat
RUN git clone https://github.com/python/cpython
RUN apt-get install -y python-pytest
RUN apt-get install -y wget zlib1g-dev
RUN apt-get install -y libssl-dev
WORKDIR cpython
RUN git checkout 2.7
# --with-zlib needed for get-pip.py https://github.com/pypa/pip/issues/1919
# Same for --with-ssl
RUN ./configure --prefix=/root --with-zlib --with-ssl
RUN CFLAGS=-g make -j 4
RUN make install
RUN wget -q https://bootstrap.pypa.io/get-pip.py
RUN /root/bin/python get-pip.py
RUN /root/bin/pip install cython numpy
RUN /root/bin/pip install pytest
RUN apt-get install -y gdb
RUN apt-get install -y emacs tmux
COPY . /root/my-crosscat
WORKDIR /root/my-crosscat
RUN find . -name \*.o -name \*.so -exec rm {} \;

RUN /root/bin/python setup.py develop
# RUN ./check.sh
