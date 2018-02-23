import matplotlib as mpl
mpl.use('TkAgg')
import matplotlib.pyplot as plt
import numpy as np
import time
import sys

DATA_LEN = 32768
TIME_START = 0
ION = False
DONE = False

# import matplotlib.rcsetup as rcsetup
# print(rcsetup.all_backends)

assert mpl.rcParams['backend'] == 'TkAgg'


class Corr2Plot(object):

    def __init__(self, figure, data_source, plot_function, animated=True):

        self.figure = figure
        self.data_source = data_source
        self.plot_function = plot_function
        self.animated = animated
        self.done = None

        self.figure.canvas.mpl_connect('close_event', self.on_close)
        self.figure.canvas.mpl_connect('key_release_event', self.redraw)

    def run(self):
        self.done = False
        self.figure.canvas.manager.window.after(50, self.plot_function, self)
        try:
            plt.show()
        except AttributeError:
            pass

    def redraw(self, key_event):
        if self.animated:
            return
        if key_event.key == 'x':
            self.figure.canvas.manager.window.after(
                50, self.plot_function, self)

    def on_close(self, close_event):
        self.done = True

    def running(self):
        return not self.done


def tic(task):
    global TICTOC
    TICTOC = (time.time(), task)


def toc():
    global TICTOC
    print('tictoc \'%s\'' % TICTOC[1], time.time() - TICTOC[0]
    sys.stdout.flush()


def get_data():
    time.sleep(np.random.rand() * 2)
    return np.random.randn(DATA_LEN), np.random.randn(DATA_LEN)


def plot_func(plot_object):
    figure = plot_object.figure

    tic('get_data')
    (a, b) = plot_object.data_source()
    toc()

    figure.axes[0].clear()
    figure.axes[1].clear()

    tic('plotting')
    figure.axes[0].plot(a)
    figure.axes[1].plot(b)
    toc()

    figure.axes[0].grid(True)
    figure.axes[1].grid(True)

    tic('canvas_draw')
    figure.canvas.draw()
    toc()

    if plot_object.animated:
        figure.canvas.manager.window.after(10, plot_func, plot_object)


fig = plt.figure()
fig.add_subplot(2, 1, 1)
fig.add_subplot(2, 1, 2)

c2plt = Corr2Plot(fig, get_data, plot_func, True)
c2plt.run()

while True:
    try:
        if not c2plt.running():
            break
        time.sleep(0.5)
    except KeyboardInterrupt:
        break
