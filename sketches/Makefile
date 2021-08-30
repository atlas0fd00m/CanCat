PORT ?= /dev/ttyACM0

.PHONY: m2 citm2-m2 due citm-due arduino clean

m2: BOARD := macchina:sam:m2
m2: M2_CAN_haz_bus/M2_CAN_haz_bus.ino $(wildcard M2_CAN_haz_bus/*.cpp) $(wildcard M2_CAN_haz_bus/*.h)
	arduino-cli compile --fqbn $(BOARD) M2_CAN_haz_bus
	arduino-cli upload -p $(PORT) --fqbn $(BOARD) M2_CAN_haz_bus

due: BOARD := arduino:sam:arduino_due_x
due: M2_CAN_haz_bus/M2_CAN_haz_bus.ino $(wildcard M2_CAN_haz_bus/*.cpp) $(wildcard M2_CAN_haz_bus/*.h)
	arduino-cli compile --fqbn $(BOARD) M2_CAN_haz_bus
	arduino-cli upload -p $(PORT) --fqbn $(BOARD) M2_CAN_haz_bus

citm-m2: BOARD := macchina:sam:m2
citm-m2: CAN_in_the_middle/CAN_in_the_middle.ino $(wildcard CAN_in_the_middle/*.cpp) $(wildcard CAN_in_the_middle/*.h)
	arduino-cli compile --fqbn $(BOARD) CAN_in_the_middle
	arduino-cli upload -p $(PORT) --fqbn $(BOARD) CAN_in_the_middle

citm-due: BOARD := arduino:sam:arduino_due_x
citm-due: CAN_in_the_middle/CAN_in_the_middle.ino $(wildcard CAN_in_the_middle/*.cpp) $(wildcard CAN_in_the_middle/*.h)
	arduino-cli compile --fqbn $(BOARD) CAN_in_the_middle
	arduino-cli upload -p $(PORT) --fqbn $(BOARD) CAN_in_the_middle

arduino: BOARD := arduino:avr:uno
arduino: CAN_haz_bus/CAN_haz_bus.ino $(wildcard CAN_haz_bus/*.cpp) $(wildcard CAN_haz_bus/*.h)
	arduino-cli compile --fqbn $(BOARD) CAN_haz_bus
	arduino-cli upload -p $(PORT) --fqbn $(BOARD) CAN_haz_bus

clean:
	rm -f M2_CAN_haz_bus/*.bin M2_CAN_haz_bus/*.elf
	rm -f CAN_in_the_middle/*.bin CAN_in_the_middle/*.elf
	rm -f CAN_haz_bus/*.bin CAN_haz_bus/*.elf

