"""Minimal HD44780 16x2 over a PCF8574 I2C backpack (0x27 or 0x3F, bus 1)."""
import time

from smbus2 import SMBus

LCD_WIDTH = 16
EN, RW, RS, BL = 0x04, 0x02, 0x01, 0x08


class Lcd:
    def __init__(self, bus=1, addr=None):
        self.bus = SMBus(bus)
        self.addr = addr
        for a in ([addr] if addr else [0x27, 0x3F]):
            try:
                self.bus.write_byte(a, 0)
                self.addr = a
                break
            except OSError:
                continue
        if self.addr is None:
            raise OSError("no LCD backpack at 0x27/0x3F")
        for cmd in (0x33, 0x32, 0x06, 0x0C, 0x28, 0x01):
            self._cmd(cmd)
        time.sleep(0.005)

    def _pulse(self, data):
        self.bus.write_byte(self.addr, data | EN | BL)
        time.sleep(0.0005)
        self.bus.write_byte(self.addr, (data & ~EN) | BL)
        time.sleep(0.0001)

    def _write(self, bits, mode):
        self._pulse(mode | (bits & 0xF0))
        self._pulse(mode | ((bits << 4) & 0xF0))

    def _cmd(self, c):
        self._write(c, 0)

    def write(self, line1="", line2=""):
        for addr, text in ((0x80, line1), (0xC0, line2)):
            self._cmd(addr)
            for ch in text.ljust(LCD_WIDTH)[:LCD_WIDTH]:
                self._write(ord(ch), RS)
