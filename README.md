Small script that turns avahi-browse output to DNS data or other useful formats.

It requires these python modules:
* dnspython
* zeroconf ([this fork](//github.com/zmousm/zeroconf))

Zeroconf in turn requires:
* pbs python module for calling avahi-browse
* avahi: avahi-daemon should be running and avahi-browse should be available in the PATH
