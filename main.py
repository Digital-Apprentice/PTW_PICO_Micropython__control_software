# main.py - 'Put to Wall concept' picking wall control
# Author: Tomasz Zgrys AiR, 2021/2022, WWSIS Horyzont
# Copyright: Tomasz Zgrys & WWSIS Horyzont


import micropython
from machine import Timer
from ptw import *

micropython.alloc_emergency_exception_buf(100)
micropython.mem_info()

# turn on onboard LED to show it works ;
__onboard_led_pin = Pin(25, Pin.OUT)
__onboard_led_pin.high()

# batch intitialization
b = Batch()

# shelf intitialization - 9 pcs
s = [None] * 9
for i in range(len(s)):
    s[i] = Shelf(i)

# Uart initialization
u = UART_com()

counter = 0         # counter of the number of beeps after the end of the process
sound = 'ENABLED'
time.sleep(5)       # wait 5s for other ICs to initialize
t = True

# timer initialization - for led flashing
timer = Timer()

def blink_timer(state):
    # timer intitialization or deinitialization
    if state == "on":
        timer.init(period=450, mode=Timer.PERIODIC, callback = tm1638_led_blink)
        # every 450 ms calculate the values of the tm1638 registers and send to the chip
    elif state == "off":
        timer.deinit()
        # stop the timer

def blink(l_on,l_off):
    # leds flashing, sending data to tm1638 registers
        global t
        if t is True:
            tm.write(l_on, 0)           
            __onboard_led_pin.high()
        else:
            tm.write(l_off, 0)           
            __onboard_led_pin.low()
        t = not t

def selftest():
    blink_timer("off")
    b.buzzer(4, 70, 40, sound)
    counter = 0
    val1 = 1
    val2 = 2
    tm.write([0, 2])
    b.print_message('SELFTEST', 0)
    b.print_message('PROCEDURE', 1)
    while counter < 10:
        if counter == 8:
            val2 += 1
            val1 = 0
        elif counter == 9:
            val2 = 2
        if counter < 9:
            s[counter].print_message(str(counter + 1), 0)
        tm.write([val1, val2, val1, val2, val1, val2, val1, val2])
        if counter > 0:
            s[counter - 1].clear_lcd()
        time.sleep_ms(250)
        val1 *= 2
        counter += 1
    for i in range(3):      
        b.buzzer(1, 70, 40,sound)
        tm.write([255, 3, 255, 1, 255, 1, 255, 1])
        time.sleep_ms(250)
        tm.write([0, 0, 0, 0, 0, 0, 0, 0])
        time.sleep_ms(250)
    tm.write([0, 2])
    b.print_message('Test', 0)
    b.print_message('finished', 1)
    b.buzzer(4,70,40,sound)
    b.clear_lcd()
    blink_timer("on")

def lonloff_clear():
    # clearing variables for tm1638 registers
    global l_on, l_off
    l_on = [0, 0, 0, 0, 0, 0, 0, 0]
    l_off = [0, 0, 0, 0, 0, 0, 0, 0]
    check_batch()


def check_batch():
    # updates data of tm1638 registers depending on the b.blink_batch_display flag or batch ending
    if not b.blink_batch_display or b.finished:
        l_on[1] |= 2
        l_off[1] |= 2
    else:
        l_on[1] |= 2
        l_off[1] |= 0

def tm1638_led_blink(timer):
    # computes data for tm1638 data registers
    lonloff_clear()
    for i in range(9):
        l1, l2 = s[i].led_value()
        for j in range(8):
            l_on[j] |= l1[j]
            l_off[j] |= l2[j]
    blink(l_on, l_off)

def update_ptw():
    # take action based on control commands
    global sound
    for data in u.update_list:
                      
        if data[0] == 'U':
            if len(data) >= 5:
                update_data(data)
            else:
                u.send_message('E',9,'ERROR') 
        elif data[0] == 'UNREGISTER':
            if data[3] == b.batch_no:
                b.print_message('UNREGISTERING')
                b.end_time = time.ticks_ms()
                for shelf in s:
                    shelf.shelf_init()
                    shelf.clear_lcd()
                u.update_list.remove(data)            
                b.buzzer(3,20,20,sound)      
                u.send_message('UNREGISTER',9,'BATCH UNREGISTERED',b.batch_no)
                tm.write([0, 2])
                b.print_message('BATCH',0)
                b.print_message('UNREGISTERED',1)
                b.batch_init()
                time.sleep_ms(500)
                b.buzzer(1,500,1,sound)
                b.clear_lcd()
            else:
                b.print_message('Batch  number',0)
                b.print_message("doesn't match",1)
                b.buzzer(5,20,20,sound)
                time.sleep_ms(1000)
                u.send_message('UNREGISTER',9,'FAILED',b.batch_no)
                b.update_lcd()
        elif data[0] == 'SOUND':
            if data[4] == 'ENABLED':
                sound = 'ENABLED'
            elif data[4] == 'DISABLED':
                sound == 'DISABLED'
            u.update_list.remove(data)
        elif data[0] == 'SELFTEST':
            u.send_message('SELFTEST',9,'IN PROGRESS')
            selftest()
            u.send_message('SELFTEST',9,'FINISHED')
            u.update_list.remove(data)
        elif data[0] == 'READY?':
            u.send_message('READY',9,'SELFTEST?')
            u.update_list.clear()
        elif data[0] == 'BLIP':
            if data[3] and data[4] and data[5]:
                b.buzzer(int(data[3]),int(data[4]),int(data[5]),sound)    
            u.update_list.remove(data)
                
        

def check_conformation(data, shelf_no):
    # uart data correctness control (only for shelf objects)
    check_conformity = 0
    if data[1] == 'S' and int(data[2]) < 9:
        if s[shelf_no].order_no == data[3]:
            check_conformity |= 1
        if s[shelf_no].item_no < int(data[4]):
            check_conformity |= 2
        if s[shelf_no].items_qty == int(data[5]):
            check_conformity |= 4
    else:
        b.print_message('Type error', 0)
        u.send_message('E', shelf_no, 'ET')
        return False

    if check_conformity == 7:
        return True
    else:
        u.update_list.remove(data)
        u.send_message('E', shelf_no, 'SA')
        return False


def update_data(data):
    # updating objects data
    shelf_no = int(data[2])
    if data[0] == 'U':
        if b.batch_no is not None:
            if data[1] == 'S':
                if s[shelf_no].order_no is not None:
                    if check_conformation(data, shelf_no):
                        s[shelf_no].waiting_front_conf = True
                        u.to_confirm.update({int(data[2]): data})
                        u.update_list.remove(data)
                else:
                    s[shelf_no].order_no = data[3]
                    s[shelf_no].items_qty = int(data[5])
                    s[shelf_no].shelf_empty = False
                    s[shelf_no].shelf_full = False
                    s[shelf_no].waiting_front_conf = True
                    u.to_confirm.update({shelf_no: data})
                    s[shelf_no].update_lcd()
                    u.update_list.remove(data)
            elif data[1] == 'B':                    
                if data[3] == b.batch_no:
                    b.print_message("Batch exist !!!", 0)
                    u.send_message('E', 9, 'NE')
                    u.update_list.remove(data)
                else:
                    b.print_message("Batch error", 0)
                    u.send_message('E', 9, 'FI')
                    u.update_list.remove(data)
            else:
                b.print_message('Type error', 0)
                u.send_message('E', 9, 'TE')
                u.update_list.remove(data)
        else:
            if data[1] == 'B':
                b.blink_batch_display = False
                b.batch_no = data[3]
                b.orders_qty = int(data[4])
                b.carts_qty = int(data[5])
                b.start_time = time.ticks_ms()
                b.update_lcd()
                u.send_message('C', 9,'BA',b.batch_no)
                u.update_list.remove(data)
                b.buzzer(3,30,40,sound)
            else:
                b.print_message('First', 0)
                b.print_message('assign batch !', 1)
                b.blink_batch_display = True
                u.send_message('E', 9,'BNA')
                u.update_list.clear()


lonloff_clear()      # clear register data for tm1638
blink_timer("on")    # start timer for led flashing

# main loop
while True:
    
    if b.batch_no is None:
        b.blink_batch_display = True
    else:
        b.blink_batch_display = False

    u.uart_read()

    if u.__rx_data:
        #read data from uart buffer
        u.receive_commands()
        if u.received_commands:
            # if data is in buffer, process it
            update_ptw()
            #micropython.mem_info() # - for debugging purposes

    for shelf in s:
        # checking shelf objects
        if shelf.button_front:
            if int(u.to_confirm.get(shelf.shelf_no)[4]) == shelf.item_no:
                b.buzzer(1,8,1,sound)            
                u.send_message('C', shelf.shelf_no, 'BFP', shelf.order_no)
                shelf.update_lcd(1)
                time.sleep_ms(350) 
                if shelf.item_no == shelf.items_qty:
                    shelf.shelf_full = True
                    shelf.waiting_back_conf = True
                    shelf.waiting_front_conf = False
                    u.send_message('C', shelf.shelf_no, 'SFD',shelf.order_no)
                shelf.button_front = False
                u.to_confirm.pop(shelf.shelf_no)
                 
        elif shelf.button_back is True and shelf.shelf_full is True:
            b.buzzer(1,10,1,sound) 
            u.send_message('C', shelf.shelf_no, 'BBP',shelf.order_no)
            shelf.shelf_init()
            shelf.clear_lcd()
            if b.orders_qty > 0:
                b.orders_qty -= 1
                if b.orders_qty == 0:
                    u.send_message('C',9,'BATCH FINISHED',b.batch_no)
                    b.finished = True
            else:
                b.print_message('Qty. orders error', 0)
                u.send_message('E', 9, 'FQ')
            b.update_lcd(1)
    if b.finished == False:
        counter = 0
    if b.orders_qty == 0 and b.finished == True:
        b.print_message('Batch completed',0)
        time.sleep_ms(900)
        b.print_message('Unregister Batch',0)
        if counter <4:
            b.buzzer(5,40,40,sound)
            counter += 1
        time.sleep_ms(500)








