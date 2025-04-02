import json
import os
import ipaddress
from collections import defaultdict

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
    def __init__(self, base_prefix):
        self.base_network = ipaddress.IPv4Network(base_prefix)
        self.link_subnets = {} # to store allocated subnets for SP core links
        self.sp_loopback_network = ipaddress.IPv4Network("192.168.15.0/24")
        self.ce_loopback_network = ipaddress.IPv4Network("192.168.20.0/24")
        self.sp_loopback_counter = 1
        self.ce_loopback_counter = 1
        self.loopback_ips = {}
        self.ce_loopback_ips = {}
        self.customer_subnets = defaultdict(list) # to store customer subnets, keyed by customer name

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
            ip = list(self.sp_loopback_network.hosts())[self.sp_loopback_counter - 1]
            self.loopback_ips[router] = f"{ip}/32"
            self.sp_loopback_counter += 1
        return self.loopback_ips[router]

    def get_ce_loopback_ip(self, router):
        """
        Allocate a /32 loopback ip for CE router
        """
        if router not in self.ce_loopback_ips:
            ip = list(self.ce_loopback_network.hosts())[self.ce_loopback_counter - 1]
            self.ce_loopback_ips[router] = f"{ip}/32"
            self.ce_loopback_counter += 1
        return self.ce_loopback_ips[router]

    def get_customer_subnet(self, customer, interface):
        """
        Allocate a /30 subnet for PE-CE link

        Args:
            customer (dict): Customer data such as 'base_prefix' and 'name'
            interface (str): Interface name (like 'GigabitEthernet2/0')

        Returns:
            list: List of IPs in the subnet
        """
        base = ipaddress.IPv4Network(customer['base_prefix'])
        index = len(self.customer_subnets[customer['name']])
        subnet = list(base.subnets(new_prefix=30))[index]
        self.customer_subnets[customer['name']].append(subnet)
        return subnet

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

def configure_loopback(router, allocator, is_ce=False):
    """
    Configure the loopback interface for a router 

    (allocator is an instance of IPAllocator)
    """

    # choose ce or sp loopback ip based on the router type
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
        if router in link['from'] and not link['to'].startswith("CE:"):
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
                "!"
            ]
    
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
        "!"
    ]

def configure_ospf(router, intent, allocator):
    """
    configure ospf for an sp router 
    """
    config = ["router ospf 1"]
    networks = []
    for link in intent['network']['service_provider']['links']:
        if router in link['from'] and not link['to'].startswith("CE:"):
            peer_router = link['to'].split(':')[0]
            hosts = allocator.get_link_subnet(router, peer_router)
            # Derive network address from the first host IP
            network = ipaddress.ip_network(f"{hosts[0]}/30", strict=False)
            networks.append(f" network {network.network_address} 0.0.0.3 area 0")
    loopback_ip = allocator.get_sp_loopback_ip(router).split('/')[0]
    networks.append(f" network {loopback_ip} 0.0.0.0 area 0")
    return config + networks + ["!"]

def configure_bgp(router, intent, allocator):
    """
    configure bgp for a pe router
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
            ]
    
    # VPNv4 address-family for iBGP
    config += ["!\n address-family vpnv4"]
    for peer in sp['routers']['PE']:
        if peer != router:
            peer_ip = allocator.get_sp_loopback_ip(peer).split('/')[0]
            config += [
                f"  neighbor {peer_ip} activate",
                f"  neighbor {peer_ip} send-community extended",
                f"  neighbor {peer_ip} next-hop-self",
            ]
    config += [" exit-address-family", "!"]
    
    # configure ebgp for customer VRFs
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
            f" route-target import {vrf_info['rt']}",
            "!"
        ]
    return config

def generate_config(router, intent, allocator, is_ce):
    """
    generate the full configuration for a router
    """

    config = generate_base_config(router, is_ce)
    
    # Add VRFs for PE routers only
    if not is_ce and router in intent['network']['service_provider']['routers']['PE']:
        config += configure_vrfs(router, intent)
    
    config += configure_loopback(router, allocator, is_ce)
    if not is_ce:
        # SP router configs
        config += configure_interfaces(router, intent, allocator)
        config += configure_ospf(router, intent, allocator)
        if router in intent['network']['service_provider']['routers']['PE']:
            config += configure_bgp(router, intent, allocator)
    else:
        # CE router configs
        config += configure_ce_interfaces(router, intent, allocator)
        config += configure_ce_bgp(router, intent, allocator)
    
    return "\n".join(config)

def main():
    """
    Main function to generate config files for all routers
    """
    intent = load_intent("intent.json")
    allocator = IPAllocator(intent['network']['service_provider']['base_prefix'])
    os.makedirs("configs", exist_ok=True) # makes configs directory if it doesn't exist
    sp_routers = intent['network']['service_provider']['routers']['PE'] + intent['network']['service_provider']['routers']['P']
    # set of ce routers from ebgp peers
    ce_routers = set(peer['ce'] for peer in intent['protocols']['bgp']['ebgp_peers'])
    all_routers = sp_routers + list(ce_routers) # combines all routers into one list
    for router in all_routers:
        is_ce = router in ce_routers # determines if it's a ce router
        config = generate_config(router, intent, allocator, is_ce)
        with open(f"configs/{router}_startup-config.cfg", "w") as f:
            f.write(config)
    print(f"Generated {len(all_routers)} config files in 'configs' directory")

if __name__ == "__main__":
    main()