"""Handle multiprocessing helpers before a frozen Qt app starts."""

import multiprocessing

multiprocessing.freeze_support()
