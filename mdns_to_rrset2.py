#!/usr/bin/env python
# -*- coding: utf-8 -*-

import sys
#import cgi
#import cgitb; cgitb.enable()
import zeroconf
import dns.name
import dns.reversename
import dns.resolver
import dns.query
import re
#from dns.rdatatype import *
from dns.exception import DNSException

import dns.zone
import dns.node
import dns.rdataset
import dns.rdata
import dns.rdatatype
import dns.rdataclass

#print

def zeroconf_search_multi(**kwargs):
    name = 'name'
    types = 'types'
    domains = 'domains'

    name = kwargs[name] if name in kwargs else None
    if types in kwargs:
        types = list(set(kwargs[types])) if not isinstance(kwargs[types], basestring) else [kwargs[types]]
    else:
        types = None
    if domains in kwargs:
        domains = list(set(kwargs[domains])) if not isinstance(kwargs[domains], basestring) else [kwargs[domains]]
    else:
        domains = 'local'

    results = {}
    for (stype, domain) in [(t, d) for t in types for d in domains]:
        print "search: %s, %s, %s" % (name, stype, domain)
        print zeroconf.search(name=name, type=stype, domain=domain)
        results.update(zeroconf.search(name=name, type=stype, domain=domain))
    return results #if len(results) > 0 else None

def zeroconf_to_zone(target_zone, target_ns='localhost', zeroconf_results = {}, ttl=3600):
    # dnssd_results = {}
    # for stype in list(set(stypes)) if not isinstance(stypes, basestring) else [stypes]:
    #     dnssd_results.update(zeroconf.search(name=None, type=stype, domain="local"))

    zone = dns.zone.from_xfr(dns.query.xfr(target_ns, target_zone))
    zone = zone.get('@').to_text(zone.origin)
    zone = dns.zone.from_text(zone, origin=target_zone)

    # dnssd = zeroconf.search(name=None, type=stype, domain="local")
    # dnssd = dnssd_results

    for key in zeroconf_results:
        inst_type = key[1]
        type_node = zone.find_node(dns.name.from_text(inst_type, origin=zone.origin), create=True)
        # <Instance> must be a single DNS label, any dots should be escaped before concatenating
        # all portions of a Service Instance Name, according to DNS-SD (RFC6763).
        # A workaround is necessary for buggy software that does not adhere to the rules:
        inst_name = re.sub(r'(?<!\\)\.', r'\.', key[0])
        inst_fullname = dns.name.from_text("%s.%s" % (inst_name, inst_type), origin=zone.origin)
        try:
            inst_hostname_rev_rr = dns.resolver.query(dns.reversename.from_address(zeroconf_results[key]['address']), dns.rdatatype.PTR)
        except DNSException, e:
            continue
        zeroconf_results[key]['hostname_rev'] = [i.to_text(relativize=False) for i in inst_hostname_rev_rr]
        inst_port = zeroconf_results[key]['port']
        inst_txt_rdata_rev = re.split('(?<=")\s+(?=")', zeroconf_results[key]['txt'])[::-1]
        if not len(zeroconf_results[key]['hostname_rev']) > 0:
            continue
        #print "%-100s %-3s %-30s" % (inst_type, 'PTR', inst_fullname)
        type_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.PTR, create=True).add(
            dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.PTR, inst_fullname.to_text()), ttl=ttl)
        inst_node = zone.find_node(inst_fullname, create=True)
        for h in zeroconf_results[key]['hostname_rev']:
            # replace hostname.local with reverse-resolved fqdn
            inst_txt_rdata_rev_fqdn = [ re.sub(r'%s\.?' % zeroconf_results[key]['hostname'], r'%s' % h.rstrip('.'), kvp) for kvp in inst_txt_rdata_rev ]
            inst_txt_rdata_rev_fqdn = ' '.join(inst_txt_rdata_rev_fqdn)
            #print "%-100s %-3s %2d %2d %-5s %-50s" % (inst_fullname, 'SRV', 0, 0, inst_port, h)
            inst_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.SRV, create=True).add(
                dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.SRV, '0 0 %s %s' % (inst_port, h)), ttl=ttl)
            if (zeroconf_results[key]['txt'] != ''):
                #print "%-100s %-3s %s" % (inst_fullname, 'TXT', inst_txt_rdata_rev_fqdn)
                inst_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.TXT, create=True).add(
                    dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.TXT, inst_txt_rdata_rev_fqdn), ttl=ttl)

    #zone.delete_node('@')
    #zone.to_file(sys.stdout)
    return zone
#for stype in ['_ipp._tcp', '_printer._tcp', '_pdl-datastream._tcp', '_print-caps._tcp', '_riousbprint._tcp', '_canon-bjnp1._tcp', '_http._tcp' ]:
#for stype in ['_ipp._tcp']:
#    dnssd_search(target_zone='dns-sd.admin.grnet.gr', target_ns='caeus.admin.grnet.gr', stypes=stype)

results = zeroconf_search_multi(types = ['_ipp._tcp', '_printer._tcp', '_pdl-datastream._tcp', '_print-caps._tcp', '_riousbprint._tcp', '_canon-bjnp1._tcp', '_http._tcp' ],
                               domains = ['local'])
# results = zeroconf_search_multi(types = ['_ipp._tcp'],
#                                 domains = 'dns-sd.admin.grnet.gr')


#print results
if results:
    zone = zeroconf_to_zone('dns-sd.admin.grnet.gr', 'caeus.admin.grnet.gr', results, 1800)
    if zone:
        #zone.get('_ipp._tcp.dns-sd.admin.grnet.gr.')
        #zone.delete_node('@')
        zone.to_file(sys.stdout)
