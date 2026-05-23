#!/usr/bin/env python3
"""
Uptime tracking system for coins and servers.

Tracks server and coin connectivity status over time, providing:
- Historical uptime data
- Offline duration tracking  
- Contact-based alerting for offline servers
- Automated cleanup of old data
"""

import json
import time
import os
from typing import Dict, List, Tuple, Optional
from logger import logger


class UptimeTracker:
    def __init__(self, uptime_file_path: str = "uptime_history.json"):
        """
        Initialize uptime tracker.
        
        Args:
            uptime_file_path: Path to the JSON file storing uptime data
        """
        self.uptime_file_path = uptime_file_path
        self.uptime_data = self._load_uptime_data()
        self.current_timestamp = int(time.time())
        
        # Time thresholds in seconds
        self.CLEANUP_THRESHOLD = 365 * 24 * 60 * 60  # 1 year
        self.OFFLINE_ALERT_THRESHOLD = 3 * 24 * 60 * 60  # 3 days
        self.OFFLINE_REMOVAL_THRESHOLD = 30 * 24 * 60 * 60  # 30 days (1 month)
        
        # Token suffixes to exclude from uptime tracking (they inherit parent chain status)
        self.EXCLUDED_TOKEN_SUFFIXES = ["-QRC20", "-ERC20", "-BEP20", "-PLG20", "-AVX20", "-GRC20"]
        
    def _should_exclude_coin(self, coin: str) -> bool:
        """
        Check if a coin should be excluded from uptime tracking.
        
        Args:
            coin: The coin ticker to check
            
        Returns:
            True if the coin should be excluded, False otherwise
        """
        return any(coin.endswith(suffix) for suffix in self.EXCLUDED_TOKEN_SUFFIXES)
        
    def _load_uptime_data(self) -> Dict:
        """Load existing uptime data from file."""
        if not os.path.exists(self.uptime_file_path):
            return {}
            
        try:
            with open(self.uptime_file_path, 'r') as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"Could not load uptime data from {self.uptime_file_path}: {e}")
            return {}
    
    def _save_uptime_data(self):
        """Save uptime data to file."""
        try:
            with open(self.uptime_file_path, 'w') as f:
                json.dump(self.uptime_data, f, indent=2, sort_keys=True)
        except Exception as e:
            logger.error(f"Failed to save uptime data to {self.uptime_file_path}: {e}")
    
    def _get_latest_status(self, status_history: Dict[str, str]) -> Tuple[Optional[str], Optional[int]]:
        """
        Get the most recent status and timestamp from status history.
        
        Args:
            status_history: Dictionary of timestamp -> status
            
        Returns:
            Tuple of (latest_status, latest_timestamp) or (None, None) if empty
        """
        if not status_history:
            return None, None
            
        # Convert string timestamps to integers for proper sorting
        timestamps = [int(ts) for ts in status_history.keys()]
        latest_timestamp = max(timestamps)
        latest_status = status_history[str(latest_timestamp)]
        
        return latest_status, latest_timestamp
    
    def _cleanup_old_data(self, status_history: Dict[str, str]) -> Dict[str, str]:
        """
        Remove entries older than cleanup threshold.
        
        Args:
            status_history: Dictionary of timestamp -> status
            
        Returns:
            Cleaned status history
        """
        cutoff_time = self.current_timestamp - self.CLEANUP_THRESHOLD
        
        return {
            timestamp: status 
            for timestamp, status in status_history.items()
            if int(timestamp) >= cutoff_time
        }
    
    def _should_update_status(self, status_history: Dict[str, str], new_status: str) -> bool:
        """
        Determine if we should add a new status entry.
        
        Args:
            status_history: Current status history
            new_status: New status to potentially add
            
        Returns:
            True if status should be updated, False otherwise
        """
        latest_status, _ = self._get_latest_status(status_history)
        
        # Always update if no prior data or status has changed
        return latest_status is None or latest_status != new_status
    
    def update_coin_status(self, coin: str, is_online: bool):
        """
        Update overall coin connectivity status.
        
        Args:
            coin: Coin ticker (e.g., "BTC", "ETH")
            is_online: Whether the coin has any working connectivity
        """
        # Skip tracking for excluded token coins
        if self._should_exclude_coin(coin):
            return
            
        if coin not in self.uptime_data:
            self.uptime_data[coin] = {
                "all": {},
                "by_server": {}
            }
        
        status = "online" if is_online else "offline"
        
        if self._should_update_status(self.uptime_data[coin]["all"], status):
            self.uptime_data[coin]["all"][str(self.current_timestamp)] = status
            logger.debug(f"Updated {coin} overall status to {status}")
        
        # Cleanup old data
        self.uptime_data[coin]["all"] = self._cleanup_old_data(self.uptime_data[coin]["all"])
    
    def update_server_status(self, coin: str, server_url: str, is_online: bool, contact_info: Optional[List[Dict]] = None):
        """
        Update specific server connectivity status.
        
        Args:
            coin: Coin ticker
            server_url: Server URL (e.g., "example.com:50001")
            is_online: Whether the server is responding
            contact_info: Optional contact information for the server
        """
        # Skip tracking for excluded token coins
        if self._should_exclude_coin(coin):
            return
            
        if coin not in self.uptime_data:
            self.uptime_data[coin] = {
                "all": {},
                "by_server": {}
            }
        
        if server_url not in self.uptime_data[coin]["by_server"]:
            self.uptime_data[coin]["by_server"][server_url] = {}
        
        status = "online" if is_online else "offline"
        server_history = self.uptime_data[coin]["by_server"][server_url]
        
        if self._should_update_status(server_history, status):
            server_history[str(self.current_timestamp)] = status
            logger.debug(f"Updated {coin} server {server_url} status to {status}")
            
            # Store contact info if provided and server went offline
            if not is_online and contact_info:
                # Store contact info in metadata (not part of status history)
                if "_metadata" not in self.uptime_data[coin]["by_server"]:
                    self.uptime_data[coin]["by_server"]["_metadata"] = {}
                self.uptime_data[coin]["by_server"]["_metadata"][server_url] = {
                    "contact": contact_info
                }
        
        # Cleanup old data
        self.uptime_data[coin]["by_server"][server_url] = self._cleanup_old_data(server_history)
    
    def get_offline_duration(self, status_history: Dict[str, str]) -> Optional[int]:
        """
        Calculate how long something has been continuously offline.
        
        Args:
            status_history: Dictionary of timestamp -> status
            
        Returns:
            Duration in seconds if currently offline, None if online or no data
        """
        latest_status, latest_timestamp = self._get_latest_status(status_history)
        
        if latest_status != "offline" or latest_timestamp is None:
            return None
        
        return self.current_timestamp - latest_timestamp
    
    def get_server_offline_duration(self, coin: str, server_url: str) -> Optional[int]:
        """
        Get how long a specific server has been offline.
        
        Args:
            coin: The coin ticker
            server_url: The server URL
            
        Returns:
            Duration in seconds if currently offline, None if online or no data
        """
        if coin not in self.uptime_data or "by_server" not in self.uptime_data[coin] or server_url not in self.uptime_data[coin]["by_server"]:
            return None
            
        # Server history is already in the correct format: {timestamp: status}
        server_history = self.uptime_data[coin]["by_server"][server_url]
            
        return self.get_offline_duration(server_history)
    
    def get_contact_info(self, coin: str, server_url: str) -> Optional[List[Dict]]:
        """
        Get contact information for a server.
        
        Args:
            coin: Coin ticker
            server_url: Server URL
            
        Returns:
            Contact information list or None if not available
        """
        try:
            metadata = self.uptime_data[coin]["by_server"]["_metadata"]
            return metadata.get(server_url, {}).get("contact")
        except KeyError:
            return None
    
    def generate_alerts(self) -> List[str]:
        """
        Generate alert messages for offline servers and coins.
        
        Returns:
            List of alert messages
        """
        alerts = []
        
        for coin, coin_data in self.uptime_data.items():
            # Check overall coin status
            coin_offline_duration = self.get_offline_duration(coin_data["all"])
            if coin_offline_duration and coin_offline_duration > self.OFFLINE_REMOVAL_THRESHOLD:
                alerts.append(f"CRITICAL: {coin} has been offline for {coin_offline_duration // (24*60*60)} days - consider delisting")
            
            # Check individual servers
            for server_url, server_history in coin_data["by_server"].items():
                if server_url == "_metadata":  # Skip metadata
                    continue
                    
                server_offline_duration = self.get_offline_duration(server_history)
                if not server_offline_duration:
                    continue
                
                days_offline = server_offline_duration // (24 * 60 * 60)
                
                if server_offline_duration > self.OFFLINE_REMOVAL_THRESHOLD:
                    alerts.append(f"CRITICAL: {coin} server {server_url} has been offline for {days_offline} days - consider removal")
                elif server_offline_duration > self.OFFLINE_ALERT_THRESHOLD:
                    try:
                        contact_info = self.get_contact_info(coin, server_url)
                        if isinstance(contact_info, dict):
                            print(f"contact_info is not a list for {coin} server {server_url}!")
                            contact_info = [contact_info]
                        contact_str = ""
                        if contact_info:
                            contacts = []
                            for contact in contact_info:
                                print(f"contact: {contact}")
                                if "email" in contact:
                                    contacts.append(f"email: {contact['email']}")
                                if "discord" in contact:
                                    contacts.append(f"discord: {contact['discord']}")
                                if "telegram" in contact:
                                    contacts.append(f"telegram: {contact['telegram']}")
                            if contacts:
                                contact_str = f" Contact: {', '.join(contacts)}"
                        
                        alerts.append(f"WARNING: {coin} server {server_url} has been offline for {days_offline} days.{contact_str}")
                    except Exception as e:
                        print(f"Error getting contact info for {coin} server {server_url}: {e}")
        return alerts
    
    def get_uptime_stats(self, coin: str, server_url: Optional[str] = None) -> Dict:
        """
        Get uptime statistics for a coin or specific server.
        
        Args:
            coin: Coin ticker
            server_url: Optional server URL for server-specific stats
            
        Returns:
            Dictionary with uptime statistics
        """
        if coin not in self.uptime_data:
            return {"error": f"No data available for {coin}"}
        
        if server_url:
            if server_url not in self.uptime_data[coin]["by_server"]:
                return {"error": f"No data available for {coin} server {server_url}"}
            status_history = self.uptime_data[coin]["by_server"][server_url]
            target = f"{coin} server {server_url}"
        else:
            status_history = self.uptime_data[coin]["all"]
            target = f"{coin} overall"
        
        if not status_history:
            return {"error": f"No status history for {target}"}
        
        # Calculate stats
        total_entries = len(status_history)
        online_entries = sum(1 for status in status_history.values() if status == "online")
        uptime_percentage = (online_entries / total_entries) * 100 if total_entries > 0 else 0
        
        latest_status, latest_timestamp = self._get_latest_status(status_history)
        offline_duration = self.get_offline_duration(status_history)
        
        # Get time range
        timestamps = [int(ts) for ts in status_history.keys()]
        oldest_timestamp = min(timestamps)
        tracking_duration = self.current_timestamp - oldest_timestamp
        
        return {
            "target": target,
            "uptime_percentage": round(uptime_percentage, 2),
            "total_status_changes": total_entries,
            "current_status": latest_status,
            "last_status_change": latest_timestamp,
            "current_offline_duration_days": offline_duration // (24 * 60 * 60) if offline_duration else 0,
            "tracking_duration_days": tracking_duration // (24 * 60 * 60),
            "first_tracked": oldest_timestamp
        }
    
    def save(self):
        """Save current uptime data to file."""
        self._save_uptime_data()
        logger.debug(f"Saved uptime data to {self.uptime_file_path}")


def format_contact_info(contact_list: Optional[List[Dict]]) -> str:
    """
    Format contact information for display.
    
    Args:
        contact_list: List of contact dictionaries
        
    Returns:
        Formatted contact string
    """
    if not contact_list:
        return "No contact info available"
    
    contacts = []
    for contact in contact_list:
        contact_parts = []
        for key, value in contact.items():
            contact_parts.append(f"{key}: {value}")
        if contact_parts:
            contacts.append(", ".join(contact_parts))
    
    return " | ".join(contacts) if contacts else "No contact info available"
