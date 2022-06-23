'''
The Envi framework allows architecture abstraction through the use of the
ArchitectureModule, Opcode, Operand, and Emulator objects.
'''

import types
import struct
import logging
import platform
import contextlib

from cancat.envi.exc import *

logger = logging.getLogger(__name__)

# TODO: move into const.py
# Parsed Opcode Formats
ARCH_DEFAULT     = 0 << 16   # arch 0 is whatever the mem object has as default
ARCH_I386        = 1 << 16
ARCH_AMD64       = 2 << 16
ARCH_ARMV7       = 3 << 16
ARCH_THUMB16     = 4 << 16
ARCH_THUMB       = 5 << 16
ARCH_MSP430      = 6 << 16
ARCH_H8          = 7 << 16
ARCH_MASK        = 0xffff0000   # Masked into IF_FOO and BR_FOO values

arch_names = {
    ARCH_DEFAULT:   'default',
    ARCH_I386:      'i386',
    ARCH_AMD64:     'amd64',
    ARCH_ARMV7:     'arm',
    ARCH_THUMB16:   'thumb16',
    ARCH_THUMB:     'thumb',
    ARCH_MSP430:    'msp430',
    ARCH_H8:        'h8',
}

arch_by_name = {
    'default':  ARCH_DEFAULT,
    'i386':     ARCH_I386,
    'amd64':    ARCH_AMD64,
    'arm':      ARCH_ARMV7,
    'armv6l':   ARCH_ARMV7,
    'armv7l':   ARCH_ARMV7,
    'thumb16':  ARCH_THUMB16,
    'thumb':    ARCH_THUMB,
    'thumb2':   ARCH_THUMB,
    'msp430':   ARCH_MSP430,
    'h8':       ARCH_H8,
}

# Instruction flags (The first 8 bits are reserved for arch independant use)
IF_NOFALL = 0x01  # Set if this instruction does *not* fall through
IF_PRIV   = 0x02  # Set if this is a "privileged mode" instruction
IF_CALL   = 0x04  # Set if this instruction branches to a procedure
IF_BRANCH = 0x08  # Set if this instruction branches
IF_RET    = 0x10  # Set if this instruction terminates a procedure
IF_COND   = 0x20  # Set if this instruction is conditional
IF_REPEAT = 0x40  # set if this instruction repeats (including 0 times)

IF_BRANCH_COND = IF_COND | IF_BRANCH

# Branch flags (flags returned by the getBranches() method on an opcode)
BR_PROC  = 1<<0  # The branch target is a procedure (call <foo>)
BR_COND  = 1<<1  # The branch target is conditional (jz <foo>)
BR_DEREF = 1<<2  # the branch target is *dereferenced* into PC (call [0x41414141])
BR_TABLE = 1<<3  # The branch target is the base of a pointer array of jmp/call slots
BR_FALL  = 1<<4  # The branch is a "fall through" to the next instruction
BR_ARCH  = 1<<5  # The branch *switches opcode formats*. ( ARCH_FOO in high bits )

import cancat.envi.bits as e_bits

