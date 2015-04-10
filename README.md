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
* Currently, CANBUS_Shield from SeeedStudio  
    http://www.seeedstudio.com/wiki/CAN-BUS_Shield
    https://github.com/Seeed-Studio/CAN_BUS_Shield

hack fun!
@

