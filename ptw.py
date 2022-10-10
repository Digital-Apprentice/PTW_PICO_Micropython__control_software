# ptw.py - picking wall control
# Author: Tomasz Zgrys AiR, 2021/2022, WWSIS Horyzont
# Copyright: Tomasz Zgrys & WWSIS Horyzont
# Classes related to the PTW order picking wall
# Batch class - a class related to batch and wall initialization
# Shelf class - all variables and methods for each compartment / shelf
# Display class - control of displays
# LED1638 class - controlling the appriopriate LED's
# Uart_com class - cummunication via UART

from micropython import const
from machine import Pin, I2C, UART

# turn on onboard LED to show it works ;
__onboard_led_pin = Pin(25, Pin.OUT)

import uasyncio as asyncio
import tm1638
import i2c23_lcd1602 as D
import mcp23017 as MCP
import time

# initialization of MCP23017 - GPIO Extender & LCD Displays
i2c = I2C(0, scl=Pin(5), sda=Pin(4), freq=400_000)

__gpio_mcp = MCP.MCP23017(i2c, 0x20)
__lcd_mcp_e_pins = (5, 6, 7, 8, 9, 10, 11, 12, 13, 14)
__buzzer_mcp_pin = (15)
# __lcd_mcp_batch_e_pin = const(14)
__lcd_mcp_rs_pin = const(0)
__lcd_mcp_d4_pin = const(1)
__lcd_mcp_d5_pin = const(2)
__lcd_mcp_d6_pin = const(3)
__lcd_mcp_d7_pin = const(4)
__lcd_columns = const(16)
__lcd_rows = const(2)

# LED driver initialization
tm = tm1638.TM1638(stb=Pin(28), clk=Pin(3), dio=Pin(2))
__seg_value = (1, 2, 4, 8, 16, 32, 64, 128, 1)
__grid_pos = (0, 0, 0, 0, 0, 0, 0, 0, 1)
__front_light_pos_offset = const(2)
__back_red_light_pos_offset = const(4)
__back_green_light_pos_offset = const(6)

# GPIO Pins for confirmation buttons
__front_button_pins = (6, 7, 8, 9, 10, 11, 12, 13, 14)
__back_button_pins = (15, 16, 17, 18, 19, 20, 21, 22, 26)
__batch_button_pin = const(27)

# Display data
__disp_words = ('Quantity:', 'Order:', 'C:', 'Orders:', 'Batch:')

# miganie ledami
t = True

class Display():
    def __init__(self, disp_type, shelf_no):
        self.shelf_no = shelf_no
        self.disp_type = disp_type
        self.display_init()

    def display_init(self):
        self.lcd = D.display(__lcd_mcp_rs_pin, __lcd_mcp_e_pins[self.shelf_no], __lcd_mcp_d4_pin, __lcd_mcp_d5_pin,
                             __lcd_mcp_d6_pin, __lcd_mcp_d7_pin, __lcd_columns, __lcd_rows, __gpio_mcp)
        self.clear_lcd()

    def clear_lcd(self,message='EMPTY'):
        self.lcd.write8(0x01)
        self.lcd.clear()
        self.lcd.set_cursor(5, 0)
        self.lcd.message(message)

    def __string(self, l):
        # format text on display (centers it)
        if l > 2: l = 2
        __lines = [''] * l
        if self.disp_type is 'S':
            for i in range(l):
                string1 = __disp_words[i]
                if i == 0:
                    string2 = str(self.item_no) + '/' + str(self.items_qty)
                else:
                    string2 = str(self.order_no)
                spaces = 16 - len(string1 + string2)
                __lines[i] = string1 + ' ' * spaces + string2
        else:
            for i in range(l):
                if i == 0:
                    string1 = __disp_words[i + 2] + str(self.carts_qty)
                    string2 = __disp_words[i + 3] + str(self.orders_qty)
                else:
                    string1 = __disp_words[i + 3]
                    string2 = str(self.batch_no)
                spaces = 16 - len(string1 + string2)
                __lines[i] = string1 + ' ' * spaces + string2
        return __lines

    def update_lcd(self, l=2):
        # updates the displayed text based on the values of the object's variables
        self.lcd.set_cursor(0, 0)
        lines = self.__string(l)
        for row, string in enumerate(lines):
            self.lcd.set_cursor(0, row)
            self.lcd.message(string)

    def print_message(self, string, row=0):
        # formats any text (centers it) - and displays it
        if row > 1: row = 1
        dlugosc = len(string)
        spaces = 8 - int(dlugosc / 2)
        string = ' ' * spaces + string + ' ' * spaces
        self.lcd.set_cursor(0, row)
        self.lcd.message(string)
        
    def set_time(self, mode='end'):
        # writes the start or end time to a variable
        if mode == 'start':
            self.start_time = time.ticks_ms()
            print('st', self.start_time)
        else:
            self.end_time = time.ticks_ms()
            print('et', self.end_time)

    def time_diff(self):
        # count time difference
        return time.ticks_diff(self.end_time, self.start_time)

    def buzzer(self,hms=4,td=200,sd=200,sound='ENABLED'):
        # emits a preset sequence of beeps
        if sound == 'ENABLED':
            while hms>0:
                __gpio_mcp.pin(__buzzer_mcp_pin,mode=0,value=1)
                time.sleep_ms(td)
                __gpio_mcp.pin(__buzzer_mcp_pin,mode=0,value=0)
                time.sleep_ms(sd)
                hms -=1
        elif sound == 'DISABLED':
             while hms>0:
                __gpio_mcp.pin(__buzzer_mcp_pin,mode=0,value=0)
                time.sleep_ms(td+sd)
                hms -=1     
        
class Shelf(Display):
    # shelf objects
    def __init__(self, shelf_no):
        super().__init__('S', shelf_no)   # inherit Display methods
        self.shelf_no = shelf_no
        self.shelf_init()

    def shelf_init(self):
        self.shelf_empty = True
        self.shelf_full = False
        self.waiting_front_conf = False
        self.waiting_back_conf = False
        self.button_front = False
        self.button_back = False
        self.order_no = None
        self.items_qty = 0
        self.item_no = 0
        self.start_time = 0
        self.end_time = 0
        self.button_init()

    def button_init(self):
        self.buttonF = Pin(__front_button_pins[self.shelf_no], Pin.IN, Pin.PULL_DOWN)
        self.buttonB = Pin(__back_button_pins[self.shelf_no], Pin.IN, Pin.PULL_DOWN)
        self.buttonF.irq(lambda pin: self.set_button_value('Front'), Pin.IRQ_RISING, hard=True)
        self.buttonB.irq(lambda pin: self.set_button_value('Back'), Pin.IRQ_RISING, hard=True)

    def set_button_value(self, b_id):      
        # interrupt handling procedure after pressing a button
        self.__b_id = b_id       
        if self.__b_id == 'Front' and self.waiting_front_conf and not self.waiting_back_conf and not self.shelf_full:
            self.button_front = True 
            if self.item_no < self.items_qty:
                if self.item_no == 0:
                    self.set_time('start')
                self.item_no += 1
                self.waiting_front_conf = False         
        if self.__b_id == 'Back' and self.waiting_back_conf and self.shelf_full:
            self.waiting_front_conf = False
            self.button_front = False
            self.button_back = True
            self.set_time('end')


    def led_value(self):
        # calculating the register bit value for the tm1638 for the given object
        __lon = [0, 0, 0, 0, 0, 0, 0, 0]
        __loff = [0, 0, 0, 0, 0, 0, 0, 0]

        # lcd display backlight
        if self.order_no:
            __lon[__grid_pos[self.shelf_no]] = __seg_value[self.shelf_no]
            if self.shelf_full and not self.shelf_empty and self.waiting_back_conf:
                __loff[__grid_pos[self.shelf_no]] = 0
            else:
                __loff[__grid_pos[self.shelf_no]] = __seg_value[self.shelf_no]
        else:
            __lon[__grid_pos[self.shelf_no]] = 0
            __loff[__grid_pos[self.shelf_no]] = 0
    
        # front light confirmation
        if not self.waiting_front_conf:
            __lon[__grid_pos[self.shelf_no] + __front_light_pos_offset] = 0
            __loff[__grid_pos[self.shelf_no] + __front_light_pos_offset] = 0
        else:
            __lon[__grid_pos[self.shelf_no] + __front_light_pos_offset] = __seg_value[self.shelf_no]
            __loff[__grid_pos[self.shelf_no] + __front_light_pos_offset] = 0
    
        # lights on back - red and green
        if not self.waiting_back_conf and not self.shelf_full:   
            # red
            __lon[__grid_pos[self.shelf_no] + __back_red_light_pos_offset] = __seg_value[self.shelf_no]
            __loff[__grid_pos[self.shelf_no] + __back_red_light_pos_offset] = __seg_value[self.shelf_no]    
            # green
            __lon[__grid_pos[self.shelf_no] + __back_green_light_pos_offset] = 0
            __loff[__grid_pos[self.shelf_no] + __back_green_light_pos_offset] = 0
    
        else:   
            # red
            __lon[__grid_pos[self.shelf_no] + __back_red_light_pos_offset] = 0
            __loff[__grid_pos[self.shelf_no] + __back_red_light_pos_offset] = 0  
            # green
            __lon[__grid_pos[self.shelf_no] + __back_green_light_pos_offset] = __seg_value[self.shelf_no]
            __loff[__grid_pos[self.shelf_no] + __back_green_light_pos_offset] = 0
    
        return __lon, __loff


class Batch(Display):
    # batch object
    def __init__(self):
        super().__init__('B', 9)
        self.batch_init()
        
    def batch_init(self):
        self.batch_no = None
        self.orders_qty = 0
        self.carts_qty = 0
        self.batch_button = False
        self.blink_batch_display = True
        self.finished = False
        self.start_time = 0
        self.end_time = 0
        self.batch_button_init()

    def batch_button_init(self):
        self.buttonF = Pin(__batch_button_pin, Pin.IN, Pin.PULL_DOWN)
        self.buttonF.irq(lambda pin: self.set_batch_button_value(True), Pin.IRQ_RISING, hard=True)

    def set_batch_button_value(self, b_id):
        self.batch_button = b_id


class UART_com():
    # communication via UART interface, reading, writing, formatting data before sending, decoding data after receiving
    def __init__(self):
        self.__rx_data = bytes()
        self.uart_init()
        self.update_list = []
        self.to_confirm = {}
        self.error_messages = {}


    def uart_init(self):
        TX_pin = Pin(0, Pin.OUT, Pin.PULL_DOWN)
        RX_pin = Pin(1, Pin.IN, Pin.PULL_UP)
        self.uart = UART(0, baudrate=115200, tx=Pin(0), rx=Pin(1), timeout=5)
        #self.uart = UART(0, baudrate=115200, tx=TX_pin, rx=RX_pin, timeout=5)

    def uart_read(self):
        # reads data from the UART buffer
        self.__rx_data = bytes()
        while self.uart.any() > 0:
            __onboard_led_pin.high()
            self.__rx_data += bytes(self.uart.read(), 'ASCII')
            __onboard_led_pin.low()
        return self.__rx_data

    def uart_write(self, tx_data):
        # sends data to the control application
        __tx_data = bytes(('!' + str(tx_data) + '%\r\n'), 'ASCII')
        __onboard_led_pin.high()
        self.uart.write(__tx_data)
        print('uart_write',__tx_data)
        time.sleep_ms(5)
        __onboard_led_pin.low()

    def receive_commands(self):
        # extracts data from a text string
        self.received_commands = []
        hmb = 0
        hme = 0
        counter = 0
        hmb, hme = str(self.__rx_data).count('!'), str(self.__rx_data).count('%')
        command_string = str(self.__rx_data)
        if self.__rx_data is not None and hme and hmb:
            while hme and hmb:
                string_len = len(command_string)
                beg = command_string.find('!')
                end = command_string.find('%')
                if beg < end:
                    self.received_commands.append(command_string[beg + 1:end].split('#'))
                    hmb -= 1
                    hme -= 1
                    command_string = command_string[end + 1:]
                else:
                    command_string = self.__rx_data[end + 1:]
        self.update_list += self.received_commands
        print('update list from receive commands',self.update_list)
        return
    
    def send_message(self,mess_type, shelf_no, command, id_number=None):
        tx_data = ''
        object_type = ''
        if shelf_no < 9:
            object_type = 'S'
        else:
            object_type = 'B'
        tx_data = mess_type + '#' + object_type + '#' + str(shelf_no) + '#' + str(id_number) + '#' + str(command)
        self.uart_write(tx_data)
        return












