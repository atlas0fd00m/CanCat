ARDUINO_HOME=$(HOME)/.arduino15/
ARDUINO_LIB_HOME=$(HOME)/Arduino/libraries/
BUILDER_PATH=/opt/arduino-builder/
SERIAL_PORT=/dev/ttyACM0

m2: BOARD := macchina:sam:m2
m2: build/M2_CAN_haz_bus.ino.bin

citm-m2: BOARD := macchina:sam:m2
citm-m2: build/CAN_in_the_middle.ino.bin

due: BOARD := arduino:sam:due
due: build/M2_CAN_haz_bus.ino.bin

citm-due: BOARD := arduino:sam:due
citm-due: build/CAN_in_the_middle.ino.bin

arduino: BOARD := arduino:avr:uno
arduino: build/CAN_haz_bus.ino.bin

build/%.ino.bin: M2_CAN_haz_bus/%.ino $(wildcard M2_CAN_haz_bus/*.cpp) $(wildcard M2_CAN_haz_bus/*.h)
	mkdir -p build/
	$(BUILDER_PATH)arduino-builder -build-path $(PWD)/build -tools $(ARDUINO_HOME)packages/arduino/tools/ -tools $(BUILDER_PATH)/tools-builder -tools $(BUILDER_PATH)/tools -hardware $(BUILDER_PATH)hardware/ -hardware $(ARDUINO_HOME)packages/ -libraries $(ARDUINO_LIB_HOME) -fqbn $(BOARD) $<

build/%.ino.bin: CAN_in_the_middle/%.ino $(wildcard CAN_in_the_middle/*.cpp) $(wildcard CAN_in_the_middle/*.h)
	mkdir -p build/
	$(BUILDER_PATH)arduino-builder -build-path $(PWD)/build -tools $(ARDUINO_HOME)packages/arduino/tools/ -tools $(BUILDER_PATH)/tools-builder -tools $(BUILDER_PATH)/tools -hardware $(BUILDER_PATH)hardware/ -hardware $(ARDUINO_HOME)packages/ -libraries $(ARDUINO_LIB_HOME) -fqbn $(BOARD) $<

build/%.ino.bin: CAN_haz_bus/%.ino $(wildcard CAN_haz_bus/*.cpp) $(wildcard CAN_haz_bus/*.h)
	mkdir -p build/
	$(BUILDER_PATH)arduino-builder -build-path $(PWD)/build -tools $(ARDUINO_HOME)packages/arduino/tools/ -tools $(BUILDER_PATH)/tools-builder -tools $(BUILDER_PATH)/tools -hardware $(BUILDER_PATH)hardware/ -hardware $(ARDUINO_HOME)packages/ -libraries $(ARDUINO_LIB_HOME) -fqbn $(BOARD) $<

bootloader:
	stty -F $(SERIAL_PORT) 1200 cs8 cread clocal
	sleep 1

flash:
ifneq ("$(wildcard build/M2_CAN_haz_bus.ino.bin)", "")
	cp build/M2_CAN_haz_bus.ino.bin build/firmware.ino.bin
else ifneq ("$(wildcard build/CAN_in_the_middle.ino.bin)", "")
	cp build/CAN_in_the_middle.ino.bin build/firmware.ino.bin
else ifneq ("$(wildcard build/CAN_haz_bus.ino.bin)", "")
	cp build/CAN_haz_bus.ino.bin build/firmware.ino.bin
endif
	$(ARDUINO_HOME)packages/arduino/tools/bossac/1.6.1-arduino/bossac -e -w -v -b build/firmware.ino.bin

clean:
	rm -rf build/

