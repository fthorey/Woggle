#! /usr/bin/env python
# encoding: utf-8

import os, sys, shutil, subprocess, termios, serial

from waflib import Utils, extras, Logs
from waflib.Context import Context
from waflib.Build import BuildContext

from wtools import arm_gcc, arm_as
from wtools import interpreter

sys.path += ['wtools']

top = '.'
out = 'wbuild'

APPNAME='swiftler'

def options(opt):
    # Set C cross compiler
    from waflib.Tools.compiler_c import c_compiler
    c_compiler['linux'] = ['arm_gcc']

    # Load compiler and asm options
    opt.load('compiler_c arm_as')

def configure(conf):
    # Load compiler and asm configuration
    conf.load('compiler_c arm_as')

    # Load objcopy
    conf.find_program(['arm-none-eabi-objcopy', 'arm-none-linux-gnueabi-objcopy'], var='OBJ_CPY')

    # Flags
    genflags = ['-std=c99', '-Wall', '-Werror', '-fasm', '-fdata-sections', '-ffunction-sections']
    archflags = ['-mcpu=cortex-m3', '-mthumb']
    optflags =  ['-g', '-Os', '-fmerge-all-constants', '-fsee']

    conf.env['CFLAGS'] =  genflags + archflags + optflags
    conf.env['ASFLAGS'] = archflags

    ldscript = conf.path.find_resource('stm32/stm32f10x_flash_md.ld')
    conf.env['LINKFLAGS'] = ['-T%s' % ldscript.abspath(),
                             '-Wl,-Map=%s.map' % APPNAME,
                             '-Wl,--gc-sections'] + archflags
    # Defines
    conf.env['DEFINES'] = ['GCC_ARMCM3', 'STM32F10X_MD']

def build(bld):
    # STM32 DIR
    stm32_dir = bld.path.find_dir('stm32/STM32_USB-FS-Device_Lib_V3.1.0/Libraries')
    stm32_core_dir = stm32_dir.find_dir('CMSIS/Core/CM3')
    stm32_startup_dir = stm32_core_dir.find_dir('startup/gcc')
    stm32_stddriver_dir = stm32_dir.find_dir('STM32F10x_StdPeriph_Driver')
    stm32_stddriver_srcdir = stm32_stddriver_dir.find_dir('src')
    stm32_stddriver_incdir = stm32_stddriver_dir.find_dir('inc')
    stm32_usb_dir = stm32_dir.find_dir('STM32_USB-FS-Device_Driver')
    stm32_usb_srcdir = stm32_usb_dir.find_dir('src')
    stm32_usb_incdir = stm32_usb_dir.find_dir('inc')
    # FreeRTOS dir
    freertos_dir = bld.path.find_dir('freertos/Source')
    freertos_incdir = freertos_dir.find_dir('include')
    freertos_platdir = freertos_dir.find_dir('portable/GCC/ARM_CM3')
    freertos_memdir = freertos_dir.find_dir('portable/MemMang')
    # project dir
    src_dir = bld.path.find_dir('src')
    libglobal_dir = src_dir.find_dir('libglobal')
    libperiph_dir = src_dir.find_dir('libperiph')

    # Build libstm32
    bld(features   = 'c cstlib',
        source     = stm32_stddriver_srcdir.ant_glob(['stm32f10x_flash.c',
                                                      'stm32f10x_gpio.c',
                                                      'stm32f10x_rcc.c',
                                                      'stm32f10x_usart.c',
                                                      'stm32f10x_tim.c',
                                                      'stm32f10x_exti.c',
                                                      'stm32f10x_adc.c',
                                                      'stm32f10x_dma.c',
                                                      'stm32f10x_i2c.c',
                                                      'misc.c',
                                                      ]),
        target     = 'stm32',
        cflags     = ['-include', 'assert_param.h'],
        includes   = [stm32_stddriver_incdir.abspath(),
                      stm32_core_dir.abspath(),
                      libglobal_dir.abspath(),
                      ],
        )

    # Build libperiph
    bld(features   = 'c cstlib',
        target     = 'periph',
        cflags     = ['-include', 'libglobal/assert_param.h'],
        source     = libperiph_dir.ant_glob(['*.c']),
        includes   = [stm32_stddriver_incdir.abspath(),
                      stm32_core_dir.abspath(),
                      freertos_incdir.abspath(),
                      src_dir.abspath(),
                      ],
        )

    # Build libglobal
    bld(features   = 'c cstlib',
        target     = 'global',
        source     = libglobal_dir.ant_glob(['*.c']),
        includes   = [stm32_stddriver_incdir.abspath(),
                      stm32_core_dir.abspath(),
                      freertos_incdir.abspath(),
                      src_dir.abspath(),
                      ],
        )

    project_sources = []
    project_sources += stm32_startup_dir.ant_glob(['startup_stm32f10x_md.s'])
    project_sources += src_dir.ant_glob(['main.c'])
    project_sources += freertos_dir.ant_glob(['queue.c', 'tasks.c', 'list.c', 'semphr.c'])
    project_sources += freertos_memdir.ant_glob(['heap_1.c'])
    project_sources += freertos_platdir.ant_glob(['port.c'])

    # Build project
    bld(features   = 'asm c cprogram',
        source     = project_sources,
        target     = '%s.elf' % APPNAME,
        use        = ['periph', 'global', 'stm32'],
        includes   = [stm32_stddriver_incdir.abspath(),
                      stm32_core_dir.abspath(),
                      freertos_incdir.abspath(),
                      src_dir.abspath(),
                      ],
        )

    # Create flash image
    bld(rule='${OBJ_CPY} -O binary ${SRC} ${TGT}', source='%s.elf' % APPNAME, target='flash.bin')

    # Copy flash configuration
    bld(rule='cp ${SRC} ${TGT}', source='flash/flash.cfg', target='flash.cfg')

def upload(upl):
    # Kill previous openocd instances
    os.system("killall -q openocd")
    # Flash into Olimexino
    openocd_cmd = ['openocd']
    openocd_cmd += ['-s']
    openocd_cmd += ['%s' % upl.path.find_dir('./wbuild').abspath()]
    openocd_cmd += ['-f']
    openocd_cmd += ['flash.cfg']
    subprocess.call(openocd_cmd)

class Upload(BuildContext):
    cmd = 'upload'
    fun = 'upload'


def flash(ctx):
    from waflib import Options
    Options.commands += ['build', 'upload', 'monitor']

def all(ctx):
    from waflib import Options
    Options.commands += ['distclean', 'configure', 'build', 'upload', 'monitor']

def monitor(ctx):
	import serial, select
        term = None
        for i in xrange(0, 8) :
            try :
                port = '/dev/ttyUSB' + str(i)
                with interpreter.console():
                    term = interpreter.Term(serial.Serial(port, 115200, timeout=1), APPNAME)
                    term.ser.write('\r')
                    interpreter.checkPrompt(term, ['swiftler', 'HiZ'])
                Logs.pprint('YELLOW', "Opened %s" % port)
                break
            except serial.SerialException as e:
                term = None
                continue
            except interpreter.TimeoutException as e:
                term = None
                continue

        if not term :
            ctx.fatal("Couldn't open a serial port")

        Logs.pprint('GREEN', '%s Monitor :' % APPNAME)
        with interpreter.console():
            term.ser.flushInput()
            term.ser.write('\r')
            term.run()
