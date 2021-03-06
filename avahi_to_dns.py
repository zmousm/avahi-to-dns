#!/usr/bin/env python
# -*- coding: utf-8 -*-
# TODO: revisit json i/o (structure, usage, ingest)
import sys
import os
import re


def prepare_options(cgi_mode):
    from optparse import OptionParser, OptionValueError, OptionGroup
    parser = OptionParser(usage="""Usage: %prog [ -z <target-zone>
-x <zone-xfr-from> -t <ttl> --output-rrset -d <domain> -s <service>
-n <instance-name> --instname-sed PATTERN REPL]""",
                          description="""DNS-SD browser that converts
avahi-browse output to a DNS zone/rrset""",
                          epilog=None)
    parser.add_option('-z', '--target-zone', default='example.com',
                      help='Target zone')
    parser.add_option('-x', '--zone-xfr-from', default='localhost',
                      help='DNS server to transfer target zone from')
    parser.add_option('-t', '--ttl', type="int", default=1800,
                      help="""TTL for created DNS resource records (default:
%default)""")
    parser.add_option('--output-rrset', action="store_true", default=False,
                      help="""Return only created DNS resource records rather
than a full zone (default: %default)""")
    parser.add_option('-f', '--output-format', default='dns',
                      choices=['dns', 'json'],
                      help='Output format: dns, json (default: %default)')
    parser.add_option('-d', '--domain', action="append", default=['local'],
                      help="""DNS-SD domain (default: local).
This option should be used once for each domain you want to browse.""")
    parser.add_option('-s', '--service', action="append", default=[None],
                      help="""Service name (default: all services).
This option should be used once for each service you want to enumerate.
Well known subtypes (HTTP and IPP) are enumerated automatically, other
subtypes should be specified explicitly. Specifying a subtype automatically
enumerates the master type as well.""")
    parser.add_option('-n', '--instance-name', default=None,
                      help="""Instance name to search for""")
    parser.add_option('--instname-sed', nargs=2, default=None,
                      help="""The pattern and replacement string to use for
regex replace on each instance name.""")
    parser.add_option('--instname-sed-service', action="append",
                      default=[None], help="""Regex replace on instance names
should be applied only to instances of these services. This option should be
used once for each service.""")
    printgroup = OptionGroup(parser, "Options specific to Bonjour Printing")
    printgroup.add_option('--location-map', default='{}',
                      help="""A dictionary mapping instance names to
locations""")
    printgroup.add_option('--priority-map', default='{}',
                      help="""A dictionary mapping instance names, types or
tuples of both to priorities""")
    parser.add_option_group(printgroup)

    if cgi_mode:
        import cgi
        #import cgitb
        #cgitb.enable()
        sys.stderr = sys.stdout
        form = cgi.FieldStorage()
        options = []
        if form.getfirst('target_zone'):
            options.extend(['--target-zone', form.getfirst('target_zone')])
        if form.getfirst('zone_xfr_from'):
            options.extend(['--zone-xfr-from', form.getfirst('zone_xfr_from')])
        if form.getfirst('ttl'):
            options.extend(['--ttl', form.getfirst('ttl')])
        if form.getfirst('output_rrset'):
            options.append('--output-rrset')
        if form.getfirst('output_format'):
            options.extend(['--output-format', form.getfirst('output_format')])
        [options.extend(['--domain', dom]) for dom in form.getlist('domain')]
        [options.extend(['--service', svc]) for svc in form.getlist('service')]
        options.extend(['--instance-name', form.getfirst('instance_name')])
        if form.getfirst('instname_pattern') and \
                form.getfirst('instname_repl'):
            options.extend(['--instname-sed',
                             form.getfirst('instname_pattern'),
                             form.getfirst('instname_repl')])
        [options.extend(['--instname-sed-service', svc]) for svc in
         form.getlist('instname_sed_service')]
        if form.getfirst('location_map'):
            options.extend(['--location-map', form.getfirst('location_map')])
        if form.getfirst('priority_map'):
            options.extend(['--priority-map', form.getfirst('priority_map')])
        (options, args) = parser.parse_args(options)
        # get rid of defaults because action=append doesnt
        if form.getlist('domain'):
            del options.domain[0]
        if form.getlist('service'):
            del options.service[0]
        if form.getlist('instname_sed_service'):
            del options.instname_sed_service[0]
    else:
        (options, args) = parser.parse_args(sys.argv[1:])
        # get rid of defaults because action=append doesnt
        if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:] for opt_str
                    in str(parser.get_option('--domain')).
                    split('/')]:
            del options.domain[0]
        if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:] for opt_str
                    in str(parser.get_option('--service')).
                    split('/')]:
            del options.service[0]
        if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:] for opt_str
                    in str(parser.get_option('--instname-sed-service')).
                    split('/')]:
            del options.instname_sed_service[0]
        # for opt in ['service', 'domain']:
        #     opt = parser.get_option('--%s' % opt)
        #     if True in [arg.find(opt_str) == 0 for arg in sys.argv[1:]
        #                 for opt_str in str(opt).split('/')]:
        #         del getattr(options, opt.dest)[0]

    #print options
    return options


def zeroconf_search_multi(name=None, types=[None], domains=['local'],
                          sed_pattern=None, sed_repl=None, sed_service=[None]):
    import zeroconf

    default_subtypes = {'_ipp._tcp':  ['_universal._sub._ipp._tcp',
                                        '_cups._sub._ipp._tcp'],
                        '_ipps._tcp': ['_universal._sub._ipps._tcp',
                                        '_cups._sub._ipps._tcp'],
                        '_http._tcp': ['_printer._sub._http._tcp']
                        }

    types = set(types)
    domains = set(domains)

    # special handling for subtypes: they are not queried through _services
    # enumeration and we can not tell them apart in responses from the
    # corresponding master service)
    subtypes_all = {type for type in types
                if isinstance(type, basestring) and
                len(re.split(r'(?<!\\)\.', type)) > 3 and
                re.split(r'(?<!\\)\.', type)[-3] == '_sub'}
    types -= subtypes_all
    # enumerate for well known sub-types if the master is requested
    for k in default_subtypes:
        if k in types:
            subtypes_all.update(default_subtypes[k])
        # but also enumerate the master if a sub-type is requested
        else:
            types |= {k for i in default_subtypes[k] if i in subtypes_all}

    filter_types = set()
    stype = None
    if len(types) > 1:
        filter_types = types
    elif types:
        stype = types.pop()

    results_all = {}
    for domain in domains:
        results = zeroconf.search(name=name, type=stype, domain=domain)

        subtypes = subtypes_all
        # add default subtypes to subtypes to be enumerated if the master is
        # found in results
        for subt_key in default_subtypes:
            if subt_key in [res_key[1] for res_key in results.keys()]:
                subtypes.update(default_subtypes[subt_key])
        # enumerate for each subtype individually
        for subtype in subtypes:
            for (key, val) in zeroconf.search(name=name, type=subtype,
                                              domain=domain).items():
                subtype = re.sub(r'._sub.%s' % key[1], '', subtype)
                # record in results for master type, add subtype
                if key in results and \
                        {k: results[key][k] for k in results[key]
                         if k != 'subtypes'} == val:
                        if 'subtypes' in results[key]:
                            results[key]['subtypes'].append(subtype)
                        else:
                            results[key]['subtypes'] = [subtype]
                # no record in results for master type, add record and subtype
                else:
                    results.update({key: val})
                    results[key]['subtypes'] = [subtype]

        results_all.update(results)

    if filter_types:
        for key in results_all.keys():
            _, svc_, _ = key
            if not svc_ in filter_types and \
                    not svc_ in subtypes:
                del results_all[key]

    for key in results_all.keys():
        name_, svc_, dom_ = key
        displayname = name_
        if sed_pattern is not None and sed_repl is not None:
            if sed_service != [None] and svc_ in sed_service:
                # newname = re.sub(r'^(.+)( @ cups)', r'AirPrint: \g<1>',
                #                  name_)
                displayname = re.sub(r'%s' % sed_pattern, r'%s' % sed_repl,
                                     name_)
        results_all[(displayname, svc_, dom_, name_)] = results_all[key]
        del results_all[key]

    return results_all  # if len(results) > 0 else None


def zeroconf_to_json(zeroconf_results={}):
    import json

    ndict = dict()

    for key, val in zeroconf_results.iteritems():
        nkey = json.dumps(key)
        ndict[nkey] = val

    return json.dumps(ndict) if len(ndict) > 0 else None


def mudns_query(qname, rdtype, qwhere='default resolver', qport=53,
                qtimeout=2, qu=False, res=None):
    import dns.name
    import dns.resolver
    import dns.query
    from dns.exception import DNSException, Timeout
    from dns.resolver import NoAnswer, NXDOMAIN
    import dns.rdatatype
    import dns.rdataclass

    qubit = 32768
    a = None

    if qwhere is 'default resolver':
        qwhere = dns.resolver.get_default_resolver().nameservers

    if qu:
        pass
    elif isinstance(res, dns.resolver.Resolver):
        instresolver = res
    else:
        instresolver = dns.resolver.Resolver()

    if isinstance(qname, (str, unicode)):
        qname = dns.name.from_text(qname, None)
    if isinstance(rdtype, (str, unicode)):
        rdtype = dns.rdatatype.from_text(rdtype)

    # QU query (typically multicast)
    # cant use dns.resolver since the question and answer will have a
    # different class failing validation
    if qu:
        q = dns.message.make_query(qname, rdtype,
                                   rdclass=dns.rdataclass.IN + qubit)
        try:
            m = dns.query.udp(q, qwhere, port=qport, timeout=qtimeout)
        except (DNSException) as e:
            # print "dns.query.udp %s : %s %s -> " + \
            #     "exception %s" % (qwhere,
            #                       qname.to_text(),
            #                       dns.rdatatype.to_text(rdtype),
            #                       type(e))
            pass
        else:
            if isinstance(m, dns.message.Message):
                a = dns.resolver.Answer(qname, rdtype, dns.rdataclass.IN, m)
    # direct unicast query
    else:
        instresolver.nameservers = [qwhere]
        instresolver.port = qport
        instresolver.lifetime = qtimeout
        try:
            a = dns.resolver.query(qname, rdtype,
                                   rdclass=dns.rdataclass.IN)
        except (DNSException, NoAnswer, NXDOMAIN) as e:
            # print "dns.resolver.query %s : %s %s -> exception %s" % (
            #     ' '.join(instresolver.nameservers),
            #     qname.to_text(),
            #     dns.rdatatype.to_text(rdtype),
            #     type(e)
            #     )
            pass

    return a


def txt_field_mangle(txt, fieldname, newval=False):
            txt_fields = re.split('(?<=")\s+(?=")', txt)[::]

            idx = False
            for (k, txt_field) in enumerate(txt_fields):
                if txt_field.find('"%s=' % fieldname) == 0:
                    idx = k
                    break

            if newval is False:
                curval = None
                if idx is not False:
                    curval = re.search(r'^"%s=([^"]*)"$' % fieldname,
                                    txt_fields[idx])
                    if curval is not None:
                        curval = curval.group(1)
                return curval

            if newval is None:
                if idx is not False:
                    del txt_fields[idx]
            else:
                txt_field_new = '"%s=%s"' % (fieldname, newval)
                if idx is not False:
                    txt_fields[idx] = txt_field_new
                else:
                    txt_fields.append(txt_field_new)

            return ' '.join(txt_fields)


def zeroconf_to_zone(target_zone='example.com', target_ns='localhost',
                     zeroconf_results={}, locmap={}, priomap={}, ttl=1800):
    import dns.name
    import dns.reversename
    import dns.resolver
    import dns.query
    from dns.exception import DNSException, Timeout
    from dns.resolver import NoAnswer, NXDOMAIN
    import dns.zone
    import dns.node
    import dns.rdataset
    import dns.rdata
    #from dns.rdatatype import *
    import dns.rdatatype
    import dns.rdataclass

    if not isinstance(locmap, dict):
        raise TypeError
    if not isinstance(priomap, dict):
        raise TypeError

    if target_zone == 'example.com':
        zone = """@ 86400 IN SOA {ns}. administrator.example.com. 1970000000 \
28800 7200 604800 1800
@ 86400 IN NS {ns}.""".format(ns=target_ns)
    else:
        zone = dns.zone.from_xfr(dns.query.xfr(target_ns, target_zone))
        zone = zone.get('@').to_text(zone.origin)
    zone = dns.zone.from_text(zone, origin=target_zone)
    # ttl = ttl if not ttl == None else \
    #     zone.get_rdataset('@', dns.rdatatype.SOA).ttl

    reverse_resolved = {}

    for key in zeroconf_results:
        inst_name, inst_type, inst_domain, inst_name_orig = key
        inst_subtypes = zeroconf_results[key]['subtypes'] \
            if 'subtypes' in zeroconf_results[key] else []

        # create service type and subtype nodes (empty nodes deleted at the
        # end)
        type_node = zone.find_node(dns.name.from_text(inst_type,
                                                      origin=zone.origin),
                                   create=True)
        subtype_nodes = [zone.find_node(dns.name.from_text(subtype + '._sub.'
                                                           + inst_type,
                                                           origin=zone.origin),
                                        create=True)
                         for subtype in inst_subtypes]

        # <Instance> must be a single DNS label, any dots should be escaped
        # before concatenating all portions of a Service Instance Name,
        # according to DNS-SD (RFC6763).
        # A workaround is necessary for buggy software that does not adhere to
        # the rules:
        inst_name = re.sub(r'(?<!\\)\.', r'\.', inst_name)

        inst_fullname = dns.name.from_text("%s.%s" % (inst_name, inst_type),
                                           origin=zone.origin)

        inst_addr = zeroconf_results[key]['address']
        if inst_addr not in reverse_resolved:
            try:
                reverse_resolved[inst_addr] = dns.resolver.query(
                    dns.reversename.from_address(inst_addr),
                    dns.rdatatype.PTR)
            except DNSException, e:
                reverse_resolved[inst_addr] = None
                continue
        # inst_hostname_rev_rr = dns.resolver.query(dns.reversename.
        #                                           from_address(inst_addr),
        #                                           dns.rdatatype.PTR)
        inst_hostname_rev_rr = reverse_resolved[inst_addr] \
            if reverse_resolved[inst_addr] is not None else []
        zeroconf_results[key]['hostname_rev'] = [i.to_text(relativize=False)
                                                 for i in inst_hostname_rev_rr]

        if not zeroconf_results[key]['hostname_rev']:
            continue

        node_ptr_rdata = dns.rdata.from_text(dns.rdataclass.IN,
                                             dns.rdatatype.PTR,
                                             inst_fullname.to_text())
        # fill service type and subtype nodes with PTR rdata
        type_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.PTR,
                                create=True).add(node_ptr_rdata, ttl=ttl)
        for subtype_node in subtype_nodes:
            subtype_node.find_rdataset(dns.rdataclass.IN, dns.rdatatype.PTR,
                                       create=True).add(node_ptr_rdata,
                                                        ttl=ttl)

        # create instance node
        inst_node = zone.find_node(inst_fullname, create=True)

        # avahi-browse returns a single SRV and TXT record so we should
        # try to resolve again

        qname = dns.name.from_text("%s.%s" % (inst_name_orig, inst_type),
                                  origin=dns.name.from_text(inst_domain))

        instresolver = dns.resolver.Resolver()

        mdns_addr = '224.0.0.251'

        for l, rdt in (('srv', dns.rdatatype.SRV),
                       ('txt', dns.rdatatype.TXT)):
            if inst_domain == 'local':
                # mDNS:
                # * try a multicast query first:
                #   - with unicast-response (QU) bit set
                #   - legacy per RFC6762 sec. 6.7 as we wont set
                #     source_port=5353
                # * fallback to direct unicast query (RFC6762 sec. 5.5)
                #   caveat:
                #   unicast responses must be less than 512 bytes
                #   or else we will not get an answer (no EDNS0)
                a = mudns_query(qname, rdt, qwhere=mdns_addr, qport=5353,
                                qtimeout=2, qu=True)
                #print "mudns returned %s" % str(a)
                if a is None:
                    a = mudns_query(qname, rdt, qwhere=inst_addr,
                                    qport=5353, qtimeout=2,
                                    res=instresolver)
            else:
                a = mudns_query(qname, rdt, qtimeout=4)

            if isinstance(a, dns.resolver.Answer):
                zeroconf_results[key][l] = [rd.to_text() for rd in a[::]]
            else:
                if l == 'srv':
                    zeroconf_results[key][l] = [
                        '0 0 %s %s' %
                        (zeroconf_results[key]['port'],
                         zeroconf_results[key]['hostname'])
                        ]
                elif l == 'txt':
                    # reverse the order of fields as returned by avahi
                    txt_rec_rev = re.split('(?<=")\s+(?=")',
                                           zeroconf_results[key][l]
                                           )[::-1]
                    zeroconf_results[key][l] = [' '.join(txt_rec_rev)]

            #print ""
        #continue

        # replace hostname.local or whatever avahi returns with
        # reverse-resolved fqdn
        for h in zeroconf_results[key]['hostname_rev']:
            zeroconf_results[key]['srv'] = [
                re.sub(
                    r'%s\.?' % zeroconf_results[key]['hostname'],
                    r'%s' % h,
                    r)
                for r in zeroconf_results[key]['srv']
                ]
            zeroconf_results[key]['txt'] = [
                re.sub(
                    r'%s\.?' % zeroconf_results[key]['hostname'],
                    r'%s' % h.rstrip('.'),
                    r)
                for r in zeroconf_results[key]['txt']
                ]

        # txt record mangling
        for (i, txt_rec) in enumerate(zeroconf_results[key]['txt']):
            # Bonjour Printing mangling
            # discard ephemeral fields: printer-state
            txt_rec = txt_field_mangle(txt_rec, 'printer-state', None)
            zeroconf_results[key]['txt'][i] = txt_rec

            # note field mangling
            if inst_name in locmap:
                txt_rec = txt_field_mangle(txt_rec, 'note', locmap[inst_name])
                zeroconf_results[key]['txt'][i] = txt_rec

            # priority field mangling
            if (inst_name, inst_type) in priomap:
                newprio = priomap[(inst_name, inst_type)]
            elif inst_name in priomap:
                newprio = priomap[inst_name]
            elif inst_type in priomap:
                newprio = priomap[inst_type]
            else:
                newprio = None
            if newprio is not None:
                prio = txt_field_mangle(txt_rec, 'priority')
                if prio is not None:
                    prio = int(prio)
                    if prio == 0:
                        continue
                else:
                    # Bonjour Printing spec v1.2 sec. 9.2.5
                    # if not specified, priority defaults to 50
                    prio = 50
                # keep the modulo 10 part of original priority
                prio = prio % 10
                txt_rec = txt_field_mangle(txt_rec, 'priority', newprio + prio)
                zeroconf_results[key]['txt'][i] = txt_rec

        # fill instance node with SRV and TXT rdata
        for rec_type in ('srv', 'txt'):
            for r in zeroconf_results[key][rec_type]:
                inst_node.find_rdataset(dns.rdataclass.IN,
                                        dns.rdatatype.from_text(rec_type),
                                        create=True).add(
                    dns.rdata.from_text(dns.rdataclass.IN,
                                        dns.rdatatype.from_text(rec_type),
                                        r),
                    ttl=ttl)

    # delete empty nodes in zone after iterating through all the results
    for name, node in zone.nodes.items():
        if not node.rdatasets:
            zone.delete_node(name)
    return zone


try:
    cgi_mode = True if 'GATEWAY_INTERFACE' in os.environ and \
        os.environ['GATEWAY_INTERFACE'].find('CGI') == 0 else False

    options = prepare_options(cgi_mode)

    sed_pattern, sed_repl = options.instname_sed \
        if options.instname_sed is not None else (None, None)

    results = zeroconf_search_multi(types=options.service,
                                    domains=options.domain,
                                    name=options.instance_name,
                                    sed_pattern=sed_pattern,
                                    sed_repl=sed_repl,
                                    sed_service=options.instname_sed_service)

    if not results:
        sys.exit()

    if options.output_format == "dns":
        zone = zeroconf_to_zone(target_zone=options.target_zone,
                                target_ns=options.zone_xfr_from,
                                zeroconf_results=results,
                                locmap=eval(options.location_map),
                                priomap=eval(options.priority_map),
                                ttl=options.ttl)
    elif options.output_format == "json":
        zone = zeroconf_to_json(zeroconf_results=results)

    if not zone:
        sys.exit()

    if cgi_mode:
        print 'Content-Type: text/{format}' % options.output_format
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
