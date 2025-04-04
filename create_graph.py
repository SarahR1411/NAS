import json 
import os
import networkx as nx
import matplotlib.pyplot as plt

json_name_file = 'intent.json'
txt_path = 'interface_summary.txt'
def run_network_visualization(json_file, txt_file, output_file=None):
    """
    Run the network visualization program with the specified input files.
    
    Args:
        json_file (str): Path to the JSON file containing network topology data
        txt_file (str): Path to the text file containing interface summary data
        output_file (str, optional): Path to save the visualization image
    """
    try:
        # Check if input files exist
        if not os.path.exists(json_file):
            print(f"Error: JSON file '{json_file}' not found.")
            return False
            
        if not os.path.exists(txt_file):
            print(f"Error: Interface summary file '{txt_file}' not found.")
            return False
        
        # Import necessary libraries
        import json
        import networkx as nx
        import matplotlib.pyplot as plt
        
        # Extract router name from a link endpoint string
        def extract_router_name(endpoint):
            parts = endpoint.split(':')
            if len(parts) > 2:
                return parts[1]
            else:
                return parts[0]
        
        # Extract loopback interfaces from the interface summary file
        def get_local_interfaces(file_path):
            loopback_addresses = dict()
            with open(file_path, 'r') as file:
                current_router = None
                for line in file:
                    line = line.strip()
                    if line.startswith("Router:"):
                        current_router = line.split()[1]
                    elif "Loopback0" in line:
                        loopback_ip = line.split("IP:")[1].split()[0]
                        loopback_addresses[current_router] = loopback_ip
            return loopback_addresses
        
        # Extract a unique list of router names from the links data
        def get_list_router_name(links):
            router_names = set()
            for link in links:
                router_names.add(extract_router_name(link["from"]))
                router_names.add(extract_router_name(link["to"]))
            return list(router_names)
        
        # Create a list of edges (source, target) from the links data
        def add_edges_to_graph(links):
            list_edge = set()
            for link in links:
                source = extract_router_name(link["from"])
                target = extract_router_name(link["to"])
                list_edge.add((source, target))
            return list(list_edge)
        
        # Load data
        with open(json_file, 'r') as f:
            intent_data = json.load(f)
        
        links = intent_data["network"]["service_provider"]["links"]
        loopback_addresses = get_local_interfaces(txt_file)
        
        # Create graph
        G = nx.Graph()
        
        # Add nodes (routers)
        list_routeurs_name = get_list_router_name(links)
        G.add_nodes_from(list_routeurs_name)
        
        # Add loopback IPs as node attributes
        for router, loopback in loopback_addresses.items():
            if router in G.nodes:
                G.nodes[router]['loopback'] = loopback
        
        # Add edges (connections between routers)
        list_edge = add_edges_to_graph(links)
        G.add_edges_from(list_edge)
        
        print("Loopback addresses:", loopback_addresses)
        
        # Visualization
        plt.figure(figsize=(12, 8))
        
        # Use Kamada-Kawai layout for better node spacing
        pos = nx.kamada_kawai_layout(G)
        
        # Draw nodes and edges
        nx.draw(G, pos, with_labels=True, node_color='skyblue', 
                node_size=1000, edge_color='gray', font_size=10, 
                font_weight='bold')
        
        # Create offset positions for loopback labels
        loopback_labels = nx.get_node_attributes(G, 'loopback')
        loopback_pos = {node: (coords[0], coords[1] - 0.08) for node, coords in pos.items()}
        
        # Draw loopback IP labels
        nx.draw_networkx_labels(G, loopback_pos, labels=loopback_labels, 
                            font_size=8, font_color='red', 
                            bbox=dict(facecolor='white', edgecolor='none', alpha=0.7, pad=2))
        
        plt.title("Network Topology Graph")
        plt.tight_layout()
        
        # Save the figure if output file is specified
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            print(f"Visualization saved to {output_file}")
        
        # Display the visualization
        plt.show()
        
        return True
    
    except Exception as e:
        print(f"Error: {str(e)}")
        return False


#run_network_visualization(json_name_file, txt_path, output_file='network_topology.png')