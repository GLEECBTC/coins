#!/usr/bin/env python3
"""
Validate seed-nodes.json against its JSON schema.

This script validates the seed-nodes.json file located in the project root
against the JSON schema defined in utils/seed_nodes_schema.json.
"""

import json
import sys
import os
import asyncio
import time
import socket
import ssl
from pathlib import Path

try:
    import jsonschema
    from jsonschema import validate, ValidationError, SchemaError
except ImportError:
    print("Error: jsonschema package is required. Install it with:")
    print("pip install jsonschema")
    sys.exit(1)

try:
    import websockets
except ImportError:
    print("Error: websockets package is required for WSS connectivity checks. Install it with:")
    print("pip install websockets")
    sys.exit(1)


def wss_port(netid, lp_rpcport=7783):
    """Quick function to get WSS port from netid."""
    """lp_rpcport is hardcoded to 7783 in kdf for calculating wss port"""
    max_netid = (65535 - 40 - lp_rpcport) // 4
    
    if not (0 <= netid <= max_netid):
        raise ValueError(f"NetID must be between 0 and {max_netid}")
    
    if netid == 0:
        other_ports = lp_rpcport
    else:
        other_ports = ((netid // 10) * 40) + lp_rpcport + (netid % 10)
    
    return other_ports + 30


def tcp_port(netid, lp_rpcport=7783):
    """Quick function to get TCP port from netid."""
    """lp_rpcport is hardcoded to 7783 in kdf for calculating tcp port"""
    max_netid = (65535 - 40 - lp_rpcport) // 4
    
    if not (0 <= netid <= max_netid):
        raise ValueError(f"NetID must be between 0 and {max_netid}")
    
    if netid == 0:
        other_ports = lp_rpcport
    else:
        other_ports = ((netid // 10) * 40) + lp_rpcport + (netid % 10)
    
    return other_ports + 20


def get_project_root():
    """Get the project root directory (parent of utils directory)."""
    return Path(__file__).parent.parent


def load_json_file(file_path):
    """Load and parse a JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: File not found: {file_path}")
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {file_path}: {e}")
        return None
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return None


def check_duplicates(seed_nodes):
    """Check for duplicate names and hosts in seed nodes."""
    errors = []
    
    # Check for duplicate names
    names = [node.get('name') for node in seed_nodes if node.get('name')]
    seen_names = set()
    duplicate_names = set()
    
    for name in names:
        if name in seen_names:
            duplicate_names.add(name)
        seen_names.add(name)
    
    if duplicate_names:
        errors.append(f"Duplicate seed node names found: {', '.join(sorted(duplicate_names))}")
    
    # Check for duplicate hosts
    hosts = [node.get('host') for node in seed_nodes if node.get('host')]
    seen_hosts = set()
    duplicate_hosts = set()
    
    for host in hosts:
        if host in seen_hosts:
            duplicate_hosts.add(host)
        seen_hosts.add(host)
    
    if duplicate_hosts:
        errors.append(f"Duplicate seed node hosts found: {', '.join(sorted(duplicate_hosts))}")
    
    return errors


def check_ssl_certificate(host, port, timeout=15):
    """Check SSL certificate to ensure it's not self-signed and return issuer info."""
    try:
        # Create SSL context with default verification
        context = ssl.create_default_context()
        
        # Connect and get certificate information
        with socket.create_connection((host, port), timeout=timeout) as sock:
            with context.wrap_socket(sock, server_hostname=host) as ssock:
                cert = ssock.getpeercert()
                
                # Check if certificate is self-signed
                # A certificate is self-signed if issuer equals subject
                issuer = dict(x[0] for x in cert['issuer'])
                subject = dict(x[0] for x in cert['subject'])
                
                # Extract issuer information
                issuer_cn = issuer.get('commonName', 'Unknown')
                issuer_o = issuer.get('organizationName', '')
                issuer_ou = issuer.get('organizationalUnitName', '')
                
                # Build issuer display string
                issuer_parts = []
                if issuer_cn:
                    issuer_parts.append(f"CN={issuer_cn}")
                if issuer_o:
                    issuer_parts.append(f"O={issuer_o}")
                if issuer_ou:
                    issuer_parts.append(f"OU={issuer_ou}")
                
                issuer_display = ", ".join(issuer_parts) if issuer_parts else "Unknown issuer"
                
                is_self_signed = issuer == subject
                
                if is_self_signed:
                    return False, f"Certificate is self-signed (issuer: {issuer_display})"
                
                return True, f"Certificate is properly signed by {issuer_display}"
                
    except ssl.SSLError as e:
        return False, f"SSL error: {e}"
    except socket.timeout:
        return False, f"SSL check timeout after {timeout}s"
    except Exception as e:
        return False, f"Certificate check error: {e}"


async def test_wss_connection(host, port, timeout=15):
    """Test WSS connection to a seed node and check SSL certificate."""
    wss_url = f"wss://{host}:{port}"
    start_time = time.time()
    
    try:
        # First check SSL certificate
        loop = asyncio.get_event_loop()
        cert_valid, cert_message = await loop.run_in_executor(
            None, check_ssl_certificate, host, port, timeout
        )
        
        if not cert_valid:
            elapsed_time = time.time() - start_time
            return False, f"SSL certificate issue: {cert_message}", elapsed_time
        
        # Connect with timeout using asyncio.wait_for
        websocket = await asyncio.wait_for(websockets.connect(wss_url), timeout=timeout)
        try:
            # Try to send a simple ping to verify the connection works
            await asyncio.wait_for(websocket.ping(), timeout=2)
            elapsed_time = time.time() - start_time
            return True, f"Connected successfully, {cert_message}", elapsed_time
        finally:
            await websocket.close()
    except asyncio.TimeoutError:
        elapsed_time = time.time() - start_time
        return False, f"Connection timeout after {timeout}s", elapsed_time
    except ssl.SSLError as e:
        elapsed_time = time.time() - start_time
        return False, f"SSL error: {e}", elapsed_time
    except OSError as e:
        elapsed_time = time.time() - start_time
        return False, f"Network error: {e}", elapsed_time
    except Exception as e:
        # Handle various websockets exceptions that may vary by version
        elapsed_time = time.time() - start_time
        error_msg = str(e)
        if "invalid uri" in error_msg.lower():
            return False, "Invalid WSS URI", elapsed_time
        elif "status code" in error_msg.lower():
            return False, f"HTTP error: {error_msg}", elapsed_time
        elif "connection closed" in error_msg.lower():
            return False, "Connection closed unexpectedly", elapsed_time
        else:
            return False, f"WebSocket error: {error_msg}", elapsed_time


async def test_tcp_connection(host, port, timeout=15):
    """Test TCP connection to a seed node."""
    start_time = time.time()
    
    def _test_connection():
        try:
            # Create socket and connect with timeout
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((host, port))
            sock.close()
            return result == 0, None
        except socket.gaierror as e:
            return False, f"DNS resolution failed: {e}"
        except Exception as e:
            return False, f"Socket error: {e}"
    
    try:
        # Run the blocking socket operation in a thread pool
        loop = asyncio.get_event_loop()
        success, error_msg = await loop.run_in_executor(None, _test_connection)
        elapsed_time = time.time() - start_time
        
        if success:
            return True, "Connected successfully", elapsed_time
        elif error_msg:
            return False, error_msg, elapsed_time
        else:
            return False, "Connection refused", elapsed_time
            
    except Exception as e:
        elapsed_time = time.time() - start_time
        return False, f"Unexpected error: {e}", elapsed_time


async def check_wss_connectivity(seed_nodes):
    """Check WSS connectivity and SSL certificate validation for seed nodes with WSS support enabled."""
    print("🔍 Checking WSS connectivity and SSL certificates for seed nodes with WSS support...")
    
    wss_nodes = [node for node in seed_nodes if node.get('wss') == True]
    
    if not wss_nodes:
        print("ℹ️  No WSS-enabled seed nodes found")
        return True
    
    connectivity_results = []
    for node in wss_nodes:
        host = node.get('host')
        name = node.get('name', 'unknown')
        netid = node.get('netid', 8762)
        
        try:
            calculated_wss_port = wss_port(netid)
            print(f"  Testing {name} ({host}) on WSS port {calculated_wss_port} (netid: {netid})...")
            print(f"    - Checking SSL certificate validity...")
            success, message, elapsed_time = await test_wss_connection(host, calculated_wss_port)
            connectivity_results.append((name, host, success, message))
        except ValueError as e:
            print(f"  ✗ Invalid netid {netid} for {name}: {e}")
            connectivity_results.append((name, host, False, f"Invalid netid: {e}"))
            elapsed_time = 0
        
        if success:
            print(f"    ✓ WSS connection successful ({elapsed_time:.2f}s)")
            print(f"    ✓ {message}")
        else:
            print(f"    ✗ WSS connection failed: {message} ({elapsed_time:.2f}s)")
    
    successful_connections = sum(1 for _, _, success, _ in connectivity_results if success)
    total_wss_nodes = len(wss_nodes)
    
    print(f"📊 WSS Connectivity Summary: {successful_connections}/{total_wss_nodes} WSS-enabled nodes reachable")
    
    if successful_connections == 0:
        print("✗ FAILURE: No WSS-enabled seed nodes are reachable via WSS")
        return False
    elif successful_connections < total_wss_nodes:
        print("✗ FAILURE: Not all WSS-enabled seed nodes are reachable via WSS")
        return False
    else:
        print("✓ All WSS-enabled seed nodes are reachable via WSS")
        return True


async def check_tcp_connectivity(seed_nodes):
    """Check TCP connectivity for all seed nodes."""
    print("🔍 Checking TCP connectivity for all seed nodes...")
    
    tcp_nodes = seed_nodes  # Check all nodes for TCP connectivity
    
    if not tcp_nodes:
        print("ℹ️  No seed nodes found")
        return True
    
    connectivity_results = []
    for node in tcp_nodes:
        host = node.get('host')
        name = node.get('name', 'unknown')
        netid = node.get('netid', 8762)
        
        try:
            calculated_tcp_port = tcp_port(netid)
            print(f"  Testing {name} ({host}) on TCP port {calculated_tcp_port} (netid: {netid})...")
            success, message, elapsed_time = await test_tcp_connection(host, calculated_tcp_port)
            connectivity_results.append((name, host, success, message))
        except ValueError as e:
            print(f"  ✗ Invalid netid {netid} for {name}: {e}")
            connectivity_results.append((name, host, False, f"Invalid netid: {e}"))
            elapsed_time = 0
        
        if success:
            print(f"    ✓ TCP connection successful ({elapsed_time:.2f}s)")
        else:
            print(f"    ✗ TCP connection failed: {message} ({elapsed_time:.2f}s)")
    
    successful_connections = sum(1 for _, _, success, _ in connectivity_results if success)
    total_tcp_nodes = len(tcp_nodes)
    
    print(f"📊 TCP Connectivity Summary: {successful_connections}/{total_tcp_nodes} nodes reachable via TCP")
    
    if successful_connections == 0:
        print("✗ FAILURE: No seed nodes are reachable via TCP")
        return False
    elif successful_connections < total_tcp_nodes:
        print("✗ FAILURE: Not all seed nodes are reachable via TCP")
        return False
    else:
        print("✓ All seed nodes are reachable via TCP")
        return True


async def validate_seed_nodes(seed_nodes_path=None, schema_path=None):
    """
    Validate seed-nodes.json against its schema and check connectivity.
    
    Args:
        seed_nodes_path: Path to seed-nodes.json (default: project_root/seed-nodes.json)
        schema_path: Path to schema file (default: utils/seed_nodes_schema.json)
    
    Returns:
        bool: True if validation passes, False otherwise
    """
    project_root = get_project_root()
    
    # Set default paths if not provided
    if seed_nodes_path is None:
        seed_nodes_path = project_root / "seed-nodes.json"
    if schema_path is None:
        schema_path = project_root / "utils" / "seed_nodes_schema.json"
    
    print(f"Validating: {seed_nodes_path}")
    print(f"Schema: {schema_path}")
    print("-" * 50)
    
    # Load schema
    schema = load_json_file(schema_path)
    if schema is None:
        return False
    
    # Load seed nodes data
    seed_nodes = load_json_file(seed_nodes_path)
    if seed_nodes is None:
        return False
    
    try:
        # Validate the schema itself first
        jsonschema.Draft202012Validator.check_schema(schema)
        print("✓ Schema is valid")
        
        # Validate the seed nodes data against the schema
        validate(instance=seed_nodes, schema=schema)
        print("✓ Seed nodes file is valid!")
        print(f"✓ Found {len(seed_nodes)} seed nodes")
        
        # Check for duplicates
        duplicate_errors = check_duplicates(seed_nodes)
        if duplicate_errors:
            for error in duplicate_errors:
                print(f"✗ {error}")
            return False
        
        # Print summary of nodes
        for i, node in enumerate(seed_nodes, 1):
            host = node.get('host', 'unknown')
            name = node.get('name', f'node-{i}')
            node_type = node.get('type', 'unknown')
            wss_support = node.get('wss', False)
            netid = node.get('netid', 'unknown') # 14428 is the max netid if rpcport is 7783 lookup max_netid in kdf repo 
            contact_count = len(node.get('contact', []))
            
            # Build protocol indicators
            protocols = []
            if wss_support:
                protocols.append("WSS")
            protocols.append("TCP")  # All nodes are checked for TCP
            protocol_indicator = "+".join(protocols)
            
            print(f"  {i}. {name} ({host}) - type: {node_type} - {protocol_indicator} - netid: {netid} - {contact_count} contact(s)")
        
        # Check WSS connectivity for WSS-enabled nodes
        wss_connectivity_result = await check_wss_connectivity(seed_nodes)
        
        # Check TCP connectivity for TCP-enabled nodes
        tcp_connectivity_result = await check_tcp_connectivity(seed_nodes)
        
        return wss_connectivity_result and tcp_connectivity_result
        
    except SchemaError as e:
        print(f"✗ Schema validation error: {e}")
        return False
    except ValidationError as e:
        print(f"✗ Validation failed: {e.message}")
        if e.absolute_path:
            print(f"  Path: {' -> '.join(str(p) for p in e.absolute_path)}")
        if e.instance:
            print(f"  Invalid value: {e.instance}")
        return False
    except Exception as e:
        print(f"✗ Unexpected error: {e}")
        return False


async def main():
    """Main function to run validation."""
    print("Komodo Seed Nodes Validator")
    print("=" * 50)
    
    # Parse command line arguments
    seed_nodes_path = None
    schema_path = None
    
    # Simple argument parsing
    args = sys.argv[1:]
    i = 0
    while i < len(args):
        arg = args[i]
        if arg in ['--help', '-h']:
            print("Usage: validate_seed_nodes.py [seed-nodes.json] [schema.json]")
            print("  --help, -h          Show this help message")
            print("")
            print("This script validates seed nodes JSON schema and tests connectivity")
            print("for all seed nodes. TCP for all and additionally WSS for seed nodes with 'wss': true.")
            print("WSS connections also validate SSL certificates to ensure they are not self-signed.")
            sys.exit(0)
        elif arg.startswith('--'):
            print(f"Unknown option: {arg}")
            print("Use --help for usage information")
            sys.exit(1)
        elif seed_nodes_path is None:
            seed_nodes_path = Path(arg)
        elif schema_path is None:
            schema_path = Path(arg)
        else:
            print(f"Too many arguments: {arg}")
            print("Use --help for usage information")
            sys.exit(1)
        i += 1
    
    # Run validation
    is_valid = await validate_seed_nodes(seed_nodes_path, schema_path)
    
    print("-" * 50)
    if is_valid:
        print("🎉 Validation completed successfully!")
        sys.exit(0)
    else:
        print("❌ Validation failed!")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main()) 