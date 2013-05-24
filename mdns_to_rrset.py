#!/usr/bin/env python
# coding: utf-8

import zeroconf
import dns.name
import dns.resolver
import dns.reversename
import re

def dnssd_search(stype='_ipp._tcp'):
    dnssd = zeroconf.search(name=None, type=stype, domain="local")

    for key in dnssd.keys():
      inst_type = key[1]
      inst_fullname = dns.name.from_text(key[0] + '.' + key[1]).to_text(omit_final_dot=True)
      inst_port = dnssd[key]['port']
      inst_hostname = dns.resolver.query(dns.reversename.from_address(dnssd[key]['address']), 'PTR')[0].to_text()
      inst_txt_rdata_rev = re.split('(?<=")\s+(?=")', dnssd[key]['txt'])[::-1]
      # replace hostname.local with reverse-resolved fqdn                                                                                                                                                   
      inst_txt_rdata_rev = [ re.sub(r'%s\.?' % dnssd[key]['hostname'], r'%s' % inst_hostname.rstrip('.'), blob) for blob in inst_txt_rdata_rev ]
      inst_txt_rdata_rev = ' '.join(inst_txt_rdata_rev)

      print "%-100s %-3s %-30s" % (inst_type, 'PTR', inst_fullname)
      print "%-100s %-3s %2d %2d %-5s %-50s" % (inst_fullname, 'SRV', 0, 0, inst_port, inst_hostname)
      print "%-100s %-3s %s" % (inst_fullname, 'TXT', inst_txt_rdata_rev)

for stype in ['_ipp._tcp', '_printer._tcp', '_pdl-datastream._tcp', '_print-caps._tcp', '_riousbprint._tcp', '_canon-bjnp1._tcp']:
    dnssd_search(stype=stype)
