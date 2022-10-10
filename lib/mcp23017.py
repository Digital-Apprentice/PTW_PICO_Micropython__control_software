"""
MicroPython MCP23017 16-bit I/O Expander
https://github.com/mcauser/micropython-mcp23017
MIT License
Copyright (c) 2019 Mike Causer
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all

"""

__version__ = '0.1.4' # - shortened version, adapted to the Put to Wall project, modified by Tomasz Zgrys - 08-01-2022

# register addresses in port=0, bank=1 mode (easier maths to convert)
_MCP_IODIR        = const(0x00) # R/W I/O Direction Register
_MCP_IOCON        = const(0x05) # R/W Configuration Register
_MCP_GPIO         = const(0x09) # R/W General Purpose I/O Port Register


class Port():
    # represents one of the two 8-bit ports
    def __init__(self, port, mcp):
        self._port = port & 1  # 0=PortA, 1=PortB
        self._mcp = mcp

    def _which_reg(self, reg):
        if self._mcp._config & 0x80 == 0x80:
            # bank = 1
            return reg | (self._port << 4)
        else:
            # bank = 0
            return (reg << 1) + self._port

    def _flip_property_bit(self, reg, condition, bit):
        if condition:
            setattr(self, reg, getattr(self, reg) | bit)
        else:
            setattr(self, reg, getattr(self, reg) & ~bit)

    def _read(self, reg):
        return self._mcp._i2c.readfrom_mem(self._mcp._address, self._which_reg(reg), 1)[0]

    def _write(self, reg, val):
        val &= 0xff
        self._mcp._i2c.writeto_mem(self._mcp._address, self._which_reg(reg), bytearray([val]))
        # if writing to the config register, make a copy in mcp so that it knows
        # which bank you're using for subsequent writes
        if reg == _MCP_IOCON:
            self._mcp._config = val

    @property
    def mode(self):
        return self._read(_MCP_IODIR)
    @mode.setter
    def mode(self, val):
        self._write(_MCP_IODIR, val)

    @property
    def gpio(self):
        return self._read(_MCP_GPIO)
    @gpio.setter
    def gpio(self, val):
        # writing to this register modifies the OLAT register for pins configured as output
        self._write(_MCP_GPIO, val)


class MCP23017():
    def __init__(self, i2c, address=0x20):
        self._i2c = i2c
        self._address = address
        self._config = 0x00
        self.init()

    def init(self):
        # error if device not found at i2c addr
        if self._i2c.scan().count(self._address) == 0:
            raise OSError('MCP23017 not found at I2C address {:#x}'.format(self._address))

        self.porta = Port(0, self)
        self.portb = Port(1, self)

        self.io_config = 0x00      # io expander configuration - same on both ports, only need to write once

        # Reset to all inputs with no pull-ups and no inverted polarity.
        self.mode = 0xFFFF                       # in/out direction (0=out, 1=in)
        self.input_polarity = 0x0000             # invert port input polarity (0=normal, 1=invert)
        self.interrupt_enable = 0x0000           # int on change pins (0=disabled, 1=enabled)
        self.default_value = 0x0000              # default value for int on change
        self.interrupt_compare_default = 0x0000  # int on change control (0=compare to prev val, 1=compare to def val)
        self.pullup = 0x0000                     # gpio weak pull up resistor - when configured as input (0=disabled, 1=enabled)
        self.gpio = 0x0000                       # port (0=logic low, 1=logic high)

    def config(self):
        io_config = self.porta.io_config


        # both ports share the same register, so you only need to write on one
        self.porta.io_config = io_config
        self._config = io_config

    def _flip_bit(self, value, condition, bit):
        if condition:
            value |= bit
        else:
            value &= ~bit
        return value

    def pin(self, pin, mode=None, value=None, default_value=None):
        assert 0 <= pin <= 15
        port = self.portb if pin // 8 else self.porta
        bit = (1 << (pin % 8))
        if mode is not None:
            # 0: Pin is configured as an output
            # 1: Pin is configured as an input
            port._flip_property_bit('mode', mode & 1, bit)
        if value is not None:
            # 0: Pin is set to logic low
            # 1: Pin is set to logic high
            port._flip_property_bit('gpio', value & 1, bit)

        if value is None:
            return port.gpio & bit == bit


    # gpio (GPIO register)
    @property
    def gpio(self):
        return self.porta.gpio | (self.portb.gpio << 8)
    @gpio.setter
    def gpio(self, val):
        self.porta.gpio = val
        self.portb.gpio = (val >> 8)

