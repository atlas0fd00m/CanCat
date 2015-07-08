# CanCat
swiss army knife of Controller Area Networks (CAN) often used in cars and building automation, etc...

made possible through collaboration with my friends at GRIMM (SMFS), most notably Matt Carpenter.

CanCat is made up of two parts:
1) Firmware for a compatible CAN-transceiver
2) Python client to talk to the tool

it is a lot like the architecture for RfCat, and we may make it moreso.  currently we're sticking with the original design by Matt and team.

currently supported CAN-transceiver combinations:
* Arduino with SeeedStudio's CANBUS Shield

possibly future options:
* "Macchina" from RechargeCar.com (they have included cool other toys for talking to other buses)
* Arduino with CANBUS Shield from LinkSprite.com (may already work, just haven't had time to test)


the goals of CanCat are multiple:
* provide a way to capture and transmit messages on an arbitrary CAN bus (whatever the speed, as supported by hardware)
* provide an architecture for analyzing messages and identifying what is what
* provide a manner for data to be shared (Ford sends different messages from GM, Saab, Toyota, Honda, Hyundai, Kia, etc...)
    this may be in the form of lookup tables
    this may be in the form of accessor code

github collab/pull requests should make this a good point of collaboration.


REQUIRED SOFTWARE:
* CANBUS_Shield from SeeedStudio  (for Firmware compilation)
    http://www.seeedstudio.com/wiki/CAN-BUS_Shield
    https://github.com/Seeed-Studio/CAN_BUS_Shield

* Python 2.7

HIGHLY RECOMMENDED SOFTWARE:
* IPython


GETTING STARTED:
once you have the required software installed, your CanCat device flashed, the interface is yours to choose.  currently, we simply enjoy using ipython to interact with the CAN bus and do analysis.
CanCat is currently centered around the class CanInterface (or some subclass of it, like FordInterface, GMInterface, etc...)

connect to the device (old way):
>>> import cancat
>>> CANalysis = cancat.CanInterface('/dev/ttyACM0', 115200) # your device may vary
>>> CANalysis.ping()

set the can bus interface baud rate (500kbps is most common, others are often slower, depending on your car):
>>> CANalysis.setCanBaud(cancat.CAN_125KBPS)    # medium speed CAN baudrate for Fords

once you connect to the device and set the device, you will automatically capture any messages the CanCat device sees on the CAN bus it is attached to.  it will store these messages for analysis

save your analysis/capture session periodically (only when you say save will it save)
>>> CANalysis.saveSessionToFile('filename_for_this_session')

once you save it once, the name will be cached so you can simply save it again to the same file by typing:
>>> CANalysis.saveSessionToFile()

other than that, "help" is your friend :)
>>> help(cancat)


connect to the device(new way - Linux):
$ ./CanCat -h
$ ./CanCat -p /dev/ttyACM0                  # if CanCat device is /dev/ttyACM0
$ ./CanCat -f filename_of_previous_capture  # no CanCat device required
'CanCat, the greatest thing since J2534!'                                                                                                                                                              
                                                                                                                                                                                                       
                                                                                                                                                                                                       Research Mode: enjoy the raw power of cancat                                                                                                                                                           

                                                                                                                                                                                                       currently your environment has an object called "c" for CanCat.  this is how 
                                                                                                                                                                                                       you interact with the CanCat dongle:
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


In [1]: 

see if the CanCat is communicating correctly with your computer (only if you have a device connected)
In [1]: c.ping()

set the can bus interface baud rate (500kbps is most common, others are often slower, depending on your car):
In [2]: c.setCanBaud(cancat.CAN_125KBPS)    # medium speed CAN baudrate for Fords

once you connect to the device and set the device, you will automatically capture any messages the CanCat device sees on the CAN bus it is attached to.  it will store these messages for analysis

save your analysis/capture session periodically (only saves when when you tell it to)
In [3]: c.saveSessionToFile('filename_for_this_session')

once you save it once, the name will be cached so you can simply save it again to the same file by typing:
In [4]: c.saveSessionToFile()

other than that, "help" is your friend :)
In [5]: help(cancat)

or tab-completion
In [6]: c.<PRESS_TAB_KEY>
c.CANrecv                          c.genCanMsgs                       c.ping                             c.recv                             c.saveSessionToFile
c.CANreplay                        c.getArbitrationIds                c.placeCanBookmark                 c.recvall                          c.setCanBaud
c.CANsniff                         c.getBookmarkFromMsgIndex          c.port                             c.register_handler                 c.setCanBookmarkComment
c.CANxmit                          c.getCanMsgCount                   c.printAsciiStrings                c.remove_handler                   c.setCanBookmarkCommentByMsgIndex
c.bookmark_info                    c.getMsgIndexFromBookmark          c.printBookmarks                   c.reprBookmark                     c.setCanBookmarkName
c.bookmarks                        c.getSessionStats                  c.printCanMsgs                     c.reprBookmarks                    c.setCanBookmarkNameByMsgIndex
c.clearCanMsgs                     c.getSessionStatsByBookmark        c.printCanMsgsByBookmark           c.reprCanMsgs                      c.snapshotCanMessages
c.comments                         c.loadFromFile                     c.printCanSessions                 c.reprCanMsgsByBookmark            c.verbose
c.filterCanMsgs                    c.log                              c.printSessionStats                c.restoreSession                   
c.filterCanMsgsByBookmark          c.name                             c.printSessionStatsByBookmark      c.saveSession                      


(start with the functions that start with "print" to get familiar with the toolset.


hack fun!
@

