#!/usr/bin/env python
# -*- coding: utf-8 -*-
# TODO: revisit json i/o (structure, usage, ingest)
import sys
import os
import re

def prepare_options(cgi_mode):
    from optparse import OptionParser, OptionValueError, OptionGroup
    parser = OptionParser (usage="Usage: %prog [ -z <target-zone> -x <zone-xfr-from> -t <ttl> --output-rrset -d <domain> -s <service> -n <instance-name> ]",
                           description="DNS-SD browser (via avahi-browse) that returns a DNS zone or rrset",
                           epilog=None)
    parser.add_option('-z', '--target-zone', default='example.com',
                      help='Target zone')
    parser.add_option('-x', '--zone-xfr-from', default='localhost',
                      help='DNS server to transfer target zone from')
    parser.add_option('-t', '--ttl', type="int", default=1800,
                      help='TTL for created DNS resource records (default: %default)')
    parser.add_option('--output-rrset', action="store_true", default=False,
                      help='Return only created DNS resource records rather than a full zone (default: %default)')
    parser.add_option('-f', '--output-format', default='dns', choices=['dns', 'json'],
                      help='Output format: dns, json (default: %default)')
    parser.add_option('-d', '--domain', action="append", default=['local'],
                      help="""DNS-SD domain (default: local).
This option should be used once for each domain you want to browse.""")
    parser.add_option('-s', '--service', action="append", default=[None],
                      help="""Service name (default: all services).
This option should be used once for each service you want to enumerate.""")
    parser.add_option('-n', '--instance-name', default=None,
                      help="""Instance name""")

    if cgi_mode:
        import cgi
        #import cgitb
        #cgitb.enable()
        sys.stderr = sys.stdout
        form = cgi.FieldStorage()
        options = []
        if form.getfirst('target_zone'):
            options.extend([ '--target-zone', form.getfirst('target_zone') ])
        if form.getfirst('zone_xfr_from'):
            options.extend([ '--zone-xfr-from', form.getfirst('zone_xfr_from') ])
        if form.getfirst('ttl'):
            options.extend([ '--ttl', form.getfirst('ttl') ])
        if form.getfirst('output_rrset'):
            options.append('--output-rrset')
        if form.getfirst('output_format'):
            options.extend([ '--output-format', form.getfirst('output_format') ])
        [options.extend(['--domain', dom]) for dom in form.getlist('domain')]
        [options.extend(['--service', svc]) for svc in form.getlist('service')]
        options.extend([ '--instance-name', form.getfirst('instance_name')])
        (options, args) = parser.parse_args(options)
        # get rid of defaults because action=append doesnt
        if form.getlist('domain'):
            del options.domain[0]
        if form.getlist('service'):
            del options.service[0]
    else:
        (options, args) = parser.parse_args(sys.argv[1:])
        # get rid of defaults because action=append doesnt
        if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:] for opt_str in str(parser.get_option('--domain')).split('/')]:
            del options.domain[0]
        if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:] for opt_str in str(parser.get_option('--service')).split('/')]:
            del options.service[0]
        # for opt in ['service', 'domain']:
        #     opt = parser.get_option('--%s' % opt)
        #     if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:] for opt_str in str(opt).split('/')]:
        #         del getattr(options, opt.dest)[0]
    #print options
    return options

def zeroconf_search_multi(name=None, types=[None], domains=['local']):
    import zeroconf

    # name = 'name'
    # types = 'types'
    # domains = 'domains'

    # name = kwargs[name] if name in kwargs else None
    # if types in kwargs:
    #     types = list(set(kwargs[types])) if not isinstance(kwargs[types], basestring) else [kwargs[types]]
    # else:
    #     types = None
    # if domains in kwargs:
    #     domains = list(set(kwargs[domains])) if not isinstance(kwargs[domains], basestring) else [kwargs[domains]]
    # else:
    #     domains = 'local'

    # name = kwargs['name'] if 'name' in kwargs else None
    # types = list(set(kwargs['types'])) if 'types' in kwargs else [None]
    # domains = list(set(kwargs['domains'])) if 'domains' in kwargs else ['local']

    filter_types = []
    results = {}
    if len(types) > 1:
        filter_types = types
        stype = None
    else:
        stype = types[0]
    for domain in domains:
        results.update(zeroconf.search(name=name, type=stype, domain=domain))
    if filter_types:
        for key in results.keys():
            _, svc_, _ = key
            if not svc_ in filter_types:
                del results[key]
    return results #if len(results) > 0 else None

def zeroconf_to_json(zeroconf_results = {}):
    import json

    ndict = dict()

    for key, val in zeroconf_results.iteritems():
        nkey = json.dumps(key)
        ndict[nkey] = val

    return json.dumps(ndict) if len(ndict) > 0 else None

def zeroconf_to_zone(target_zone='example.com', target_ns='localhost', zeroconf_results = {}, ttl=1800):
    import dns.name
    import dns.reversename
    import dns.resolver
    import dns.query
    from dns.exception import DNSException
    import dns.zone
    import dns.node
    import dns.rdataset
    import dns.rdata
    #from dns.rdatatype import *
    import dns.rdatatype
    import dns.rdataclass

    if target_zone == 'example.com':
        zone = """@ 86400 IN SOA {ns}. administrator.example.com. 1970000000 28800 7200 604800 1800
@ 86400 IN NS {ns}.""".format(ns=target_ns)
    else:
        zone = dns.zone.from_xfr(dns.query.xfr(target_ns, target_zone))
        zone = zone.get('@').to_text(zone.origin)
    zone = dns.zone.from_text(zone, origin=target_zone)
    # ttl = ttl if not ttl == None else zone.get_rdataset('@', dns.rdatatype.SOA).ttl

    reverse_resolved = {}

    for key in zeroconf_results:
        inst_name, inst_type, inst_domain = key
        type_node = zone.find_node(dns.name.from_text(inst_type, origin=zone.origin), create=True)
        # <Instance> must be a single DNS label, any dots should be escaped before concatenating
        # all portions of a Service Instance Name, according to DNS-SD (RFC6763).
        # A workaround is necessary for buggy software that does not adhere to the rules:
        inst_name = re.sub(r'(?<!\\)\.', r'\.', inst_name)
        inst_fullname = dns.name.from_text("%s.%s" % (inst_name, inst_type), origin=zone.origin)
        inst_addr = zeroconf_results[key]['address']

        if inst_addr not in reverse_resolved:
            try:
                reverse_resolved[inst_addr] = dns.resolver.query(
                    dns.reversename.from_address(inst_addr),
                    dns.rdatatype.PTR)
            except DNSException, e:
                reverse_resolved[inst_addr] = None
                continue
        #inst_hostname_rev_rr = dns.resolver.query(dns.reversename.from_address(inst_addr), dns.rdatatype.PTR)
        inst_hostname_rev_rr = reverse_resolved[inst_addr] if reverse_resolved[inst_addr] is not None else []
        zeroconf_results[key]['hostname_rev'] = [i.to_text(relativize=False) for i in inst_hostname_rev_rr]

        inst_port = zeroconf_results[key]['port']
        inst_txt_rdata_rev = re.split('(?<=")\s+(?=")', zeroconf_results[key]['txt'])[::-1]
        if not len(zeroconf_results[key]['hostname_rev']) > 0:
            continue
        type_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.PTR, create=True).add(
            dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.PTR, inst_fullname.to_text()), ttl=ttl)
        inst_node = zone.find_node(inst_fullname, create=True)
        for h in zeroconf_results[key]['hostname_rev']:
            # replace hostname.local or whatever avahi returns with reverse-resolved fqdn
            inst_txt_rdata_rev_fqdn = [ re.sub(r'%s\.?' % zeroconf_results[key]['hostname'], r'%s' % h.rstrip('.'), kvp) for kvp in inst_txt_rdata_rev ]
            inst_txt_rdata_rev_fqdn = ' '.join(inst_txt_rdata_rev_fqdn)
            inst_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.SRV, create=True).add(
                dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.SRV, '0 0 %s %s' % (inst_port, h)), ttl=ttl)
            if (zeroconf_results[key]['txt'] != ''):
                inst_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.TXT, create=True).add(
                    dns.rdata.from_text(dns.rdataclass.IN, dns.rdatatype.TXT, inst_txt_rdata_rev_fqdn), ttl=ttl)

    return zone


try:
    cgi_mode = True if 'GATEWAY_INTERFACE' in os.environ and os.environ['GATEWAY_INTERFACE'].find('CGI') == 0 else False

    options = prepare_options(cgi_mode)

    results = zeroconf_search_multi(types = options.service,
                                    domains = options.domain,
                                    name = options.instance_name)

    if not results:
        sys.exit()

    if options.output_format == "dns":
        zone = zeroconf_to_zone(target_zone=options.target_zone, target_ns=options.zone_xfr_from, zeroconf_results=results, ttl=options.ttl)
    elif options.output_format == "json":
        zone = zeroconf_to_json(zeroconf_results=results)

    if not zone:
        sys.exit()

    if cgi_mode:
        print 'Content-Type: text/{format}'.format(format=options.output_format)
        print

    if options.output_format == "dns":
        if options.output_rrset:
            zone.delete_node('@')
        zone.to_file(sys.stdout)
    elif options.output_format == "json":
        print zone

except:
    if cgi_mode:
        print 'Content-Type: text/plain'
        print
    raise
