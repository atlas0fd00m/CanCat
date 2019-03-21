# CanCat
CanCat is an open source  multi-purpose tool for interacting and experimenting with Controller Area Networks (CAN), such as those that are often used in cars, building automation, etc. 

## Description

CanCat has two main parts:  
1) Firmware for a compatible CAN-transceiver,  
2) Python client to talk to the tool,  

The currently supported CAN-transceiver combinations:
* Arduino with SeeedStudio's CANBUS Shield
* Arduino DUE with Togglebit.net's CAN shield
* [Macchina M2 (Under-the-Hood)](https://www.macchina.cc/catalog) 
* [Macchina M2 (Under-the-Dash)](https://www.macchina.cc/catalog)

The goals of CanCat are to provide:
* a way to capture and transmit messages on an arbitrary CAN bus (whatever the speed, as supported by hardware)
* an architecture for analyzing and identifying messages on a CAN bus
* a manner for data to be shared (Ford sends different messages from GM, Saab, Toyota, Honda, Hyundai, Kia, etc.) (either in the form of lookup tables or in the form of accessor codes.)



## Software
### Required:
* CANBUS_Shield from SeeedStudio (for Firmware compilation)  
    https://github.com/Seeed-Studio/CAN_BUS_Shield

* Python 2.7

* vstructs From the Vivisect framework in the Python Path:  
    (required for J1939 module)  
    https://github.com/vivisect/vivisect


### Recommended:
* ipython



## Installation
1) Install pyserial:
```
$ pip install --user pyserial
```

2) (OPTIONAL) Install ipython *(NOTE): ipython is required for interactive use.)*
```
$ pip install --user ipython
```

3) Install the [Arduino IDE](https://www.arduino.cc/en/main/software) on your computer.  

4) (OPTIONAL) If you are using a [Macchina M2](https://www.macchina.cc/) follow the [getting started guide](http://docs.macchina.cc/m2/getting-started/arduino.html) for the M2 to install the M2 hardware definitions in the Arduino tool.

5) (OPTIONAL) If you are on a Linux system, you may choose to install the [arduino-builder](https://github.com/arduino/arduino-builder) for your platform. The arduino-builder tool can be used to compile and flash your CAN device without opening the Arudino IDE. 

6) Clone CanCat and build the desired firmware. If not using the arduino-builder tool, use the Arduino IDE as normal to build and flash the sketch onto your target device. 

```
$ git clone https://github.com/atlas0fd00m/CanCat
$ cd CanCat/sketches
$ make m2
$ make bootloader
$ make flash
```

7) Unplug and replug in the USB connector to your CAN device (to remove it from bootloader mode)

8) Start CanCat and do a connectivity check.  

    `c.ping()` confirms that the CanCat python script is communicating properly with the CAN device.  
    `c.getCanMsgCount()` shows that CAN messages are being received by CanCat.

```
$ cd CanCat
$ ./CanCat.py -p /dev/ttyACM0 

In [1]: c.ping()
Out[1]: (1521577490.792667, 'ABCDEFGHIJKL')

In [2]: c.getCanMsgCount()
Out[2]: 1900

In [3]: c.getCanMsgCount()
Out[3]: 2127

In [4]: 
```



## Getting Started:
Once you have the required software installed and your device is flashed, you can begin to use CanCat. Currently, we use CanCat with ipython to interact with the CAN bus and do analysis.

CanCat is currently centered around the class CanInterface (or some subclass of it, like FordInterface, GMInterface, etc.)

### Connect to the device (old way):

```python
>>> import cancat

>>> CANalysis = cancat.CanInterface('/dev/ttyACM0', 115200) # your device may vary

>>> CANalysis.ping()
```

Set the can bus interface baud rate (500kbps is most common, others are often slower, depending on your car):

```python
>>> CANalysis.setCanBaud(cancat.CAN_125KBPS)    # medium speed CAN baudrate for Fords
```

Once you connect to the device and set the device, you will automatically capture any messages the CanCat device sees on the CAN bus it is attached to. It will store these messages for analysis.

Save your analysis/capture session periodically. *(NOTE: CanCat will only save when you tell it to save.)*

```python
>>> CANalysis.saveSessionToFile('filename_for_this_session')
```

Once you save for the first time, the file name will be cached so you can simply save it again to the same file by typing:

```python
>>> CANalysis.saveSessionToFile()
```

If you need help, use the help command:

```python
>>> help(cancat)
```

### Connect to the device(new way [Linux]):

```bash
$ ./CanCat.py -h

$ ./CanCat.py -p /dev/ttyACM0  # if CanCat device is /dev/ttyACM0

$ ./CanCat.py -f filename_of_previous_capture  # no CanCat device required
```

```
'CanCat, the greatest thing since J2534!'

Research Mode: enjoy the raw power of CanCat

currently your environment has an object called "c" for CanCat.  this is how 
you interact with the CanCat tool:
    >>> c.ping()
    >>> c.placeBookmark('')
    >>> c.snapshotCanMsgs()
    >>> c.printSessionStats()
    >>> c.printCanMsgs()
    >>> c.printCanSessions()
    >>> c.CANxmit('message', )
    >>> c.CANreplay()
    >>> c.saveSessionToFile('file_to_save_session_to')
    >>> help(c)
```

*(Note: The following two are used interchangeably in our notes:)*
(`>>>` is the default interactive python prompt.)
(`In [#]:` is the ipython prompt)

See if the CanCat is communicating correctly with your computer (only if you have a device connected).

```python
In [1]: c.ping()
```

Set the can bus interface baud rate (500kbps is most common, others are often slower, depending on your car):

```python
In [2]: c.setCanBaud(cancat.CAN_125KBPS)  # medium speed CAN baudrate for Fords
```

Once you connect to the device and set the device, you will automatically capture any messages the CanCat device sees on the CAN bus it is attached to. It will store these messages for analysis.

Save your analysis/capture session periodically. (CanCat only saves when when you tell it to).

```python
In [3]: c.saveSessionToFile('filename_for_this_session')
```

Once you save it once, the name will be cached so you can simply save it again to the same file by typing:

```python
In [4]: c.saveSessionToFile()
```

Other than that, "help" is your friend. :)

```python
In [5]: help(cancat)
```

or tab-completion

```python
In [6]: c.<PRESS_TAB_KEY>
c.CANrecv
c.genCanMsgs
c.ping
c.recv
c.saveSessionToFile
c.CANreplay
c.getArbitrationIds
c.placeCanBookmark
c.recvall
c.setCanBaud
c.CANsniff
c.getBookmarkFromMsgIndex
c.port
c.register_handler
c.setCanBookmarkComment
c.CANxmit
c.getCanMsgCount
c.printAsciiStrings
c.remove_handler
c.setCanBookmarkCommentByMsgIndex
c.bookmark_info
c.getMsgIndexFromBookmark
c.printBookmarks
c.reprBookmark
c.setCanBookmarkName
c.bookmarks
c.getSessionStats
c.printCanMsgs
c.reprBookmarks
c.setCanBookmarkNameByMsgIndex
c.clearCanMsgs
c.getSessionStatsByBookmark
c.printCanMsgsByBookmark
c.reprCanMsgs
c.snapshotCanMessages
c.comments
c.loadFromFile
c.printCanSessions
c.reprCanMsgsByBookmark
c.verbose
c.filterCanMsgs
c.log
c.printSessionStats
c.restoreSession
c.filterCanMsgsByBookmark
c.name
c.printSessionStatsByBookmark
c.saveSession
```



## CAN-in-the-Middle
CAN-in-the-Middle is another way to utilize your CanCat. It requires two CAN shields 
on one arduino. One of the CAN shields needs to be modified so that the CS pin of the 
MCP2515 CAN controller is on D10, rather than D9. This is accomplished by cutting a 
trace on the CAN shield PCB and bridging (solder bridge or 0-ohm resistor) the pads
for CS and D10. Instructions are also on the seeedstudio Wiki, although their board 
differed slightly from mine, mostly in that the pads are on the bottom of the board 
on mine and on the top of the board in their example.

Once you have a properly modified CAN Bus shield, you'll be able to isolate components
connected to the CAN bus to see which messages a specific device is sending, without
changing the conditions by fully removing it from the CAN Bus. This can be very helpful for 
certain reverse engineering tasks.

Flash the CAN_in_the_middle firmware to the Arduino. Hook the CAN wires up so that the 
device you are trying to isolate is connected to the modified CAN shield that uses D10
for CS, and the vehicle CAN bus (with the rest of the devices) is connected to the 
unmodified CAN shield. These are referred to as the Isolation network (ISO)
and the Vehicle network (VEH) respectively.

Start CAN_in_the_middle with the following command:

`./CanCat.py -I CanInTheMiddle -p /dev/tty.usbmodem1411 -S 500K`

where the -p option is your port and -S is the CAN Baud rate

Most of the commands for CanInTheMiddle are the same as the normal CanCat interface. 
Functions that report only what has been received on the Isolation side have Iso appended 
to the end of the function name. For example:

```sh
$ citm.getCanMsgCount() # The number of CAN packets seen in aggregate

$ citm.getCanMsgCountIso() # The number of CAN packets received on the Isolation network

$ citm.printCanMsgs() # Prints all CAN messages

$ citm.printCanMsgsIso() # prints all CAN messages received on the Isolation network
```

Placing a bookmark places a bookmark simultaneously on both the Isolation information (Iso interface messages) and the aggregate information (standard CAN interface messages).

Happy Hacking!



## Acknowledgments
This project is made possible through collaboration with researchers at GRIMM (SMFS, Inc.), most notably Matt Carpenter and Tim Brom.