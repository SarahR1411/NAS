import json
import os
import ipaddress
from collections import defaultdict
from addresses import get_address_file
from create_graph import run_network_visualization

def load_intent(file_path):
    """
    Load network intent from a JSON file
    """
    with open(file_path) as f:
        return json.load(f)

class IPAllocator:
    """
    Manages IP address allocation for router interfaces and loopbacks
    """
    def __init__(self, intent):
        self.intent = intent
        sp = intent['network']['service_provider']
        self.base_network = ipaddress.IPv4Network(sp['base_prefix'])
        self.sp_loopback_network = ipaddress.IPv4Network(sp['loopback_prefix'])
        self.customer_loopback_networks = {
            cust['name']: ipaddress.IPv4Network(cust['loopback_prefix'])
            for cust in intent['network']['customers']
        }
        self.external_network = ipaddress.IPv4Network(sp['external_prefix'])
        self.external_loopback_networks = {
            ext['name']: ipaddress.IPv4Network(ext['loopback_prefix'])
            for ext in intent['network']['external_as']
        }
        self.link_subnets = {} # to store allocated subnets for SP core links
        self.loopback_ips = {}
        self.ce_loopback_ips = {}
        self.ex_loopback_ips = {}
        self.sp_loopback_counter = 0
        self.ce_loopback_counters = {cust['name']: 0 for cust in intent['network']['customers']}
        self.ex_loopback_counters = {ext['name']: 0 for ext in intent['network']['external_as']}
        self.ce_to_customer = {}
        for peer in intent['protocols']['bgp']['ebgp_peers']:
            ce = peer['ce']
            vrf = peer['vrf']
            customer = next(cust for cust in intent['network']['customers'] if vrf in cust['vrfs'])
            self.ce_to_customer[ce] = customer['name']
        self.customer_subnets = defaultdict(list) # to store customer subnets, keyed by customer name
        self.ex_to_as = {}
        for ext in intent['network']['external_as']:
            for router in ext['routers']:
                self.ex_to_as[router] = ext['name']
        self.external_subnets = defaultdict(list)

    def get_link_subnet(self, router_a, router_b):
        """
        Allocate a /30 subnet for a link between 2 SP routers.
        """
        key = tuple(sorted([router_a, router_b]))
        if key not in self.link_subnets:
            # subnet the base network into /30 networks and take the next available one
            subnet = list(self.base_network.subnets(new_prefix=30))[len(self.link_subnets)]
            hosts = list(subnet.hosts()) # get only the usable host IPs
            self.link_subnets[key] = hosts
        return self.link_subnets[key]

    def get_sp_loopback_ip(self, router):
        """
        Allocate a /32 loopback ip for an SP router
        """
        if router not in self.loopback_ips:
            ip = list(self.sp_loopback_network.hosts())[self.sp_loopback_counter]
            self.loopback_ips[router] = f"{ip}/32"
            self.sp_loopback_counter += 1
        return self.loopback_ips[router]

    def get_ce_loopback_ip(self, router):
        """
        Allocate a /32 loopback ip for CE router
        """
        if router not in self.ce_loopback_ips:
            customer_name = self.ce_to_customer[router]
            counter = self.ce_loopback_counters[customer_name]
            network = self.customer_loopback_networks[customer_name]
            ip = list(network.hosts())[counter]
            self.ce_loopback_ips[router] = f"{ip}/32"
            self.ce_loopback_counters[customer_name] += 1
        return self.ce_loopback_ips[router]

    def get_ex_loopback_ip(self, router):
        """
        Allocate a /32 loopback ip for external router
        """
        if router not in self.ex_loopback_ips:
            as_name = self.ex_to_as[router]
            counter = self.ex_loopback_counters[as_name]
            network = self.external_loopback_networks[as_name]
            ip = list(network.hosts())[counter]
            self.ex_loopback_ips[router] = f"{ip}/32"
            self.ex_loopback_counters[as_name] += 1
        return self.ex_loopback_ips[router]

    def get_customer_subnet(self, customer, interface):
        """
        Allocate a /30 subnet for PE-CE link
        """
        base = ipaddress.IPv4Network(customer['base_prefix'])
        index = len(self.customer_subnets[customer['name']])
        subnet = list(base.subnets(new_prefix=30))[index]
        self.customer_subnets[customer['name']].append(subnet)
        return subnet

    def get_external_subnet(self, pe, ex):
        """
        Allocate a /30 subnet for PE-EX link
        """
        key = tuple(sorted([pe, ex]))
        if key not in self.link_subnets:
            subnet = list(self.external_network.subnets(new_prefix=30))[len(self.link_subnets)]
            hosts = list(subnet.hosts())
            self.link_subnets[key] = hosts
        return self.link_subnets[key]

def generate_base_config(router, is_ce=False):
    """
    Generates basic router configuration commands
    """
    config = [
        "!",
        f"hostname {router}",
        "no ip domain lookup",
        "ip cef",
    ]
    if not is_ce: # MPLS is only for SP routers (PE and P)
        config += ["mpls label protocol ldp"]
    config += ["!"]
    return config

def configure_loopback(router, allocator, is_ce=False, is_ex=False):
    """
    Configure the loopback interface for a router 
    """
    if is_ex:
        ip = allocator.get_ex_loopback_ip(router)
    else:
        ip = allocator.get_ce_loopback_ip(router) if is_ce else allocator.get_sp_loopback_ip(router)
    return [
        "interface Loopback0",
        f" ip address {ip.split('/')[0]} 255.255.255.255",
        "!"
    ]

def configure_interfaces(router, intent, allocator):
    """
    configure physical interfaces for an SP router
    """
    config = []
    sp = intent['network']['service_provider']
    
    # Core interfaces for SP routers
    for link in sp['links']:
        if router in link['from'] and not link['to'].startswith("CE:") and not link['to'].startswith("EX:"):
            _, local_intf = link['from'].split(':', 1)
            peer_router, peer_intf = link['to'].split(':', 1)
            hosts = allocator.get_link_subnet(router, peer_router)
            # Assign hosts[0] to the lower-named router and hosts[1] to the higher-named router
            ip = hosts[0] if router < peer_router else hosts[1]
            config += [
                f"interface {local_intf}",
                f" ip address {ip} 255.255.255.252",
                " negotiation auto",
                " mpls ip",
                " no shutdown",
            ]
            if 'cost' in link:
                config += [f" ip ospf cost {link['cost']}"]
            config += ["!"]
    
    # Customer-facing interfaces for PE routers
    if router in sp['routers']['PE']:
        for pe_link in intent['protocols']['bgp']['ebgp_peers']:
            if pe_link['pe'] == router:
                customer = next(cust for cust in intent['network']['customers'] if pe_link['vrf'] in cust['vrfs'])
                subnet = allocator.get_customer_subnet(customer, pe_link['interface'])
                config += [
                    f"interface {pe_link['interface']}",
                    f" ip vrf forwarding {pe_link['vrf']}",
                    f" ip address {subnet[2]} 255.255.255.252",  # PE gets second host IP
                    " negotiation auto",
                    " no shutdown",
                    "!"
                ]
    
    # External AS-facing interfaces for PE routers
    if router in sp['routers']['PE']:
        for ex_link in intent['protocols']['bgp']['external_peers']:
            if ex_link['pe'] == router:
                subnet = allocator.get_external_subnet(ex_link['pe'], ex_link['ce'])
                config += [
                    f"interface {ex_link['interface']}",
                    f" ip address {subnet[0]} 255.255.255.252",
                    " negotiation auto",
                    " no shutdown",
                    "!"
                ]
    return config

def configure_ce_interfaces(router, intent, allocator):
    """
    configure the interface for a ce router facing its pe
    """
    pe_link = next(p for p in intent['protocols']['bgp']['ebgp_peers'] if p['ce'] == router)
    vrf = pe_link['vrf']
    customer = next(cust for cust in intent['network']['customers'] if vrf in cust['vrfs'])
    customer_pe_links = [p for p in intent['protocols']['bgp']['ebgp_peers'] if p['vrf'] == vrf]
    index = customer_pe_links.index(pe_link)
    subnet = allocator.customer_subnets[customer['name']][index]
    for link in intent['network']['service_provider']['links']:
        if link['to'].startswith(f"CE:{router}:"):
            ce_intf = link['to'].split(':')[2]
            break
    return [
        f"interface {ce_intf}",
        f" ip address {subnet[1]} 255.255.255.252",  # CE gets first host IP
        " negotiation auto",
        " no shutdown",
        "!"
    ]

def configure_ex_interfaces(router, intent, allocator):
    """
    configure the interface for an external router facing its pe
    """
    ex_link = next(p for p in intent['protocols']['bgp']['external_peers'] if p['ce'] == router)
    pe = ex_link['pe']
    subnet = allocator.get_external_subnet(pe, router)
    for link in intent['network']['service_provider']['links']:
        if link['to'].startswith(f"EX:{router}:"):
            ex_intf = link['to'].split(':')[2]
            break
    return [
        f"interface {ex_intf}",
        f" ip address {subnet[1]} 255.255.255.252",
        " negotiation auto",
        " no shutdown",
        "!"
    ]

def configure_ospf(router, intent, allocator):
    """
    configure ospf for an sp router 
    """
    config = ["router ospf 1"]
    networks = []
    for link in intent['network']['service_provider']['links']:
        if router in link['from'] and not link['to'].startswith("CE:") and not link['to'].startswith("EX:"):
            peer_router = link['to'].split(':')[0]
            hosts = allocator.get_link_subnet(router, peer_router)
            network = ipaddress.ip_network(f"{hosts[0]}/30", strict=False)
            networks.append(f" network {network.network_address} 0.0.0.3 area 0")
    loopback_ip = allocator.get_sp_loopback_ip(router).split('/')[0]
    networks.append(f" network {loopback_ip} 0.0.0.0 area 0")
    return config + networks + ["!"]

def configure_bgp(router, intent, allocator):
    """
    configure bgp for pe routers
    """
    sp = intent['network']['service_provider']
    config = [
        f"router bgp {sp['asn']}",
        " bgp log-neighbor-changes",
    ]
    
    # iBGP with other PE routers
    for peer in sp['routers']['PE']:
        if peer != router:
            peer_ip = allocator.get_sp_loopback_ip(peer).split('/')[0]
            config += [
                f" neighbor {peer_ip} remote-as {sp['asn']}",
                f" neighbor {peer_ip} update-source Loopback0",
                f" neighbor {peer_ip} send-community extended",  # Transmit communities in iBGP
            ]
    
    # eBGP with external AS
    for ex_link in intent['protocols']['bgp']['external_peers']:
        if ex_link['pe'] == router:
            subnet = allocator.get_external_subnet(ex_link['pe'], ex_link['ce'])
            ex_ip = subnet[1]  # External router’s IP
            relationship = ex_link['relationship']
            local_pref = 200 if relationship == "customer" else 50 if relationship == "provider" else 100  # Settlement-free peer
            community = "100:1" if relationship == "customer" else "100:2" if relationship == "provider" else "100:3"
            config += [
                f" neighbor {ex_ip} remote-as {ex_link['asn']}",
                " !",
                " address-family ipv4",
                f"  neighbor {ex_ip} activate",
                f"  neighbor {ex_ip} route-map {relationship}_in in",
                f"  neighbor {ex_ip} route-map {relationship}_out out",
                " exit-address-family",
                "!",
                f"route-map {relationship}_in permit 10",
                f" set community {community}",  # Tag routes with community
                f" set local-preference {local_pref}",  # Set local-preference
                "!",
                f"route-map {relationship}_out permit 10",
            ]
            if relationship == "provider":
                config += [
                    " match community customer_routes"  # Filter routes to provider
                ]
            config += ["!"]

    config += ["!\n address-family vpnv4"]
    # Add route reflector neighbors
    if router in sp.get('route_reflectors', []):
        for peer in sp['routers']['PE']:
            if peer != router:
                peer_ip = allocator.get_sp_loopback_ip(peer).split('/')[0]
                config += [f"  neighbor {peer_ip} route-reflector-client"]
    for peer in sp['routers']['PE']:
        if peer != router:
            peer_ip = allocator.get_sp_loopback_ip(peer).split('/')[0]
            config += [
                f"  neighbor {peer_ip} activate",
                f"  neighbor {peer_ip} send-community extended",
            ]
    config += [" exit-address-family", "!"]
    
    # Configure eBGP for customer VRFs
    for pe_link in intent['protocols']['bgp']['ebgp_peers']:
        if pe_link['pe'] == router:
            vrf = pe_link['vrf']
            customer = next(cust for cust in intent['network']['customers'] if vrf in cust['vrfs'])
            index = [p['ce'] for p in intent['protocols']['bgp']['ebgp_peers'] if p['vrf'] == vrf].index(pe_link['ce'])
            subnet = allocator.customer_subnets[customer['name']][index]
            ce_ip = subnet[1]  # CE’s IP matches its interface IP
            config += [
                f" address-family ipv4 vrf {vrf}",
                "  redistribute connected",
                f"  neighbor {ce_ip} remote-as {customer['asn']}",
                f"  neighbor {ce_ip} activate",
                " exit-address-family",
                "!"
            ]
    
    # Define community list for filtering
    config += [
        "ip community-list standard customer_routes permit 100:1",
        "!"
    ]
    return config

def configure_ce_bgp(router, intent, allocator):
    """
    configure bgp for a ce router 
    """
    pe_link = next(p for p in intent['protocols']['bgp']['ebgp_peers'] if p['ce'] == router)
    vrf = pe_link['vrf']
    customer = next(cust for cust in intent['network']['customers'] if vrf in cust['vrfs'])
    customer_pe_links = [p for p in intent['protocols']['bgp']['ebgp_peers'] if p['vrf'] == vrf]
    index = customer_pe_links.index(pe_link)
    subnet = allocator.customer_subnets[customer['name']][index]
    pe_ip = subnet[2]  # PE’s interface IP
    loopback_ip = allocator.get_ce_loopback_ip(router).split('/')[0]
    return [
        f"router bgp {customer['asn']}",
        " bgp log-neighbor-changes",
        f" neighbor {pe_ip} remote-as {intent['network']['service_provider']['asn']}",
        " !",
        " address-family ipv4",
        f"  network {loopback_ip} mask 255.255.255.255",
        f"  neighbor {pe_ip} activate",
        " exit-address-family",
        "!"
    ]

def configure_ex_bgp(router, intent, allocator):
    """
    configure bgp for an external router 
    """
    ex_link = next(p for p in intent['protocols']['bgp']['external_peers'] if p['ce'] == router)
    pe = ex_link['pe']
    subnet = allocator.get_external_subnet(pe, router)
    pe_ip = subnet[0]
    loopback_ip = allocator.get_ex_loopback_ip(router).split('/')[0]
    external_as = next(ext for ext in intent['network']['external_as'] if router in ext['routers'])
    return [
        f"router bgp {external_as['asn']}",
        " bgp log-neighbor-changes",
        f" neighbor {pe_ip} remote-as {intent['network']['service_provider']['asn']}",
        " !",
        " address-family ipv4",
        f"  network {loopback_ip} mask 255.255.255.255",
        f"  neighbor {pe_ip} activate",
        " exit-address-family",
        "!"
    ]

def configure_vrfs(router, intent):
    """
    configure VRFs for PE routers
    """
    if router not in intent['network']['service_provider']['routers']['PE']:
        return [] # only PE routers need VRFs
    
    vrfs = set() # to collect unique VRFs for a given PE
    for peer in intent['protocols']['bgp']['ebgp_peers']:
        if peer['pe'] == router:
            vrfs.add(peer['vrf'])
    
    config = []
    for vrf in vrfs:
        customer = next(cust for cust in intent['network']['customers'] if vrf in cust['vrfs'])
        vrf_info = customer['vrfs'][vrf]
        config += [
            f"ip vrf {vrf}",
            f" rd {vrf_info['rd']}",
            f" route-target export {vrf_info['rt']}",
        ]
        if 'import_rts' in vrf_info:
            for rt in vrf_info['import_rts']:
                config += [f" route-target import {rt}"]
        config += [f" route-target import {vrf_info['rt']}", "!"]
    return config

def generate_config(router, intent, allocator, is_ce, is_ex):
    """
    generate the full configuration for a router
    """
    config = generate_base_config(router, is_ce or is_ex)
    
    # Add VRFs for PE routers only
    if not is_ce and not is_ex and router in intent['network']['service_provider']['routers']['PE']:
        config += configure_vrfs(router, intent)
    
    config += configure_loopback(router, allocator, is_ce, is_ex)
    if not is_ce and not is_ex:
        # SP router configs
        config += configure_interfaces(router, intent, allocator)
        config += configure_ospf(router, intent, allocator)
        if router in intent['network']['service_provider']['routers']['PE']:
            config += configure_bgp(router, intent, allocator)
    elif is_ce:
        # CE router configs
        config += configure_ce_interfaces(router, intent, allocator)
        config += configure_ce_bgp(router, intent, allocator)
    else:
        # External router configs
        config += configure_ex_interfaces(router, intent, allocator)
        config += configure_ex_bgp(router, intent, allocator)
    
    return "\n".join(config)

def main():
    """
    Main function to generate config files for all routers
    """
    intent = load_intent("intent.json")
    allocator = IPAllocator(intent)
    os.makedirs("configs", exist_ok=True) # makes configs directory if it doesn't exist
    sp_routers = intent['network']['service_provider']['routers']['PE'] + intent['network']['service_provider']['routers']['P']
    # set of ce routers from ebgp peers
    ce_routers = set(peer['ce'] for peer in intent['protocols']['bgp']['ebgp_peers'])
    # set of external routers
    ex_routers = set(peer['ce'] for peer in intent['protocols']['bgp']['external_peers'])
    all_routers = sp_routers + list(ce_routers) + list(ex_routers) # combines all routers into one list
    for router in all_routers:
        is_ce = router in ce_routers # determines if it's a ce router
        is_ex = router in ex_routers # determines if it's an external router
        config = generate_config(router, intent, allocator, is_ce, is_ex)
        with open(f"configs/{router}_startup-config.cfg", "w") as f:
            f.write(config)
    print(f"Generated {len(all_routers)} config files in 'configs' directory")

if __name__ == "__main__":
    main()
    get_address_file()
    run_network_visualization("intent.json", "interface_summary.txt")
