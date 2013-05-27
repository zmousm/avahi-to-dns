#!/usr/bin/env python
# -*- coding: utf-8 -*-

#import cgi
#import cgitb; cgitb.enable()
import zeroconf
import dns.name
import dns.resolver
import dns.reversename
import re
from dns.rdatatype import *
from dns.exception import DNSException


#print

def dnssd_search(stype='_http._tcp'):
    dnssd = zeroconf.search(name=None, type=stype, domain="local")

    for key in dnssd.keys():
        inst_type = key[1]
        # <Instance> must be a single DNS label, any dots should be escaped before concatenating
        # all portions of a Service Instance Name, according to DNS-SD (RFC6763).
        # A workaround is necessary for buggy software that does not adhere to the rules:
        inst_name = re.sub(r'(?<!\\)\.', r'\.', key[0])
        inst_fullname = dns.name.from_text(inst_name + '.' + inst_type).to_text(omit_final_dot=True)
        try:
            inst_hostname_rev_rr = dns.resolver.query(dns.reversename.from_address(dnssd[key]['address']), 'PTR')
        except DNSException, e:
            continue
        dnssd[key]['hostname_rev'] = [i.to_text(relativize=False) for i in inst_hostname_rev_rr]
        inst_port = dnssd[key]['port']
        inst_txt_rdata_rev = re.split(r'(?<=")\s+(?=")', dnssd[key]['txt'])[::-1]
        if not len(dnssd[key]['hostname_rev']) > 0:
            continue
        print "%-100s %-3s %-30s" % (inst_type, 'PTR', inst_fullname)
        for h in dnssd[key]['hostname_rev']:
            # replace hostname.local with reverse-resolved fqdn in TXT rdata
            inst_txt_rdata_rev_host = [ re.sub(r'%s\.?' % dnssd[key]['hostname'], r'%s' % h.rstrip('.'), blob) for blob in inst_txt_rdata_rev ]
            inst_txt_rdata_rev_host = ' '.join(inst_txt_rdata_rev_host)
            print "%-100s %-3s %2d %2d %-5s %-50s" % (inst_fullname, 'SRV', 0, 0, inst_port, h)
            if (dnssd[key]['txt'] != ''):
                print "%-100s %-3s %s" % (inst_fullname, 'TXT', inst_txt_rdata_rev_host)

for stype in ['_ipp._tcp', '_printer._tcp', '_pdl-datastream._tcp', '_print-caps._tcp', '_riousbprint._tcp', '_canon-bjnp1._tcp', '_http._tcp' ]:
    dnssd_search(stype=stype)
