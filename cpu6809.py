#!/usr/bin/env python

"""
    DragonPy - Dragon 32 emulator in Python
    =======================================

    6809 is Big-Endian

    Links:
        http://dragondata.worldofdragon.org/Publications/inside-dragon.htm
        http://www.burgins.com/m6809.html
        http://koti.mbnet.fi/~atjs/mc6809/

    https://github.com/kjetilhoem/hatchling-32/blob/master/hatchling-32/src/no/k/m6809/InstructionSet.scala

        MAME
        http://mamedev.org/source/src/mess/drivers/dragon.c.html
        http://mamedev.org/source/src/mess/machine/dragon.c.html
        http://mamedev.org/source/src/emu/cpu/m6809/m6809.c.html

    :copyleft: 2013 by the DragonPy team, see AUTHORS for more details.
    :license: GNU GPL v3 or above, see LICENSE for more details.

    Based on:
        ApplePy - an Apple ][ emulator in Python:
        James Tauber / http://jtauber.com/ / https://github.com/jtauber/applepy
        originally written 2001, updated 2011
        origin source code licensed under MIT License
"""


import BaseHTTPServer
import inspect
import json
import logging
import re
import select
import socket
import struct
import sys

from DragonPy_CLI import DragonPyCLI
import os
from Dragon32_mem_info import DragonMemInfo, print_out


log = logging.getLogger("DragonPy")

bus = None # socket for bus I/O
ILLEGAL_OPS = (
    0x1, 0x2, 0x5, 0xb,
    0x14, 0x15, 0x18, 0x1b,
    0x38,
    0x41, 0x42, 0x45, 0x4b, 0x4e,
    0x51, 0x52, 0x55, 0x5b, 0x5e,
    0x61, 0x62, 0x65, 0x6b,
    0x71, 0x72, 0x75, 0x7b,
    0x87, 0x8f,
    0xc7, 0xcd, 0xcf
)


def signed5(x):
    """ convert to signed 5-bit """
    if x > 0xf: # 0xf == 2**4-1 == 15
        assert x <= 0x1f # 0x1f == 2**5-1 == 31
        x = x - 0x20 # 0x20 == 2**5 == 32
    return x

def signed8(x):
    """ convert to signed 8-bit """
    if x > 0x7f: # 0x7f ==  2**7-1 == 127
        assert x <= 0xff # 0xff == 2**8-1 == 255
        x = x - 0x100 # 0x100 == 2**8 == 256
    return x

def signed16(x):
    """ convert to signed 16-bit """
    if x > 0x7fff: # 0x7fff ==  2**15-1 == 32767
        assert x <= 0xffff # 0xffff == 2**16-1 == 65535
        x = x - 0x10000 # 0x100 == 2**16 == 65536
    return x


def byte2bit_string(data):
    return '{0:08b}'.format(data)


def opcode(code):
    """A decorator for opcodes"""
    def decorator(func):
        setattr(func, "_is_opcode", True)
        setattr(func, "_opcode", code)
        return func
    return decorator


class ROM(object):

    def __init__(self, cfg, start, size):
        self.cfg = cfg
        self.start = start
        self.end = start + size
        self._mem = [0x00] * size
        log.info("init %s Bytes %s (%s - %s)" % (
            size, self.__class__.__name__, hex(start), hex(self.end)
        ))

    def load(self, address, data):
        for offset, datum in enumerate(data):
            self._mem[address - self.start + offset] = datum

    def load_file(self, address, filename):
        with open(filename, "rb") as f:
            for offset, datum in enumerate(f.read()):
                index = address - self.start + offset
                try:
                    self._mem[index] = ord(datum)
                except IndexError:
                    size = os.stat(filename).st_size
                    log.error("Error: File %s (%sBytes in hex: %s) is bigger than: %s" % (
                        filename, size, hex(size), hex(index)
                    ))
        log.debug("Read %sBytes from %s into ROM %s-%s" % (
            offset, filename, hex(address), hex(address + offset)
        ))

    def read_byte(self, address):
        assert self.start <= address <= self.end, "Read %s from %s is not in range %s-%s" % (hex(address), self.__class__.__name__, hex(self.start), hex(self.end))
        byte = self._mem[address - self.start]
#         log.debug("Read byte %s: %s" % (hex(address), hex(byte)))
#         self.cfg.mem_info(address, "read byte")
        return byte

# print_mem_info = DragonMemInfo(print_out)
class RAM(ROM):
    def write_byte(self, address, value):
#         print_mem_info(
        self.cfg.mem_info(
            address, "write $%x to" % value,
#             shortest=False
            shortest=True
        )
        self._mem[address] = value





class Memory:
    def __init__(self, cfg=None, use_bus=True):
        self.cfg = cfg
        self.use_bus = use_bus

        self.rom = ROM(cfg, start=self.cfg.ROM_START, size=self.cfg.ROM_SIZE)

        if cfg:
            self.rom.load_file(self.cfg.ROM_START, cfg.rom)

        self.ram = RAM(cfg, start=self.cfg.RAM_START, size=self.cfg.RAM_SIZE)

        if cfg and cfg.ram:
            self.ram.load_file(self.cfg.RAM_START, cfg.ram)

    def load(self, address, data):
        if address < self.cfg.RAM_END:
            self.ram.load(address, data)

    def read_byte(self, cycle, address):
        if address < self.cfg.RAM_END:
            return self.ram.read_byte(address)
        elif self.cfg.ROM_START <= address <= self.cfg.ROM_END:
            return self.rom.read_byte(address)
        else:
            return self.bus_read(cycle, address)

    def read_word(self, cycle, address):
        #  little-endian or big-endian ?!?!
        return self.read_byte(cycle + 1, address + 1) + (self.read_byte(cycle, address) << 8)
#         return self.read_byte(cycle, address) + (self.read_byte(cycle + 1, address + 1) << 8)

    def write_byte(self, cycle, address, value):
        if address < self.cfg.RAM_END:
            self.ram.write_byte(address, value)
        if 0x400 <= address < 0x800 or 0x2000 <= address < 0x5FFF:
            self.bus_write(cycle, address, value)

    def bus_read(self, cycle, address):
        if not self.use_bus:
            return 0
        op = struct.pack("<IBHB", cycle, 0, address, 0)
        try:
            bus.send(op)
            b = bus.recv(1)
            if len(b) == 0:
                sys.exit(0)
            return ord(b)
        except socket.error:
            sys.exit(0)

    def bus_write(self, cycle, address, value):
        if not self.use_bus:
            return
        op = struct.pack("<IBHB", cycle, 1, address, value)
        try:
            bus.send(op)
        except IOError:
            sys.exit(0)


class ControlHandler(BaseHTTPServer.BaseHTTPRequestHandler):

    def __init__(self, request, client_address, server, cpu):
        self.cpu = cpu

        self.get_urls = {
            r"/disassemble/(\d+)$": self.get_disassemble,
            r"/memory/(\d+)(-(\d+))?$": self.get_memory,
            r"/memory/(\d+)(-(\d+))?/raw$": self.get_memory_raw,
            r"/status$": self.get_status,
        }

        self.post_urls = {
            r"/memory/(\d+)(-(\d+))?$": self.post_memory,
            r"/memory/(\d+)(-(\d+))?/raw$": self.post_memory_raw,
            r"/quit$": self.post_quit,
            r"/reset$": self.post_reset,
        }

        BaseHTTPServer.BaseHTTPRequestHandler.__init__(self, request, client_address, server)

    def log_request(self, code, size=0):
        pass

    def dispatch(self, urls):
        for r, f in urls.items():
            m = re.match(r, self.path)
            if m is not None:
                f(m)
                break
        else:
            self.send_response(404)
            self.end_headers()

    def response(self, s):
        self.send_response(200)
        self.send_header("Content-Length", str(len(s)))
        self.end_headers()
        self.wfile.write(s)

    def do_GET(self):
        self.dispatch(self.get_urls)

    def do_POST(self):
        self.dispatch(self.post_urls)

    def get_disassemble(self, m):
        addr = int(m.group(1))
        r = []
        n = 20
        while n > 0:
            dis, length = self.disassemble.disasm(addr)
            r.append(dis)
            addr += length
            n -= 1
        self.response(json.dumps(r))

    def get_memory_raw(self, m):
        addr = int(m.group(1))
        e = m.group(3)
        if e is not None:
            end = int(e)
        else:
            end = addr
        self.response("".join([chr(self.cpu.read_byte(x)) for x in range(addr, end + 1)]))

    def get_memory(self, m):
        addr = int(m.group(1))
        e = m.group(3)
        if e is not None:
            end = int(e)
        else:
            end = addr
        self.response(json.dumps(list(map(self.cpu.read_byte, range(addr, end + 1)))))

    def get_status(self, m):
        self.response(json.dumps(dict((x, getattr(self.cpu, x)) for x in (
            "accumulator",
            "x_index",
            "y_index",
            "stack_pointer",
            "program_counter",
            "sign_flag",
            "flag_V",
            "break_flag",
            "decimal_mode_flag",
            "interrupt_disable_flag",
            "flag_Z",
            "flag_C",
        ))))

    def post_memory(self, m):
        addr = int(m.group(1))
        e = m.group(3)
        if e is not None:
            end = int(e)
        else:
            end = addr
        data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        for i, a in enumerate(range(addr, end + 1)):
            self.cpu.write_byte(a, data[i])
        self.response("")

    def post_memory_raw(self, m):
        addr = int(m.group(1))
        e = m.group(3)
        if e is not None:
            end = int(e)
        else:
            end = addr
        data = self.rfile.read(int(self.headers["Content-Length"]))
        for i, a in enumerate(range(addr, end + 1)):
            self.cpu.write_byte(a, data[i])
        self.response("")

    def post_quit(self, m):
        self.cpu.quit = True
        self.response("")

    def post_reset(self, m):
        self.cpu.reset()
        self.cpu.running = True
        self.response("")


class ControlHandlerFactory:

    def __init__(self, cpu):
        self.cpu = cpu

    def __call__(self, request, client_address, server):
        return ControlHandler(request, client_address, server, self.cpu)


class CPU(object):

    def __init__(self, cfg, memory):
        self.cfg = cfg
        self.memory = memory

        if self.cfg.bus:
            self.control_server = BaseHTTPServer.HTTPServer(("127.0.0.1", 6809), ControlHandlerFactory(self))
        else:
            self.control_server = None

        self.index_x = 0 # X - 16 bit index register
        self.index_y = 0 # Y - 16 bit index register

        self.user_stack_pointer = 0 # U - 16 bit user-stack pointer
        self.stack_pointer = 0 # S - 16 bit system-stack pointer

        self.value_register = 0 # V - 16 bit variable inter-register

        self.program_counter = -1 # PC - 16 bit program counter register

        self.accumulator_a = 0 # A - 8 bit accumulator
        self.accumulator_b = 0 # B - 8 bit accumulator
        self.accumulator_e = 0 # E - 8 bit accumulator
        self.accumulator_f = 0 # F - 8 bit accumulator

        # D - 16 bit concatenated reg. (A + B)
        # W - 16 bit concatenated reg. (E + F)
        # Q - 32 bit concatenated reg. (D + W)

        # CC - 8 bit condition code register bits
        self.flag_E = 0 # E - bit 7 - Entire register state stacked
        self.flag_F = 0 # F - bit 6 - FIRQ interrupt masked
        self.flag_H = 0 # H - bit 5 - Half-Carry
        self.flag_I = 0 # I - bit 4  - IRQ interrupt masked
        self.flag_N = 0 # N - bit 3 - Negative result (twos complement)
        self.flag_Z = 0 # Z - bit 2 - Zero result
        self.flag_V = 0 # V - bit 1 - Overflow
        self.flag_C = 0 # C - bit 0 - Carry (or borrow)

        self.mode_error = 0 # MD - 8 bit mode/error register
        self.condition_code = 0
        self.direct_page = 0 # DP - 8 bit direct page register

        self.cycles = 0

        self.opcodes = {}
        for name, value in inspect.getmembers(self):
            if inspect.ismethod(value) and getattr(value, "_is_opcode", False):
                self.opcodes[getattr(value, "_opcode")] = value

        for illegal_ops in ILLEGAL_OPS:
            self.opcodes[illegal_ops] = self.illegal_op

#         self.program_counter = 0x8000
#         self.program_counter = 0xb3b4
        self.program_counter = 0xb3ba
#         self.reset()
#         if cfg.pc is not None:
#             self.program_counter = cfg.pc

        self.running = True
        self.quit = False

    ####

    def status_from_byte(self, status):
        status_bits = [0 if status & x == 0 else 1 for x in (128, 64, 32, 16, 8, 4, 2, 1)]
        self.flag_E, \
        self.flag_F, \
        self.flag_H, \
        self.flag_I, \
        self.flag_N, \
        self.flag_Z, \
        self.flag_V, \
        self.flag_C = status_bits
        assert self.status_as_byte() == status

    def status_as_byte(self):
        return self.flag_C | \
            self.flag_V << 1 | \
            self.flag_Z << 2 | \
            self.flag_N << 3 | \
            self.flag_I << 4 | \
            self.flag_H << 5 | \
            self.flag_F << 6 | \
            self.flag_E << 7

    def get_register(self, addr):
        log.debug("get register value from %s" % hex(addr))
        if addr == 0x00: # 0000 - D - 16 bit concatenated reg.(A B)
            return self.accumulator_a + self.accumulator_b
        elif addr == 0x01: # 0001 - X - 16 bit index register
            return self.index_x
        elif addr == 0x02: # 0010 - Y - 16 bit index register
            return self.index_y
        elif addr == 0x03: # 0011 - U - 16 bit user-stack pointer
            return self.user_stack_pointer
        elif addr == 0x04: # 0100 - S - 16 bit system-stack pointer
            return self.stack_pointer
        elif addr == 0x05: # 0101 - PC - 16 bit program counter register
            return self.program_counter
        elif addr == 0x08: # 1000 - A - 8 bit accumulator
            return self.accumulator_a
        elif addr == 0x09: # 1001 - B - 8 bit accumulator
            return self.accumulator_b
        elif addr == 0x0a: # 1010 - CC - 8 bit condition code register as flags
            return self.status_as_byte()
        elif addr == 0x0b: # 1011 - DP - 8 bit direct page register
            return self.direct_page
        else:
            raise RuntimeError("Register %s doesn't exists!" % hex(addr))

    def set_register(self, addr, value):
        log.debug("set register %s to %s" % (hex(addr), hex(value)))
        if addr == 0x00: # 0000 - D - 16 bit concatenated reg.(A B)
            self.accumulator_a, self.accumulator_b = divmod(value, 256)
        elif addr == 0x01: # 0001 - X - 16 bit index register
            self.index_x = value
        elif addr == 0x02: # 0010 - Y - 16 bit index register
            self.index_y = value
        elif addr == 0x03: # 0011 - U - 16 bit user-stack pointer
            self.user_stack_pointer = value
        elif addr == 0x04: # 0100 - S - 16 bit system-stack pointer
            self.stack_pointer = value
        elif addr == 0x05: # 0101 - PC - 16 bit program counter register
            self.program_counter = value
        elif addr == 0x08: # 1000 - A - 8 bit accumulator
            self.accumulator_a = value
        elif addr == 0x09: # 1001 - B - 8 bit accumulator
            self.accumulator_b = value
        elif addr == 0x0a: # 1010 - CC - 8 bit condition code register as flags
            self.status_from_byte(value)
        elif addr == 0x0b: # 1011 - DP - 8 bit direct page register
            self.direct_page = value
        else:
            raise RuntimeError("Register %s doesn't exists!" % hex(addr))

    ####

    def reset(self):
        pc = self.read_word(self.cfg.RESET_VECTOR)
        log.debug("$%x CPU reset: read word from $%x set pc to %s" % (
            self.program_counter, self.cfg.RESET_VECTOR,
            self.cfg.mem_info.get_shortest(pc)
        ))
        self.program_counter = pc - 1

    def run(self, bus_port):
        global bus
        bus = socket.socket()
        bus.connect(("127.0.0.1", bus_port))

        assert self.cfg.bus != None

        last_op_code = None
        same_op_count = 0

#         while not self.quit:
#         for x in xrange(10):
        for x in xrange(100):
#         for x in xrange(1000):
            timeout = 0
            if not self.running:
                timeout = 1
            # Currently this handler blocks from the moment
            # a connection is accepted until the response
            # is sent. TODO: use an async HTTP server that
            # handles input data asynchronously.
            sockets = [self.control_server]
            rs, _, _ = select.select(sockets, [], [], timeout)
            for s in rs:
                if s is self.control_server:
                    self.control_server._handle_request_noblock()
                else:
                    pass

#             for count in xrange(10):
#             for count in xrange(100):
            for count in xrange(1000):
                if not self.running:
                    break

                op = self.read_pc_byte()
                try:
                    func = self.opcodes[op]
                except KeyError:
                    msg = "$%x *** UNKNOWN OP $%x" % (self.program_counter - 1, op)
                    log.error(msg)
                    sys.exit(msg)
                    break

                if op == last_op_code:
                    same_op_count += 1
                elif same_op_count == 0:
                    log.debug("$%x *** new op code: $%x (%s)" % (self.program_counter - 1, op, func.__name__))
                    last_op_code = op
                else:
                    log.debug("$%x *** last op code %s count: %s - new op code: $%x (%s)" % (
                        self.program_counter - 1, last_op_code, same_op_count, op, func.__name__
                    ))
                    last_op_code = op
                    same_op_count = 0

                # call op code method:
                func()

    def test_run(self, start, end):
        self.program_counter = start
        while True:
            if self.program_counter == end:
                break
            op = self.read_pc_byte()
            try:
                func = self.opcodes[op]
            except KeyError:
                print "UNKNOWN OP %s (program counter: %s)" % (
                    hex(op), hex(self.program_counter - 1)
                )
                break
            else:
                func()

    def illegal_op(self):
        self.program_counter -= 1
        op = self.read_pc_byte()
        raise RuntimeError("$%x Op code $%x is illegal!" % (
            self.program_counter - 1, op
        ))

    ####

    def get_pc(self, inc=1):
        pc = self.program_counter
        self.program_counter += inc
        return pc

    def read_byte(self, address):
        return self.memory.read_byte(self.cycles, address)

    def read_word(self, address):
        return self.memory.read_word(self.cycles, address)

    def read_pc_byte(self):
        return self.read_byte(self.get_pc())

    def read_pc_word(self):
        return self.read_word(self.get_pc(2))

    def write_byte(self, address, value):
        self.memory.write_byte(self.cycles, address, value)

    ####

    def push_byte(self, byte):
        self.write_byte(self.cfg.STACK_PAGE + self.stack_pointer, byte)
        self.stack_pointer = (self.stack_pointer - 1) % 0x100

    def pull_byte(self):
        self.stack_pointer = (self.stack_pointer + 1) % 0x100
        return self.read_byte(self.cfg.STACK_PAGE + self.stack_pointer)

    def push_word(self, word):
        hi, lo = divmod(word, 0x100)
        self.push_byte(hi)
        self.push_byte(lo)

    def pull_word(self):
        s = self.cfg.STACK_PAGE + self.stack_pointer + 1
        self.stack_pointer += 2
        return self.read_word(s)

    ####

    def update_nzvc(self, value):
        value = value % 0x100
        self.flag_N = 1 if (value < 0) else 0
        self.flag_Z = 1 if (value == 0) else 0

        # V - bit 1 - Overflow
#         if value == 0x989680: # == 10000000
#             self.flag_V = 1
        self.flag_V = 1 if (value > 127) | (value < -128) else 0 # ???

        # C - 1 if borrow, else 0
        self.flag_C = 1 if (value > 0xFF) else 0 # ???

        return value

    ####

    def AND(self, r, m):
        value = r & m
        self.flag_N = 1 if (value < 0) else 0
        self.flag_Z = 1 if (value == 0) else 0
        self.flag_V = 0
        return value

    ####

    def immediate_byte(self):
        value = self.read_pc_byte()
        log.debug("$%x addressing 'immediate byte' value: $%x \t| %s" % (
            self.program_counter, value, self.cfg.mem_info.get_shortest(self.program_counter)
        ))
        return value

    def immediate_word(self):
        value = self.read_pc_word()
        log.debug("$%x addressing 'immediate word' value: $%x \t| %s" % (
            self.program_counter, value, self.cfg.mem_info.get_shortest(self.program_counter)
        ))
        return value

    def direct(self):
        pass
    def base_page_direct(self, debug=False):
        post_byte = self.read_pc_byte()
        ea = self.direct_page << 8 | post_byte
        if debug:
            log.debug("$%x addressing 'base page direct' value: $%x (DP: $%x post byte: $%x) \t| %s" % (
                self.program_counter,
                ea, self.direct_page, post_byte,
                self.cfg.mem_info.get_shortest(self.program_counter)
            ))
        return ea

    def indexed(self):
        """
        +-------------------------------+--------------------------------------
        | Post-byte register bits       | Indexed addressing modes
        | 7 | 6 | 5 | 4 | 3 | 2 | 1 | 0 |
        +-------------------------------+--------------------------------------
        | 0 | R | R | d | d | d | d | d | EA = ,R + 5-bit offset
        | 1 | R | R | 0 | 0 | 0 | 0 | 0 | $0 - ,R++
        | 1 | R | R | i | 0 | 0 | 0 | 1 | $1 - ,-R
        | 1 | R | R | 0 | 0 | 0 | 1 | 1 | $3 - ,--R
        | 1 | R | R | i | 0 | 1 | 0 | 0 | $4 - EA = ,R + 0 offset
        | 1 | R | R | i | 0 | 1 | 0 | 1 | $5 - EA = ,R + ACCB offset
        | 1 | R | R | i | 0 | 1 | 1 | 0 | $6 - EA = ,R + ACCA offset
        | 1 | R | R | i | 1 | 0 | 0 | 0 | $8 - EA = ,R + 8-bit offset
        | 1 | R | R | i | 1 | 0 | 0 | 1 | $9 - EA = ,R + 16-bit offset
        | 1 | R | R | i | 1 | 0 | 1 | 1 | $b - EA = ,R + D offset
        | 1 | x | x | i | 1 | 1 | 0 | 0 | $c - EA = ,PC + 8-bit offset
        | 1 | x | x | i | 1 | 1 | 0 | 1 | $d - EA = ,PC + 16-bit offset
        | 1 | R | R | i | 1 | 1 | 1 | 1 | $f - EA = (, Address)
        +-------------------------------+--------------------------------------
        |   : |   | : | :
        |   : |   | : V :
        |   : |   | : i | Indirect fields (or sign bit when bit 7 = 0)
        |   : |   | : 0 | Direct
        |   : |   | : 1 | Indirect
        |   : V   V :
        |   | R | R | Register fields:
        |   | 0 | 0 | $0 = X
        |   | 0 | 1 | $1 = Y
        |   | 1 | 0 | $2 = U
        |   | 1 | 1 | $3 = S
        +-------------------------------+--------------------------------------
        """
        postbyte = self.read_pc_byte()
        log.debug("$%x indexed addressing mode: postbyte: $%x == %s" % (
            self.program_counter, postbyte, byte2bit_string(postbyte)
        ))

        rr = (postbyte >> 5) & 3
        if rr == 0x00:
            # X - 16 bit index register
            register_value = self.index_x
            reg_attr_name = "index_x"
        elif rr == 0x01:
            # Y - 16 bit index register
            register_value = self.index_y
            reg_attr_name = "index_y"
        elif rr == 0x02:
            # U - 16 bit user-stack pointer
            register_value = self.user_stack_pointer
            reg_attr_name = "user_stack_pointer"
        elif rr == 0x03:
            # S - 16 bit system-stack pointer
            register_value = self.stack_pointer
            reg_attr_name = "stack_pointer"
        else:
            raise RuntimeError("Register $%x doesn't exists! (postbyte: $%x)" % (rr, postbyte))

        if (postbyte & 0x80) == 0: # bit 7 == 0
            # EA = ,R + 5-bit offset
            return register_value + signed5(postbyte) # FIXME: cutout only the 5bits from post byte?

        if postbyte == 0x8f or postbyte == 0x90: # 0x8f == 10001111 | 0x90 == 10010000
            ea = register_value
            self.cycles += 1
        elif postbyte == 0xaf or postbyte == 0xb0: # 0xaf=10101111 | 0xb0=10110000
            ea = self.read_pc_word()
            ea = ea + register_value
            self.cycles += 1
        elif postbyte == 0xcf or postbyte == 0xd0: # 0xcf=11001111 | 0xd0=11010000
            ea = register_value
            setattr(self, reg_attr_name, register_value + 2) # FIXME
            self.cycles += 2
        elif postbyte == 0xef or postbyte == 0xf0: # 0xef=11101111 | 0xf0=11110000
            setattr(self, reg_attr_name, register_value - 2) # FIXME
            ea = register_value
            self.cycles += 2
        else:
            addr_mode = postbyte & 0x0f
            self.cycles += 1
            if addr_mode == 0x0: # 0000 0x0
                ea = register_value + 1
            elif addr_mode == 0x1: # 0001 0x1
                ea = register_value + 2
            elif addr_mode == 0x2: # 0010 0x2
                ea = register_value - 1
            elif addr_mode == 0x3: # 0011 0x3
                ea = register_value - 2
                self.cycles += 1
            elif addr_mode == 0x4: # 0100 0x4
                ea = register_value
            elif addr_mode == 0x5: # 0101 0x5
                ea = register_value + signed8(self.accumulator_b)
            elif addr_mode == 0x6: # 0110 0x6
                ea = register_value + signed8(self.accumulator_a)
            elif addr_mode == 0x7: # 0111 0x7
                ea = register_value + signed8(self.accumulator_e)
            elif addr_mode == 0x8: # 1000 0x8
                offset = self.read_pc_byte()
                ea = signed8(offset) + register_value
            elif addr_mode == 0x9: # 1001 0x9
                offset = self.read_pc_word()
                ea = register_value + offset
                self.cycles += 1
            elif addr_mode == 0xa: # 1010 0xa
                ea = register_value + signed8(self.accumulator_f)
            elif addr_mode == 0xb: # 1011 0xb
                ea = register_value + signed8(self.accumulator_d)
            elif addr_mode == 0xc: # 1100 0xc
                offset = self.read_pc_byte()
                ea = signed8(offset) + self.program_counter
            elif addr_mode == 0xd: # 1101 0xd
                offset = self.read_pc_word()
                ea = signed8(offset) + self.program_counter
            elif addr_mode == 0xe: # 1110 0xe
                # W - 16 bit concatenated reg. (E + F)
                ea = register_value + signed8(self.accumulator_e + self.accumulator_f)
                self.cycles += 1
            elif addr_mode == 0xf: # 1111 0xf
                ea = self.read_pc_word()
            else:
                raise RuntimeError("unknown addressing mode: $%x" % addr_mode)

        if postbyte & 0x10:
            # bit 4 is 1 -> Indirect
            tmp_ea = self.read_pc_byte()
            tmp_ea = tmp_ea << 8
            ea = tmp_ea | self.read_byte(ea + 1)

        log.debug("$%x indexed addressing mode ea=$%x" % (
            self.program_counter, ea
        ))
        return ea


    def extended(self):
        """
        extended indirect addressing mode takes a 2-byte value from post-bytes
        """
        value = self.read_pc_word()
        log.debug("$%x addressing 'extended indirect' value: $%x \t| %s" % (
            self.program_counter, value, self.cfg.mem_info.get_shortest(self.program_counter)
        ))
        return value

    def inherent(self):
        pass

    #### Op methods in alphabetical order:

    @opcode(0xbb)
    def ADDA_extended(self):
        """
        ADD to accumulator A
        A = A + M
        """
        self.cycles += 5
        value = self.extended()
        log.debug("$%x ADDA extended: Add %s to accu A: %s" % (
            self.program_counter, hex(value), hex(self.accumulator_a)
        ))
        value = self.update_nzvc(value)
        self.accumulator_a += value

    @opcode(0x84)
    def ANDA_immediate(self):
        """
        AND with accumulator A
        Number of Program Bytes: 2
        """
        self.cycles += 2 # Number of MPU Cycles
        value = self.immediate_byte()
        result = self.AND(self.accumulator_a, value)
        self.cfg.mem_info(self.program_counter,
            "$%x ANDA immediate set accu A to $%x ($%x & $%x) |" % (
                self.program_counter, result, self.accumulator_a, value
        ))
        self.accumulator_a = result

    @opcode(0x6f)
    def CLR_indexed(self):
        """
        CLeaR
        Number of Program Bytes: 2+
        """
        self.cycles += 6
        addr = self.indexed()
        self.write_byte(addr, 0x0)
        self.flag_N = 0
        self.flag_Z = 1
        self.flag_V = 0
        self.flag_C = 0

    @opcode(0xbc)
    def CMPX_extended(self):
        """
        CoMPare with X index
        """
        self.cycles += 7
        value = self.extended()
        log.debug("$%x CMPX extended - set index X to $%x ($%x - $%s) |" % (
            self.program_counter,
        ))

        result = self.index_x - value

        self.cfg.mem_info(self.program_counter,
            "$%x CMPX extended - $%x (index X) - $%x (post word) = $%x | update NZVC with $%x |" % (
                self.program_counter, self.index_x, value, result, result
        ))

#         self.flag_C = 1 if (result >= 0) else 0
        self.update_nzvc(result)
#         log.debug("%s - 0xbc CMPX extended: %s - %s = %s (Set C to %s)" % (
#             self.program_counter, hex(self.index_x), hex(value), hex(result), self.flag_C
#         ))

    @opcode(0x03)
    def COM_direct(self):
        """
        COMplement memory
        Number of Program Bytes: 2
        """
        self.cycles += 6
        value = self.base_page_direct(debug=True)
        value = value ^ -1
        self.flag_N = 1 if (value < 0) else 0
        self.flag_Z = 1 if (value == 0) else 0
        self.flag_V = 0
        self.flag_C = 1

    @opcode(0x7e)
    def JMP_extended(self):
        """
        Unconditional JuMP
        Number of Program Bytes: 3
        Calculates an effective address (ea), and stores it in the program counter.
        Addressing Mode: extended
        """
        self.cycles += 3
        addr = self.extended()
        self.program_counter = addr
#         log.debug()
        self.cfg.mem_info(addr, "$%x JMP extended to" % self.program_counter)

    @opcode(0xbd)
    def JSR_extended(self):
        """
        Jump to SubRoutine
        Addressing Mode: extended
        """
        self.cycles += 8
        addr = self.extended()
        self.push_word(self.program_counter - 1)
        self.program_counter = addr
        log.debug("$%x JSR extended: push %s to stack and jump to %s" % (
            self.program_counter, hex(self.program_counter - 1), hex(addr)
        ))

    @opcode(0xcc)
    def LDD_immediate(self):
        """
        LoaD register D
        Number of Program Bytes: 3
        """
        self.cycles += 3

        # XXX
        value1 = self.read_pc_byte()
        value2 = self.read_pc_byte()
        self.accumulator_a = value1
        self.accumulator_b = value2

        self.cfg.mem_info(self.program_counter,
            "$%x LDD immediate $%x and $%x to accu A & B" % (
                self.program_counter, value1, value2
        ))

    @opcode(0x8e)
    def LDX_immediate(self):
        """
        LoaD index X
        Number of Program Bytes: 3
        """
        self.cycles += 3 # Number of MPU Cycles

        value = self.immediate_word()
        self.index_x = value

        self.cfg.mem_info(self.program_counter,
            "$%x LDX immediate: set $%x to index X |" % (
                self.program_counter, value
        ))

    @opcode(0x30)
    def LEAX_indexed(self):
        """
        Load Effective Address from index X
        Number of Program Bytes: 4+
        """
        self.cycles += 2 # Number of MPU Cycles
        ea = self.indexed()
        self.index_x = ea
        self.cfg.mem_info(self.program_counter,
            "$%x LEAX indexed: set $%x to index X |" % (
                self.program_counter, ea
        ))

    @opcode(0x00)
    def NEG_direct(self):
        """
        Negate (Twos Complement) a Byte in Memory
        Number of Program Bytes: 2
        Addressing Mode: direct
        """
        self.cycles += 6
        value = self.base_page_direct()
#         log.debug("%s 0x00 NEG direct %s" % (self.program_counter, hex(value)))

        value = -value
        self.update_nzvc(value)

    @opcode(0xa7)
    def STA_indexed(self):
        """
        STore register A
        Number of Program Bytes: 2+
        """
        self.cycles += 4
        offset = self.immediate_word()
        addr = self.accumulator_a + offset
        value = self.accumulator_a

        self.cfg.mem_info(self.program_counter,
            "$%x STA indexed - store $%x with offset:$%x to $%x |" % (
                self.program_counter, value, offset, addr
        ))

        self.write_byte(addr, value)

    @opcode(0x1f)
    def TFR(self):
        """
        TransFeR Register to Register
        Number of Program Bytes: 2
        Copies data in register r1 to another register r2 of the same size.
        Addressing Mode: immediate register numbers
        """
        self.cycles += 7
        post_byte = self.immediate_byte()
        high, low = divmod(post_byte, 16)
        log.debug("$%x TFR: post byte: %s high: %s low: %s" % (
            self.program_counter, hex(post_byte), hex(high), hex(low)
        ))
        # TODO: check if source and dest has the same size
        source = self.get_register(high)
        self.set_register(low, source)


if __name__ == "__main__":
    cli = DragonPyCLI()
    cfg = cli.get_cfg()

    if cfg.bus is None:
        import subprocess
        subprocess.Popen([sys.executable,
            "DragonPy_CLI.py",
            "--verbosity=5",
#             "--verbosity=50",
        ]).wait()
        sys.exit(0)
        print "DragonPy cpu core"
        print "Run DragonPy_CLI.py instead"
        sys.exit(0)

    log.debug("Use bus port: %s" % repr(cfg.bus))

    mem = Memory(cfg)
    cpu = CPU(cfg, mem)
    cpu.run(cfg.bus)
