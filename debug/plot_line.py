import matplotlib as mpl
mpl.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
import time
import sys

DATA_LEN = 32768
TIME_START = 0


# import matplotlib.rcsetup as rcsetup
# print(rcsetup.all_backends)

assert mpl.rcParams['backend'] == 'TkAgg'


def tic(task):
    global TICTOC
    TICTOC = (time.time(), task)


def toc():
    global TICTOC
    print('tictoc \'%s\'' % TICTOC[1], time.time() - TICTOC[0]
    sys.stdout.flush()


def get_data():
    print('in'
    sys.stdout.flush()
    time.sleep(np.random.rand() * 2)
    print('out'
    sys.stdout.flush()
    return np.random.randn(DATA_LEN), np.random.randn(DATA_LEN)

subplots = [plt.subplot(2, 1, 1), plt.subplot(2, 1, 2)]

plt.ion()
plt.show()

while True:

    (a, b) = get_data()

    subplots[0].clear()
    subplots[1].clear()

    subplots[0].plot(a)
    subplots[1].plot(b)

    plt.draw()
